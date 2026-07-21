from langgraph.graph import END, START, StateGraph

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
from app.agent.state import AgentState


def build_analysis_graph(
    runtime: AgentRuntime,
    load_context: LoadContextNode,
    define_problem: DefineProblemNode,
    ask_clarification: AskClarificationNode,
    build_analysis_plan: BuildAnalysisPlanNode,
    query_data: QueryDataNode,
    validate_data: ValidateDataNode,
    analyze_with_pandas: AnalyzeWithPandasNode,
    build_evidence: BuildEvidenceNode,
    determine_attribution: DetermineAttributionNode,
    build_report_ir: BuildReportIRNode,
    validate_report: ValidateReportNode,
    render_report: RenderReportNode,
):
    builder = StateGraph(AgentState)
    builder.add_node("load_context", runtime.wrap_node("load_context", load_context))
    builder.add_node("define_problem", runtime.wrap_node("define_problem", define_problem))
    builder.add_node(
        "ask_clarification",
        runtime.wrap_node("ask_clarification", ask_clarification),
    )
    builder.add_node(
        "build_analysis_plan",
        runtime.wrap_node("build_analysis_plan", build_analysis_plan),
    )
    builder.add_node("query_data", runtime.wrap_node("query_data", query_data))
    builder.add_node("validate_data", runtime.wrap_node("validate_data", validate_data))
    builder.add_node(
        "analyze_with_pandas",
        runtime.wrap_node("analyze_with_pandas", analyze_with_pandas),
    )
    builder.add_node("build_evidence", runtime.wrap_node("build_evidence", build_evidence))
    builder.add_node(
        "determine_attribution",
        runtime.wrap_node("determine_attribution", determine_attribution),
    )
    builder.add_node(
        "build_report_ir",
        runtime.wrap_node("build_report_ir", build_report_ir),
    )
    builder.add_node(
        "validate_report",
        runtime.wrap_node("validate_report", validate_report),
    )
    builder.add_node("render_report", runtime.wrap_node("render_report", render_report))
    builder.add_edge(START, "load_context")
    builder.add_edge("load_context", "define_problem")
    builder.add_conditional_edges(
        "define_problem",
        lambda state: (
            "clarify"
            if state.get("problem_definition", {}).get("missing_fields")
            else "plan"
        ),
        {"clarify": "ask_clarification", "plan": "build_analysis_plan"},
    )
    builder.add_edge("ask_clarification", END)
    builder.add_edge("build_analysis_plan", "query_data")
    builder.add_edge("query_data", "validate_data")
    builder.add_edge("validate_data", "analyze_with_pandas")
    builder.add_edge("analyze_with_pandas", "build_evidence")
    builder.add_edge("build_evidence", "determine_attribution")
    builder.add_edge("determine_attribution", "build_report_ir")
    builder.add_edge("build_report_ir", "validate_report")
    builder.add_conditional_edges(
        "validate_report",
        lambda state: "render" if state.get("report_valid") else "retry",
        {"render": "render_report", "retry": "build_report_ir"},
    )
    builder.add_edge("render_report", END)
    return builder.compile()
