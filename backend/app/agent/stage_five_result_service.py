import json
from datetime import UTC, datetime

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agent.state import AgentState
from app.agent.storage.workspace import WorkspaceStorage
from app.models.entities import AnalysisResult, Message, ReportFile
from app.schemas.report import ReportIR
from app.services.event_service import event_service
from app.services.task_service import task_service


class StageFiveResultService:
    def __init__(
        self,
        redis: Redis,
        sessions: async_sessionmaker[AsyncSession],
        workspace: WorkspaceStorage,
    ) -> None:
        self.redis = redis
        self.sessions = sessions
        self.workspace = workspace

    async def persist(self, state: AgentState) -> AnalysisResult:
        report = ReportIR.model_validate(state["report_ir"])
        generated_files = state.get("generated_files", [])
        if not generated_files:
            raise RuntimeError("validated report has no generated files")
        markdown_file = next(
            item for item in generated_files if item.get("file_type") == "md"
        )
        html_file = next(
            item for item in generated_files if item.get("file_type") == "html"
        )
        markdown = self.workspace.resolve_key(
            str(markdown_file["storage_key"])
        ).read_text(encoding="utf-8")
        summary = build_summary(report)

        async with self.sessions() as session:
            task = await task_service.tasks.get_by_id(session, state["task_id"], lock=True)
            if task is None:
                raise RuntimeError(f"task not found: {state['task_id']}")
            existing = await session.scalar(
                select(AnalysisResult).where(AnalysisResult.task_id == task.id)
            )
            if existing is not None:
                return existing
            conversation = await task_service.tasks.lock_conversation_owned(
                session,
                task.conversation_id,
                task.user_id,
            )
            if conversation is None:
                raise RuntimeError(f"conversation not found for task: {task.id}")
            conclusion_text = "\n".join(
                f"{item.title}：{item.description}"
                for item in report.attribution_conclusions
            )
            missing_data_text = "\n".join(
                f"{item.reason}；{item.required_action}" for item in report.missing_data
            ) or "无已识别的数据缺口"
            result = AnalysisResult(
                task_id=task.id,
                conversation_id=task.conversation_id,
                schema_version=report.schema_version,
                problem_definition=report.problem_definition.model_dump(mode="json"),
                key_metrics_json=[item.model_dump(mode="json") for item in report.key_metrics],
                evidence_list_json=[
                    item.model_dump(mode="json") for item in report.evidence_list
                ],
                conclusion_text=conclusion_text,
                missing_data_text=missing_data_text,
                next_action_text=json.dumps(
                    [item.model_dump(mode="json") for item in report.next_actions],
                    ensure_ascii=False,
                ),
                result_markdown=markdown,
                result_file_path=str(html_file["storage_key"]),
                report_ir_json=report.model_dump(mode="json"),
                validation_status="valid",
            )
            session.add(result)
            await session.flush()
            report_files: list[ReportFile] = []
            for file_info in generated_files:
                report_file = ReportFile(
                    task_id=task.id,
                    conversation_id=task.conversation_id,
                    file_type=str(file_info["file_type"]),
                    file_name=str(file_info["file_name"]),
                    storage_key=str(file_info["storage_key"]),
                    file_size=int(file_info["file_size"]),
                    sha256=str(file_info["sha256"]),
                )
                session.add(report_file)
                report_files.append(report_file)
            message = Message(
                conversation_id=task.conversation_id,
                task_id=task.id,
                seq_no=await task_service.tasks.next_message_seq(
                    session,
                    task.conversation_id,
                ),
                role="assistant",
                message_type="report",
                content=summary,
                content_json={
                    "stage": 5,
                    "result_id": result.id,
                    "validation_status": "valid",
                },
            )
            session.add(message)
            conversation.last_message_at = datetime.now(UTC)
            await session.flush()
            file_ids = [item.id for item in report_files]
            events = await event_service.append_many(
                session,
                task,
                [
                    (
                        "message_start",
                        {
                            "message_id": message.id,
                            "task_id": task.id,
                            "role": "assistant",
                            "seq_no": message.seq_no,
                        },
                    ),
                    (
                        "message_delta",
                        {
                            "message_id": message.id,
                            "seq_no": message.seq_no,
                            "delta_text": summary,
                            "complete": True,
                        },
                    ),
                    (
                        "result_ready",
                        {
                            "result_id": result.id,
                            "file_ids": file_ids,
                            "stage": 5,
                            "validation_status": "valid",
                        },
                    ),
                ],
                already_locked=True,
            )
            await session.commit()
        await event_service.publish(self.redis, events)
        return result


def build_summary(report: ReportIR) -> str:
    conclusions = "；".join(item.title for item in report.attribution_conclusions[:3])
    return (
        f"正式归因报告已生成并通过 Report IR 校验。"
        f"共形成 {len(report.key_metrics)} 项指标、{len(report.evidence_list)} 条证据，"
        f"主要结论：{conclusions}。"
    )
