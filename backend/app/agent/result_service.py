from datetime import UTC, datetime
from typing import Any

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agent.stage_five_result_service import StageFiveResultService
from app.agent.state import AgentState
from app.agent.storage.workspace import WorkspaceStorage
from app.models.entities import AnalysisResult, Message, ReportFile
from app.services.event_service import event_service
from app.services.task_service import task_service


class _StageFourResultServiceLegacy:
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
        task_id = state["task_id"]
        artifact = self._artifact(state)
        storage_key = f"tasks/{task_id}/result/stage_four_analysis.json"
        file_size, sha256 = self.workspace.write_json(storage_key, artifact)
        summary = self._summary(state)
        markdown = self._markdown(state, summary)

        async with self.sessions() as session:
            task = await task_service.tasks.get_by_id(session, task_id, lock=True)
            if task is None:
                raise RuntimeError(f"task not found: {task_id}")
            existing = await session.scalar(
                select(AnalysisResult).where(AnalysisResult.task_id == task_id)
            )
            if existing is not None:
                return existing
            conversation = await task_service.tasks.lock_conversation_owned(
                session,
                task.conversation_id,
                task.user_id,
            )
            if conversation is None:
                raise RuntimeError(f"conversation not found for task: {task_id}")
            message = Message(
                conversation_id=task.conversation_id,
                task_id=task.id,
                seq_no=await task_service.tasks.next_message_seq(
                    session,
                    task.conversation_id,
                ),
                role="assistant",
                message_type="analysis_summary",
                content=summary,
                content_json={"stage": 4, "formal_attribution_pending": True},
            )
            session.add(message)
            await session.flush()

            metrics = list(state.get("metric_results", {}).get("metrics", []))
            missing_messages = list(state.get("data_quality", {}).get("gaps", []))
            missing_messages.extend(
                str(item.get("message"))
                for item in state.get("metric_results", {}).get("data_gaps", [])
                if item.get("message")
            )
            result = AnalysisResult(
                task_id=task.id,
                conversation_id=task.conversation_id,
                schema_version="0.4",
                problem_definition=state["problem_definition"],
                key_metrics_json=metrics,
                evidence_list_json=[],
                conclusion_text=summary,
                missing_data_text="；".join(missing_messages) or "无已识别的数据缺口",
                next_action_text="进入阶段五后生成证据链、归因结论和正式报告。",
                result_markdown=markdown,
                result_file_path=storage_key,
                report_ir_json={
                    "status": "not_generated",
                    "deferred_to_stage": 5,
                    "formal_attribution_pending": True,
                    "analysis_artifact": storage_key,
                },
                validation_status="analysis_only",
            )
            session.add(result)
            await session.flush()
            report_file = ReportFile(
                task_id=task.id,
                conversation_id=task.conversation_id,
                file_type="analysis_json",
                file_name="stage_four_analysis.json",
                storage_key=storage_key,
                file_size=file_size,
                sha256=sha256,
            )
            session.add(report_file)
            conversation.last_message_at = datetime.now(UTC)
            await session.flush()
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
                            "report_file_id": report_file.id,
                            "stage": 4,
                        },
                    ),
                ],
                already_locked=True,
            )
            await session.commit()
        await event_service.publish(self.redis, events)
        return result

    @staticmethod
    def _artifact(state: AgentState) -> dict[str, Any]:
        return {
            "schema_version": "0.4",
            "stage": "analysis_ready",
            "formal_attribution_pending": True,
            "problem_definition": state["problem_definition"],
            "analysis_plan": state.get("analysis_plan", []),
            "query_specs": state.get("query_specs", []),
            "data_files": [
                {
                    key: value
                    for key, value in file_ref.items()
                    if key not in {"storage_key"}
                }
                for file_ref in state.get("data_files", [])
            ],
            "data_quality": state.get("data_quality", {}),
            "metric_results": state.get("metric_results", {}),
            "deferred_outputs": [
                "evidence_list",
                "attribution_candidates",
                "report_ir",
            ],
        }

    @staticmethod
    def _summary(state: AgentState) -> str:
        results = state.get("metric_results", {})
        return (
            f"阶段四数据计算完成：得到 {len(results.get('metrics', []))} 组指标、"
            f"{len(results.get('trends', []))} 组趋势、"
            f"{len(results.get('contributions', []))} 组结构贡献，"
            f"识别 {len(results.get('anomalies', []))} 个统计异常点。"
            "当前产物是可复核的数据分析结果，尚未生成正式归因结论和报告。"
        )

    @staticmethod
    def _markdown(state: AgentState, summary: str) -> str:
        definition = state["problem_definition"]
        metric_lines = "\n".join(
            f"- {item.get('field')}: {item.get('value')}（{item.get('formula')}）"
            for item in state.get("metric_results", {}).get("metrics", [])
        )
        return (
            "# 阶段四分析结果\n\n"
            f"{summary}\n\n"
            "## 问题定义\n\n"
            f"- 指标：{definition.get('metric')}\n"
            f"- 时间范围：{definition.get('time_range')}\n"
            f"- 对比基线：{definition.get('baseline')}\n\n"
            f"## 已计算指标\n\n{metric_lines or '- 无'}\n"
        )


# 兼容旧导入；阶段五起统一持久化经过校验的正式 Report IR。
StageFourResultService = StageFiveResultService
