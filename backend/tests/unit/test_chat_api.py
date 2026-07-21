from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.database import get_db_session
from app.dependencies.auth import get_current_user
from app.main import create_app
from app.models.base import Base
from app.models.entities import Attachment, Conversation, Message, User


@pytest.mark.asyncio
async def test_conversation_crud_enforces_current_user_ownership() -> None:
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
            external_user_id="sub-owner",
            display_name="测试用户",
            role="user",
            status="active",
        )
        other = User(
            external_user_id="sub-other",
            display_name="其他用户",
            role="user",
            status="active",
        )
        session.add_all([user, other])
        await session.commit()
        await session.refresh(user)
        await session.refresh(other)
        other_conversation = Conversation(user_id=other.id, title="不可见会话")
        session.add(other_conversation)
        await session.commit()
        await session.refresh(other_conversation)

    async def override_session() -> AsyncIterator[AsyncSession]:
        async with sessions() as session:
            yield session

    async def override_user() -> User:
        return user

    app = create_app()
    app.dependency_overrides[get_db_session] = override_session
    app.dependency_overrides[get_current_user] = override_user
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            me = await client.get("/api/me")
            assert me.status_code == 200
            assert me.json()["data"]["user_id"] == user.id

            created = await client.post("/api/chat/create", json={"title": "利润下降分析"})
            assert created.status_code == 200
            conversation_id = created.json()["data"]["conversation_id"]
            assert created.json()["data"]["status"] == "draft"

            listed = await client.get("/api/chat/ls")
            assert [item["conversation_id"] for item in listed.json()["data"]["items"]] == [
                conversation_id
            ]

            updated = await client.post(
                "/api/chat/update",
                json={"conversation_id": conversation_id, "title": "华东利润下降"},
            )
            assert updated.json()["data"]["title"] == "华东利润下降"

            forbidden_as_not_found = await client.get(
                f"/api/chat/ls/{other_conversation.id}"
            )
            assert forbidden_as_not_found.status_code == 404

            deleted = await client.post(
                "/api/chat/delete",
                json={"conversation_ids": [conversation_id]},
            )
            assert deleted.json()["data"]["deleted_count"] == 1
            assert (await client.get("/api/chat/ls")).json()["data"]["items"] == []
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()


@pytest.mark.asyncio
async def test_message_query_returns_chronological_messages_and_attachments() -> None:
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
            external_user_id="sub-message",
            display_name="消息用户",
            role="user",
            status="active",
        )
        session.add(user)
        await session.flush()
        conversation = Conversation(user_id=user.id, title="消息会话", status="active")
        session.add(conversation)
        await session.flush()
        first = Message(
            conversation_id=conversation.id,
            seq_no=1,
            role="user",
            content="为什么利润下降？",
        )
        second = Message(
            conversation_id=conversation.id,
            seq_no=2,
            role="assistant",
            content="正在分析。",
        )
        session.add_all([first, second])
        await session.flush()
        session.add(
            Attachment(
                user_id=user.id,
                conversation_id=conversation.id,
                message_id=first.id,
                file_name="profit.csv",
                storage_key="test/profit.csv",
                mime_type="text/csv",
                file_size=128,
                parse_status="success",
            )
        )
        await session.commit()

    async def override_session() -> AsyncIterator[AsyncSession]:
        async with sessions() as session:
            yield session

    async def override_user() -> User:
        return user

    app = create_app()
    app.dependency_overrides[get_db_session] = override_session
    app.dependency_overrides[get_current_user] = override_user
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get(f"/api/chat/ls/{conversation.id}")
        assert response.status_code == 200
        items = response.json()["data"]["items"]
        assert [item["seq_no"] for item in items] == [1, 2]
        assert items[0]["attachments"][0]["file_name"] == "profit.csv"
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()
