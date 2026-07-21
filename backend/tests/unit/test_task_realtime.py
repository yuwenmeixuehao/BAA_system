import logging
import time
from collections import defaultdict
from collections.abc import AsyncIterator
from dataclasses import dataclass

import pytest
from httpx import ASGITransport, AsyncClient
from redis.exceptions import RedisError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.database import get_db_session
from app.core.exceptions import AppException, ErrorCode
from app.core.redis import get_redis
from app.dependencies.auth import get_current_user
from app.main import create_app
from app.models.base import Base
from app.models.entities import AnalysisTask, Conversation, Message, TaskEvent, User
from app.schemas.websocket import UserMessageEvent
from app.services.event_service import event_service
from app.services.task_service import task_service
from app.services.websocket_token_service import websocket_token_service
from app.workers.cancellation import cancellation_service
from app.workers.task_worker import TaskWorker, WorkerContext, WorkerOutcome


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.lists: dict[str, list[str]] = defaultdict(list)
        self.published: list[tuple[str, str]] = []

    async def setex(self, key: str, _: int, value: str) -> None:
        self.values[key] = value

    async def set(
        self,
        key: str,
        value: str,
        *,
        nx: bool = False,
        ex: int | None = None,
    ) -> bool:
        del ex
        if nx and key in self.values:
            return False
        self.values[key] = value
        return True

    async def getdel(self, key: str) -> str | None:
        return self.values.pop(key, None)

    async def exists(self, key: str) -> int:
        return int(key in self.values)

    async def delete(self, key: str) -> None:
        self.values.pop(key, None)

    async def publish(self, channel: str, payload: str) -> None:
        self.published.append((channel, payload))

    async def lpush(self, key: str, value: str) -> None:
        self.lists[key].insert(0, value)

    async def rpush(self, key: str, value: str) -> None:
        self.lists[key].append(value)

    async def brpoplpush(
        self,
        source: str,
        destination: str,
        **options: int,
    ) -> str | None:
        del options
        if not self.lists[source]:
            return None
        value = self.lists[source].pop()
        self.lists[destination].insert(0, value)
        return value

    async def lrem(self, key: str, count: int, value: str) -> int:
        if count == 0:
            previous = len(self.lists[key])
            self.lists[key] = [item for item in self.lists[key] if item != value]
            return previous - len(self.lists[key])
        try:
            self.lists[key].remove(value)
        except ValueError:
            return 0
        return 1


class FailingCancellationRedis(FakeRedis):
    async def exists(self, key: str) -> int:
        del key
        raise RedisError("redis unavailable")


@dataclass
class TaskDatabase:
    sessions: async_sessionmaker[AsyncSession]
    user: User
    conversation: Conversation


@pytest.fixture
async def task_database() -> AsyncIterator[TaskDatabase]:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with sessions() as session:
        user = User(
            external_user_id="task-user",
            display_name="任务用户",
            role="user",
            status="active",
        )
        session.add(user)
        await session.flush()
        conversation = Conversation(user_id=user.id, title="任务会话")
        session.add(conversation)
        await session.commit()
        await session.refresh(user)
        await session.refresh(conversation)
    yield TaskDatabase(sessions=sessions, user=user, conversation=conversation)
    await engine.dispose()


@pytest.mark.asyncio
async def test_task_creation_is_atomic_idempotent_and_rejects_parallel_task(
    task_database: TaskDatabase,
) -> None:
    redis = FakeRedis()
    request = UserMessageEvent(
        type="user_message",
        conversation_id=task_database.conversation.id,
        client_msg_id="client-001",
        content="分析本月利润下降原因",
        attachment_ids=[],
    )
    async with task_database.sessions() as session:
        first = await task_service.create_from_message(
            session,
            redis,  # type: ignore[arg-type]
            task_database.user.id,
            request,
        )
        repeated = await task_service.create_from_message(
            session,
            redis,  # type: ignore[arg-type]
            task_database.user.id,
            request,
        )
        assert first.created is True
        assert repeated.created is False
        assert repeated.task.id == first.task.id
        assert [event.event_type for event in first.events] == ["message_start", "task_status"]
        assert [event.event_seq for event in first.events] == [1, 2]

        with pytest.raises(AppException) as exc_info:
            await task_service.create_from_message(
                session,
                redis,  # type: ignore[arg-type]
                task_database.user.id,
                UserMessageEvent(
                    type="user_message",
                    conversation_id=task_database.conversation.id,
                    client_msg_id="client-002",
                    content="再创建一个任务",
                    attachment_ids=[],
                ),
            )
        assert exc_info.value.code == ErrorCode.TASK_ALREADY_RUNNING

        task_count = await session.scalar(select(func.count()).select_from(AnalysisTask))
        message_count = await session.scalar(select(func.count()).select_from(Message))
        assert task_count == 1
        assert message_count == 1


