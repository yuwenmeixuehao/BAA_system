from typing import Any

from app.agent.state import AgentState


class DetermineAttributionNode:
    async def __call__(self, state: AgentState) -> AgentState:
        conclusions: list[dict[str, Any]] = []
        evidence = state.get("evidence_list", [])

        def append(item: dict[str, Any]) -> None:
            item["conclusion_id"] = f"c_{len(conclusions) + 1:03d}"
            conclusions.append(item)

        comparison_items = [item for item in evidence if item.get("kind") == "comparison"]
        for item in comparison_items[:1]:
            change = float(item.get("change_value") or 0.0)
            direction = "下降" if change < 0 else "上升"
            status, confidence, verification_needed = attribution_level(item, 0.98)
            append(
                {
                    "title": f"目标指标较基线{direction}",
                    "description": item["description"],
                    "status": status,
                    "impact_level": impact_level(item.get("change_rate")),
                    "confidence": confidence,
                    "evidence_ids": [item["evidence_id"]],
                    "verification_needed": verification_needed,
                }
            )

        dimension_items = [
            item
            for item in evidence
            if item.get("kind") == "dimension_change"
            and float(item.get("change_value") or 0.0) < 0
        ]
        dimension_items.sort(
            key=lambda item: abs(float(item.get("change_value") or 0.0)),
            reverse=True,
        )
        for item in dimension_items[:3]:
            status, confidence, verification_needed = attribution_level(item, 0.95)
            append(
                {
                    "title": f"{item.get('dimension_value')}贡献了主要下降",
                    "description": (
                        f"按{item.get('dimension')}拆解，该项较基线变化 "
                        f"{item.get('change_value')}；这是数值贡献，不等同于深层因果。"
                    ),
                    "status": status,
                    "impact_level": impact_level(item.get("change_rate")),
                    "confidence": confidence,
                    "evidence_ids": [item["evidence_id"]],
                    "verification_needed": verification_needed,
                }
            )

        risk_items = [item for item in evidence if item.get("kind") == "inventory_risk"]
        for item in risk_items[:5]:
            status, confidence, verification_needed = attribution_level(item, 0.9)
            append(
                {
                    "title": item["title"],
                    "description": (
                        f"依据库存和销量公式识别为{item['title'].split('：')[-1]}；"
                        "形成原因仍需结合采购、交付或活动数据验证。"
                    ),
                    "status": status,
                    "impact_level": (
                        "high" if item.get("severity") == "high" else "medium"
                    ),
                    "confidence": confidence,
                    "evidence_ids": [item["evidence_id"]],
                    "verification_needed": verification_needed,
                }
            )

        if not conclusions:
            evidence_ids = [str(item["evidence_id"]) for item in evidence[:3]]
            append(
                {
                    "title": "当前数据仅支持描述性判断",
                    "description": (
                        "已完成指标计算，但缺少可验证的基线变化或维度变化证据，"
                        "不能将相关性表述为经营原因。"
                    ),
                    "status": "to_verify",
                    "impact_level": "medium",
                    "confidence": 0.45,
                    "evidence_ids": evidence_ids,
                    "verification_needed": True,
                }
            )

        return {
            "attribution_candidates": conclusions,
            "current_step": "determine_attribution",
        }


def attribution_level(
    evidence: dict[str, Any],
    confirmed_confidence: float,
) -> tuple[str, float, bool]:
    if evidence.get("quality_status") == "verified":
        return "confirmed", confirmed_confidence, False
    return "probable", min(confirmed_confidence, 0.7), True


def impact_level(change_rate: object) -> str:
    rate = abs(float(change_rate or 0.0))
    if rate >= 0.2:
        return "high"
    if rate >= 0.05:
        return "medium"
    return "low"
