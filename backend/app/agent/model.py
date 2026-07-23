import logging
import re
from dataclasses import dataclass
from typing import Protocol

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.agent.errors import AgentExecutionError
from app.agent.state import (
    AnalysisPlanOutput,
    ClarificationOutput,
    ProblemDefinition,
)
from app.core.config import Settings

logger = logging.getLogger(__name__)


def _with_structured_output(model: ChatOpenAI, schema: type):
    """Use function_calling for providers that do not expose OpenAI JSON Schema mode
    (e.g. DeepSeek). json_mode is unreliable because some providers require the word
    'json' in the prompt, and json_schema is OpenAI-only."""
    return model.with_structured_output(schema, method="function_calling")


class ProblemDefinitionExtractor(Protocol):
    async def extract(
        self,
        question: str,
        recent_messages: list[dict[str, object]],
    ) -> ProblemDefinition: ...


class ClarificationGenerator(Protocol):
    async def generate(
        self,
        question: str,
        problem_definition: dict[str, object],
        recent_messages: list[dict[str, object]],
    ) -> str: ...


class AnalysisPlanner(Protocol):
    async def build(
        self,
        question: str,
        problem_definition: dict[str, object],
        attachment_ids: list[str],
    ) -> AnalysisPlanOutput: ...


@dataclass(frozen=True)
class AnalysisModelServices:
    problem_extractor: ProblemDefinitionExtractor
    clarification_generator: ClarificationGenerator
    analysis_planner: AnalysisPlanner


METRIC_ALIASES: dict[str, tuple[str, ...]] = {
    "sales_amount": (
        "销售额",
        "销售收入",
        "营收",
        "成交额",
        "revenue",
        "sales",
        "amount",
        "cur_amount",
        "current_amount",
        "current_sales_amount",
        "total_amount",
        "previous_sales_amount",
        "prev_amount",
    ),
    "profit": ("利润", "毛利", "净利润", "profit"),
    "order_count": ("订单量", "订单数", "单量", "order count", "order_count", "orders"),
    "conversion_rate": ("转化率", "成交率", "conversion rate", "conversion_rate"),
    "inventory": (
        "库存",
        "库存量",
        "当前库存",
        "可用库存",
        "存货",
        "inventory",
        "stock_quantity",
        "current_stock",
    ),
    "customer_count": ("客户数", "用户数", "customer count"),
}


def canonical_metric(metric: str | None) -> str | None:
    """Map a model/user metric alias to the canonical report metric name."""
    if not metric:
        return metric
    candidate = metric.strip().lower().replace(" ", "").replace("_", "")
    for canonical, aliases in METRIC_ALIASES.items():
        names = (canonical, *aliases)
        if any(candidate == name.lower().replace(" ", "").replace("_", "") for name in names):
            return canonical
    return metric

DIMENSION_ALIASES: dict[str, tuple[str, ...]] = {
    "region": ("地区", "区域", "省份", "城市", "region"),
    "product": ("产品", "商品", "品类", "sku", "product"),
    "channel": ("渠道", "平台", "channel"),
    "customer": ("客户", "客群", "customer"),
    "organization": ("部门", "门店", "组织", "团队", "department"),
}