@pytest.mark.asyncio
async def test_event_batch_allocates_contiguous_sequences_with_one_lock(
    task_database: TaskDatabase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis = FakeRedis()
    async with task_database.sessions() as session:
        outcome = await task_service.create_from_message(
            session,
            redis,  # type: ignore[arg-type]
            task_database.user.id,
            UserMessageEvent(
                type="user_message",
                conversation_id=task_database.conversation.id,
                client_msg_id="batch-001",
                content="验证事件批量写入",
                attachment_ids=[],
            ),
        )
        lock_count = 0
        original_get_by_id = event_service.tasks.get_by_id

        async def counting_get_by_id(
            current_session: AsyncSession,
            task_id: str,
            *,
            lock: bool = False,
        ) -> AnalysisTask | None:
            nonlocal lock_count
            if lock:
                lock_count += 1
            return await original_get_by_id(current_session, task_id, lock=lock)

        monkeypatch.setattr(event_service.tasks, "get_by_id", counting_get_by_id)
        events = await event_service.append_many(
            session,
            outcome.task,
            [
                ("tool_start", {"tool_name": "db_query"}),
                ("tool_finish", {"tool_name": "db_query"}),
                ("task_status", {"task_status": "running"}),
            ],
        )
        await session.commit()

    assert lock_count == 1
    assert [event.event_seq for event in events] == [3, 4, 5]


@pytest.mark.asyncio
async def test_cancellation_check_logs_redis_degradation_and_falls_back_to_database(
    task_database: TaskDatabase,
    caplog: pytest.LogCaptureFixture,
) -> None:
    redis = FailingCancellationRedis()
    with caplog.at_level(
        logging.WARNING,
        logger="app.workers.cancellation",
    ):
        async with task_database.sessions() as session:
            requested = await cancellation_service.is_requested(
                redis,  # type: ignore[arg-type]
                session,
                "missing-task",
            )

    assert requested is False
    assert "cancellation marker check degraded to database" in caplog.text
    assert caplog.records[-1].task_id == "missing-task"


@pytest.mark.asyncio
async def test_queued_task_can_be_cancelled_and_events_can_be_replayed(
    task_database: TaskDatabase,
) -> None:
    redis = FakeRedis()
    async with task_database.sessions() as session:
        outcome = await task_service.create_from_message(
            session,
            redis,  # type: ignore[arg-type]
            task_database.user.id,
            UserMessageEvent(
                type="user_message",
                conversation_id=task_database.conversation.id,
                client_msg_id="cancel-001",
                content="创建后立即取消",
                attachment_ids=[],
            ),
        )
        result = await task_service.cancel(
            session,
            redis,  # type: ignore[arg-type]
            outcome.task.id,
            task_database.user.id,
        )
        replay = await task_service.list_events_owned(
            session,
            outcome.task.id,
            task_database.user.id,
            after_seq=2,
        )

    assert result.task_status == "cancelled"
    assert result.cancel_requested is True
    assert [event.type for event in replay.items] == ["task_status", "done"]
    assert [event.event_seq for event in replay.items] == [3, 4]


@pytest.mark.asyncio
async def test_task_query_event_and_cancel_http_endpoints(
    task_database: TaskDatabase,
) -> None:
    redis = FakeRedis()
    async with task_database.sessions() as session:
        outcome = await task_service.create_from_message(
            session,
            redis,  # type: ignore[arg-type]
            task_database.user.id,
            UserMessageEvent(
                type="user_message",
                conversation_id=task_database.conversation.id,
                client_msg_id="api-001",
                content="验证任务接口",
                attachment_ids=[],
            ),
        )

    async def override_session() -> AsyncIterator[AsyncSession]:
        async with task_database.sessions() as session:
            yield session

    async def override_user() -> User:
        return task_database.user

    async def override_redis() -> FakeRedis:
        return redis

    app = create_app()
    app.dependency_overrides[get_db_session] = override_session
    app.dependency_overrides[get_current_user] = override_user
    app.dependency_overrides[get_redis] = override_redis
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            task_response = await client.get(f"/api/tasks/{outcome.task.id}")
            events_response = await client.get(
                f"/api/tasks/{outcome.task.id}/events",
                params={"after_seq": 0},
            )
            cancel_response = await client.post(f"/api/tasks/{outcome.task.id}/cancel")
        assert task_response.status_code == 200
        assert task_response.json()["data"]["task_status"] == "queued"
        assert [item["event_seq"] for item in events_response.json()["data"]["items"]] == [
            1,
            2,
        ]
        assert cancel_response.status_code == 200
        assert cancel_response.json()["data"]["task_status"] == "cancelled"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_websocket_token_is_bound_to_conversation_and_single_use(
    task_database: TaskDatabase,
) -> None:
    redis = FakeRedis()
    async with task_database.sessions() as session:
        issued = await websocket_token_service.issue(
            session,
            redis,  # type: ignore[arg-type]
            task_database.user.id,
            task_database.conversation.id,
        )
        user_id = await websocket_token_service.consume(
            session,
            redis,  # type: ignore[arg-type]
            issued.websocket_token,
            task_database.conversation.id,
        )
        assert user_id == task_database.user.id
        with pytest.raises(AppException) as exc_info:
            await websocket_token_service.consume(
                session,
                redis,  # type: ignore[arg-type]
                issued.websocket_token,
                task_database.conversation.id,
            )
        assert exc_info.value.code == ErrorCode.UNAUTHORIZED


class WaitingInputExecutor:
    async def execute(self, context: WorkerContext) -> WorkerOutcome:
        await context.check_cancelled()
        return WorkerOutcome(
            status="waiting_input",
            current_step="define_problem",
            clarification_question="请补充时间范围和对比基线。",
        )


class StopWorkerLoop(Exception):
    pass


@pytest.mark.asyncio
async def test_worker_retries_after_transient_redis_error(
    task_database: TaskDatabase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis = FakeRedis()
    worker = TaskWorker(redis, task_database.sessions)  # type: ignore[arg-type]
    worker.last_recovery_at = time.monotonic()
    attempts = 0
    delays: list[float] = []

    async def process_once_with_transient_failure(
        executor: WaitingInputExecutor,
        *,
        block_seconds: int | None = None,
    ) -> bool:
        nonlocal attempts
        del executor, block_seconds
        attempts += 1
        if attempts == 1:
            raise RedisError("temporary Redis timeout")
        raise StopWorkerLoop

    async def record_sleep(delay: float) -> None:
        delays.append(delay)

    monkeypatch.setattr(worker, "process_once", process_once_with_transient_failure)
    monkeypatch.setattr("app.workers.task_worker.asyncio.sleep", record_sleep)

    with pytest.raises(StopWorkerLoop):
        await worker.run_forever(WaitingInputExecutor())

    assert attempts == 2
    assert delays == [1.0]


@pytest.mark.asyncio
async def test_worker_consumes_task_and_persists_status_events(
    task_database: TaskDatabase,
) -> None:
    redis = FakeRedis()
    async with task_database.sessions() as session:
        outcome = await task_service.create_from_message(
            session,
            redis,  # type: ignore[arg-type]
            task_database.user.id,
            UserMessageEvent(
                type="user_message",
                conversation_id=task_database.conversation.id,
                client_msg_id="worker-001",
                content="请执行任务",
                attachment_ids=[],
            ),
        )

    worker = TaskWorker(redis, task_database.sessions)  # type: ignore[arg-type]
    assert await worker.process_once(WaitingInputExecutor(), block_seconds=1) is True

    async with task_database.sessions() as session:
        task = await session.get(AnalysisTask, outcome.task.id)
        events = list(
            await session.scalars(
                select(TaskEvent)
                .where(TaskEvent.task_id == outcome.task.id)
                .order_by(TaskEvent.event_seq)
            )
        )
    assert task is not None
    assert task.task_status == "waiting_input"
    assert task.started_at is not None
    assert [event.event_type for event in events] == [
        "message_start",
        "task_status",
        "task_status",
        "task_status",
        "clarification_required",
    ]
