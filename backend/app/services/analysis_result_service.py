import json
from copy import deepcopy
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.storage.workspace import WorkspaceStorage
from app.core.config import Settings
from app.core.exceptions import AppException, ErrorCode
from app.models.entities import AnalysisResult, AuditLog, ReportFile
from app.repositories.task_repository import TaskRepository
from app.schemas.report import AnalysisResultResponse, GeneratedFileItem


class AnalysisResultService:
    def __init__(self, settings: Settings) -> None:
        self.tasks = TaskRepository()
        self.workspace = WorkspaceStorage(settings.agent_data_root)

    async def get_owned(
        self,
        session: AsyncSession,
        task_id: str,
        user_id: str,
    ) -> AnalysisResultResponse:
        task = await self.tasks.get_owned(session, task_id, user_id)
        if task is None:
            raise AppException(ErrorCode.RESOURCE_NOT_FOUND, "任务不存在", status_code=404)
        result = await session.scalar(
            select(AnalysisResult).where(AnalysisResult.task_id == task_id)
        )
        if result is None:
            raise AppException(ErrorCode.RESOURCE_NOT_FOUND, "分析结果尚未生成", status_code=404)
        files = list(
            await session.scalars(
                select(ReportFile)
                .where(ReportFile.task_id == task_id)
                .order_by(ReportFile.created_at.asc())
            )
        )
        report_ir = sanitize_report_ir(result.report_ir_json)
        return AnalysisResultResponse(
            task_id=task.id,
            result_id=result.id,
            schema_version=result.schema_version,
            problem_definition=result.problem_definition,
            key_metrics=result.key_metrics_json,
            evidence_list=result.evidence_list_json,
            attribution_conclusions=list(report_ir.get("attribution_conclusions", [])),
            conclusion_text=result.conclusion_text,
            missing_data_text=result.missing_data_text,
            next_actions=parse_next_actions(result.next_action_text),
            result_markdown=result.result_markdown or "",
            result_file_path=f"result:{result.id}" if result.result_file_path else None,
            report_ir=report_ir,
            generated_files=[
                GeneratedFileItem(
                    file_id=file.id,
                    file_type=file.file_type,
                    file_name=file.file_name,
                    file_size=file.file_size,
                    download_url=(
                        f"/api/results/{task.id}/export?format={file.file_type}"
                    ),
                )
                for file in files
            ],
            validation_status=result.validation_status,
        )

    async def export_owned(
        self,
        session: AsyncSession,
        task_id: str,
        user_id: str,
        file_type: str,
    ) -> tuple[ReportFile, Path]:
        task = await self.tasks.get_owned(session, task_id, user_id)
        if task is None:
            raise AppException(ErrorCode.RESOURCE_NOT_FOUND, "任务不存在", status_code=404)
        report_file = await session.scalar(
            select(ReportFile).where(
                ReportFile.task_id == task_id,
                ReportFile.file_type == file_type,
            )
        )
        if report_file is None:
            raise AppException(
                ErrorCode.RESOURCE_NOT_FOUND,
                "指定格式的报告文件不存在",
                status_code=404,
            )
        path = self.workspace.resolve_key(report_file.storage_key)
        if not path.is_file():
            raise AppException(ErrorCode.RESOURCE_NOT_FOUND, "报告文件不存在", status_code=404)
        session.add(
            AuditLog(
                actor_user_id=user_id,
                action="report.export",
                resource_type="analysis_task",
                resource_id=task_id,
                detail_json={"file_id": report_file.id, "file_type": file_type},
            )
        )
        await session.commit()
        return report_file, path


def parse_next_actions(value: str) -> list[dict[str, object]]:
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return [{"title": "下一步建议", "description": value}]
    return list(parsed) if isinstance(parsed, list) else []


def sanitize_report_ir(report_ir: dict[str, object]) -> dict[str, object]:
    safe = deepcopy(report_ir)
    generated = safe.get("generated_files")
    if isinstance(generated, list):
        safe["generated_files"] = [
            {key: value for key, value in item.items() if key != "storage_key"}
            for item in generated
            if isinstance(item, dict)
        ]
    return safe


analysis_result_service: AnalysisResultService | None = None


def get_analysis_result_service(settings: Settings) -> AnalysisResultService:
    global analysis_result_service
    if analysis_result_service is None:
        analysis_result_service = AnalysisResultService(settings)
    return analysis_result_service
