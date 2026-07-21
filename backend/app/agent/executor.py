import logging

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agent.errors import AgentExecutionError
from app.agent.events import AgentEventEmitter
from app.agent.graph import build_analysis_graph
from app.agent.model import AnalysisModelServices, build_analysis_model_services
from app.agent.nodes.analyze_with_pandas import AnalyzeWithPandasNode
from app.agent.nodes.ask_clarification import AskClarificationNode
from app.agent.nodes.build_analysis_plan import BuildAnalysisPlanNode
from app.agent.nodes.build_evidence import BuildEvidenceNode
from app.agent.nodes.build_report_ir import BuildReportIRNode
from app.agent.nodes.define_problem import DefineProblemNode
from app.agent.nodes.determine_attribution import DetermineAttributionNode
from app.agent.nodes.load_context import LoadContextNode
from app.agent.nodes.query_data import QueryDataNode
from app.agent.nodes.render_report import RenderReportNode
from app.agent.nodes.validate_data import ValidateDataNode
from app.agent.nodes.validate_report import ValidateReportNode
from app.agent.runtime import AgentRuntime
from app.agent.stage_five_result_service import StageFiveResultService
from app.agent.state import AgentState
from app.agent.storage.workspace import WorkspaceStorage
from app.agent.tools.db_query import DataAgentClient, DbQueryTool
from app.agent.tools.file_read import FileReadTool
from app.agent.tools.pandas_analyze import PandasAnalyzeTool
from app.core.config import Settings
from app.reporting.renderer import ReportRenderer
from app.services.context_summary_service import ContextSummaryService
from app.workers.task_worker import (
    TaskExecutionError,
    WorkerContext,
    WorkerOutcome,
)

logger = logging.getLogger(__name__)


class LangGraphTaskExecutor:
    def __init__(
        self,
        redis: Redis,
        sessions: async_sessionmaker[AsyncSession],
        settings: Settings,
        *,
        data_agent_client: DataAgentClient | None = None,
        model_services: AnalysisModelServices | None = None,
    ) -> None:
        self.redis = redis
        self.sessions = sessions
        self.settings = settings
        self.model_services = model_services or build_analysis_model_services(settings)
        self.data_agent_client = data_agent_client
        self.workspace = WorkspaceStorage(settings.agent_data_root)
        self.result_service = StageFiveResultService(redis, sessions, self.workspace)
        self.context_summary_service = ContextSummaryService(sessions, settings)

    async def execute(self, context: WorkerContext) -> WorkerOutcome:
        emitter = AgentEventEmitter(self.redis, self.sessions)
        runtime = AgentRuntime(
            emitter,
            context.check_cancelled,
            self.workspace.root,
        )
        load_context = LoadContextNode(self.sessions, self.settings)
        define_problem = DefineProblemNode(self.model_services.problem_extractor)
        ask_clarification = AskClarificationNode(
            self.model_services.clarification_generator
        )
        build_analysis_plan = BuildAnalysisPlanNode(self.model_services.analysis_planner)
        query_data = QueryDataNode(
            runtime,
            FileReadTool(self.sessions, self.settings),
            DbQueryTool(self.settings, self.data_agent_client),
        )
        validate_data = ValidateDataNode(self.settings, self.workspace.root)
        analyze = AnalyzeWithPandasNode(runtime, PandasAnalyzeTool(self.settings))
        build_evidence = BuildEvidenceNode()
        determine_attribution = DetermineAttributionNode()
        build_report_ir = BuildReportIRNode()
        validate_report = ValidateReportNode()
        render_report = RenderReportNode(ReportRenderer(self.workspace))
        graph = build_analysis_graph(
            runtime,
            load_context,
            define_problem,
            ask_clarification,
            build_analysis_plan,
            query_data,
            validate_data,
            analyze,
            build_evidence,
            determine_attribution,
            build_report_ir,
            validate_report,
            render_report,
        )
        try:
            final_state: AgentState = await graph.ainvoke(
                {"task_id": context.task_id},
                config={"configurable": {"thread_id": context.task_id}},
            )
            clarification = final_state.get("clarification_question")
            if clarification:
                return WorkerOutcome(
                    status="waiting_input",
                    current_step="ask_clarification",
                    clarification_question=clarification,
                )
            await self.result_service.persist(final_state)
            try:
                await self.context_summary_service.compress_if_needed(
                    final_state["conversation_id"]
                )
            except Exception:
                logger.exception(
                    "context compression failed after result persistence",
                    extra={"task_id": context.task_id},
                )
            return WorkerOutcome(status="success", current_step="report_ready")
        except AgentExecutionError as exc:
            raise TaskExecutionError(exc.error_code, exc.user_message) from exc