class RuleBasedProblemDefinitionExtractor:
    """Conservative fallback: extract explicit facts and leave unknowns missing."""

    async def extract(
        self,
        question: str,
        recent_messages: list[dict[str, object]],
    ) -> ProblemDefinition:
        clarification_text = " ".join(
            str(item.get("content") or "")
            for item in recent_messages
            if item.get("clarification_for_task")
        )
        text = f"{question} {clarification_text}".strip()
        lowered = text.lower()

        metric = next(
            (
                canonical
                for canonical, aliases in METRIC_ALIASES.items()
                if any(alias.lower() in lowered for alias in aliases)
            ),
            None,
        )
        dimensions = [
            canonical
            for canonical, aliases in DIMENSION_ALIASES.items()
            if any(alias.lower() in lowered for alias in aliases)
        ]
        time_range = self._extract_time_range(text)
        baseline = self._extract_baseline(text)
        subject = "经营数据" if metric else None
        return ProblemDefinition(
            metric=metric,
            subject=subject,
            time_range=time_range,
            baseline=baseline,
            analysis_goal=question.strip(),
            dimensions=dimensions,
            extraction_method="rules",
        )

    @staticmethod
    def _extract_time_range(text: str) -> str | None:
        date_range = re.search(
            r"(20\d{2}[年./-]\d{1,2}(?:[月./-]\d{1,2}日?)?)\s*"
            r"(?:至|到|~|—|-)\s*"
            r"(20\d{2}[年./-]\d{1,2}(?:[月./-]\d{1,2}日?)?)",
            text,
        )
        if date_range:
            return f"{date_range.group(1)}至{date_range.group(2)}"
        for phrase, canonical in (
            ("本月", "current_month"),
            ("这个月", "current_month"),
            ("本季度", "current_quarter"),
            ("本年", "current_year"),
            ("今年", "current_year"),
            ("上月", "previous_month"),
            ("上季度", "previous_quarter"),
            ("去年", "previous_year"),
        ):
            if phrase in text:
                return canonical
        single_period = re.search(r"20\d{2}年(?:第?[一二三四1234]季度|\d{1,2}月)", text)
        return single_period.group(0) if single_period else None

    @staticmethod
    def _extract_baseline(text: str) -> str | None:
        for phrase, canonical in (
            ("去年同期", "year_over_year"),
            ("同比", "year_over_year"),
            ("上月", "previous_period"),
            ("上季度", "previous_period"),
            ("环比", "previous_period"),
            ("预算", "budget"),
            ("目标", "target"),
        ):
            if phrase in text:
                return canonical
        comparison = re.search(r"(?:对比|相比|比较)([^，。；]{1,30})", text)
        return comparison.group(1).strip() if comparison else None


class LangChainProblemDefinitionExtractor:
    def __init__(self, model: ChatOpenAI) -> None:
        self.structured_model = _with_structured_output(model, ProblemDefinition)

    async def extract(
        self,
        question: str,
        recent_messages: list[dict[str, object]],
    ) -> ProblemDefinition:
        compact_context = "\n".join(
            f"{item.get('role', 'unknown')}: {str(item.get('content') or '')[:1000]}"
            for item in recent_messages[-10:]
        )
        try:
            result = await self.structured_model.ainvoke(
                [
                    SystemMessage(
                        content=(
                            "Return only a valid JSON object matching the requested schema. "
                            "你是经营分析问题定义器。只提取用户明确表达的信息，不得补造。"
                            "metric 使用稳定英文名称；缺失 metric、time_range 或 "
                            "baseline 时保留 null。"
                            "analysis_goal 保留原始目标，extraction_method 固定为 model。"
                        )
                    ),
                    HumanMessage(
                        content=f"最近上下文：\n{compact_context}\n\n当前问题：\n{question}"
                    ),
                ]
            )
        except Exception as exc:
            logger.exception("problem definition model invocation failed")
            raise AgentExecutionError(
                "MODEL_INVOCATION_FAILED",
                "问题定义模型调用失败，请检查模型配置后重试",
            ) from exc
        definition = result
        if not isinstance(definition, ProblemDefinition):
            definition = ProblemDefinition.model_validate(definition)
        definition.extraction_method = "model"
        return definition


class LangChainClarificationGenerator:
    def __init__(self, model: ChatOpenAI) -> None:
        self.structured_model = _with_structured_output(model, ClarificationOutput)

    async def generate(
        self,
        question: str,
        problem_definition: dict[str, object],
        recent_messages: list[dict[str, object]],
    ) -> str:
        compact_context = "\n".join(
            f"{item.get('role', 'unknown')}: {str(item.get('content') or '')[:800]}"
            for item in recent_messages[-8:]
        )
        try:
            result = await self.structured_model.ainvoke(
                [
                    SystemMessage(
                        content=(
                            "Return only a valid JSON object matching the requested schema. "
                            "你是经营分析澄清助手。根据问题定义中的 missing_fields，"
                            "生成一个简洁、自然、与用户原问题相关的中文追问。"
                            "只询问完成分析必需的信息，不重复询问已有信息，不给出分析结论。"
                        )
                    ),
                    HumanMessage(
                        content=(
                            f"原问题：{question}\n"
                            f"问题定义：{problem_definition}\n"
                            f"最近上下文：\n{compact_context}"
                        )
                    ),
                ]
            )
        except Exception as exc:
            logger.exception("clarification model invocation failed")
            raise AgentExecutionError(
                "CLARIFICATION_MODEL_FAILED",
                "生成澄清问题失败，请稍后重试",
            ) from exc
        output = (
            result
            if isinstance(result, ClarificationOutput)
            else ClarificationOutput.model_validate(result)
        )
        return output.question.strip()


class LangChainAnalysisPlanner:
    def __init__(self, model: ChatOpenAI) -> None:
        self.structured_model = _with_structured_output(model, AnalysisPlanOutput)

    async def build(
        self,
        question: str,
        problem_definition: dict[str, object],
        attachment_ids: list[str],
    ) -> AnalysisPlanOutput:
        source_hint = "优先读取用户附件" if attachment_ids else "通过受控 Data Agent 查询"
        try:
            result = await self.structured_model.ainvoke(
                [
                    SystemMessage(
                        content=(
                            "Return only a valid JSON object matching the requested schema. "
                            "你是经营分析计划器。输出可执行的阶段四计划和查询规格。"
                            "计划只能使用 query_data、validate_data、analyze_with_pandas 三类步骤，"
                            "但每一步的目标、维度和方法必须针对当前问题动态生成。"
                            "不得生成 SQL、物理文件路径、虚构字段或分析结论。"
                        )
                    ),
                    HumanMessage(
                        content=(
                            f"原问题：{question}\n"
                            f"问题定义：{problem_definition}\n"
                            f"数据来源策略：{source_hint}\n"
                            "请给出所需字段、拆解维度、时间和基线策略。"
                        )
                    ),
                ]
            )
        except Exception as exc:
            logger.exception("analysis plan model invocation failed")
            raise AgentExecutionError(
                "ANALYSIS_PLAN_MODEL_FAILED",
                "生成分析计划失败，请稍后重试",
            ) from exc
        return (
            result
            if isinstance(result, AnalysisPlanOutput)
            else AnalysisPlanOutput.model_validate(result)
        )


def build_analysis_model_services(settings: Settings) -> AnalysisModelServices:
    provider = settings.analysis_model_provider.strip().lower()
    model_name = settings.analysis_model_name.strip()
    api_key = settings.analysis_model_api_key.strip()
    base_url = settings.analysis_model_base_url.strip()
    if not provider:
        provider = "openai_compatible" if base_url else "openai"
    if provider not in {"openai", "openai_compatible"} and not base_url:
        raise AgentExecutionError(
            "MODEL_PROVIDER_UNSUPPORTED",
            f"模型供应商 {settings.analysis_model_provider} 需要提供 OpenAI-compatible BASE_URL",
        )
    if not model_name or not api_key:
        raise AgentExecutionError(
            "MODEL_CONFIG_INCOMPLETE",
            "阶段四必须配置 MODEL_NAME 和 API_KEY，或配置 ANALYSIS_AGENT 专用模型",
        )
    options: dict[str, object] = {
        "model": model_name,
        "api_key": api_key,
        "temperature": 0,
        "timeout": settings.analysis_model_timeout_seconds,
        "max_retries": 2,
    }
    if base_url:
        options["base_url"] = base_url
    model = ChatOpenAI(**options)  # type: ignore[arg-type]
    return AnalysisModelServices(
        problem_extractor=LangChainProblemDefinitionExtractor(model),
        clarification_generator=LangChainClarificationGenerator(model),
        analysis_planner=LangChainAnalysisPlanner(model),
    )
