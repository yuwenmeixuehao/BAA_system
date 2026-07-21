import html
import json
from dataclasses import dataclass
from typing import Any

from app.agent.storage.workspace import WorkspaceStorage
from app.schemas.report import GeneratedFile, ReportIR

HTML_STYLE = """
body { margin: 0; background: #f4f7fb; color: #182238;
  font-family: Inter, 'Microsoft YaHei', sans-serif; }
main { max-width: 1180px; margin: auto; padding: 32px; }
header, section { margin-bottom: 22px; padding: 24px; background: #fff;
  border: 1px solid #dfe6f0; border-radius: 14px; }
h1 { margin: 0 0 10px; }
h2 { font-size: 18px; }
.metrics { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 12px; }
.metric-card { padding: 16px; background: #f7f9ff; border-radius: 10px; }
.metric-card span, .metric-card small { display: block; color: #68758c; }
.metric-card strong { display: block; margin: 8px 0; font-size: 24px; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th, td { padding: 9px; border-bottom: 1px solid #e7ebf1; text-align: left; }
.conclusion { padding: 12px 0; border-bottom: 1px solid #edf0f4; }
.chart { height: 380px; }
small { color: #68758c; }
@media (max-width: 640px) {
  main { padding: 12px; }
  header, section { padding: 16px; }
}
"""

ECHARTS_SCRIPT = """
const charts = __CHART_DATA__;
for (const chart of charts) {
  const el = document.getElementById(chart.chart_id);
  if (!el || !window.echarts) continue;
  const instance = echarts.init(el);
  let series;
  if (chart.type === 'pie') {
    series = [{
      type: 'pie',
      data: chart.categories.map((name, index) => ({
        name,
        value: chart.series[0].data[index]
      }))
    }];
  } else {
    series = chart.series.map((item) => ({
      name: item.name,
      type: chart.type === 'line' ? 'line' : 'bar',
      stack: chart.type === 'stackedBar' ? 'total' : undefined,
      data: item.data
    }));
  }
  instance.setOption({
    tooltip: { trigger: 'axis' },
    legend: {},
    xAxis: chart.type === 'pie' ? undefined : {
      type: 'category', data: chart.categories
    },
    yAxis: chart.type === 'pie' ? undefined : { type: 'value' },
    series
  });
  window.addEventListener('resize', () => instance.resize());
}
"""


@dataclass(frozen=True)
class RenderedReport:
    report_ir: dict[str, Any]
    generated_files: list[dict[str, Any]]
    markdown: str
    html: str


class ReportRenderer:
    def __init__(self, workspace: WorkspaceStorage) -> None:
        self.workspace = workspace

    def render(self, report: ReportIR) -> RenderedReport:
        markdown = render_markdown(report)
        html_content = render_html(report)
        prefix = f"tasks/{report.task_id}/reports"
        html_key = f"{prefix}/report.html"
        markdown_key = f"{prefix}/report.md"
        json_key = f"{prefix}/report_ir.json"
        html_size, html_sha = self.workspace.write_text(html_key, html_content)
        markdown_size, markdown_sha = self.workspace.write_text(markdown_key, markdown)
        published_files = [
            generated_file("html", "经营归因分析报告.html", html_key, html_size, html_sha),
            generated_file("md", "经营归因分析报告.md", markdown_key, markdown_size, markdown_sha),
        ]
        report.generated_files = [GeneratedFile.model_validate(item) for item in published_files]
        report_payload = report.model_dump(mode="json")
        json_size, json_sha = self.workspace.write_json(json_key, report_payload)
        generated_files = [
            *published_files,
            generated_file("json", "Report IR.json", json_key, json_size, json_sha),
        ]
        return RenderedReport(
            report_ir=report_payload,
            generated_files=generated_files,
            markdown=markdown,
            html=html_content,
        )


def generated_file(
    file_type: str,
    file_name: str,
    storage_key: str,
    file_size: int,
    sha256: str,
) -> dict[str, Any]:
    return {
        "file_type": file_type,
        "file_name": file_name,
        "storage_key": storage_key,
        "file_size": file_size,
        "sha256": sha256,
    }


def render_markdown(report: ReportIR) -> str:
    metrics = "\n".join(
        (
            f"- **{item.label}**：{format_number(item.value)}"
            f"{format_unit(item.unit)}（公式：`{item.formula}`）"
        )
        for item in report.key_metrics
    )
    evidence = "\n".join(
        f"- `{item.evidence_id}` {item.title}：{item.description}"
        for item in report.evidence_list
    )
    conclusions = "\n".join(
        (
            f"- **{item.title}** [{item.status}/{item.impact_level}]："
            f"{item.description}（证据：{', '.join(item.evidence_ids) or '无'}）"
        )
        for item in report.attribution_conclusions
    )
    missing = "\n".join(
        f"- {item.reason}；影响：{item.impact}；处理：{item.required_action}"
        for item in report.missing_data
    ) or "- 无已识别的数据缺口"
    actions = "\n".join(
        f"- **{item.title}**（{item.priority}）：{item.description}"
        for item in report.next_actions
    )
    return (
        "# 经营归因分析报告\n\n"
        "## 1. 问题定义\n\n"
        f"- 原问题：{report.problem_definition.question}\n"
        f"- 范围：{report.problem_definition.scope}\n"
        f"- 指标：{report.problem_definition.metric}\n"
        f"- 基线：{report.problem_definition.baseline}\n"
        f"- 场景：{report.problem_definition.scenario}\n\n"
        f"## 2. 关键指标\n\n{metrics}\n\n"
        f"## 3. 证据列表\n\n{evidence}\n\n"
        f"## 4. 归因结论\n\n{conclusions}\n\n"
        f"## 5. 待补充数据\n\n{missing}\n\n"
        f"## 6. 下一步建议\n\n{actions}\n"
    )


def render_html(report: ReportIR) -> str:
    report_data = report.model_dump(mode="json")
    chart_data = json.dumps(
        [item for item in report_data["visualizations"] if item["type"] != "table"],
        ensure_ascii=False,
        allow_nan=False,
    ).replace("<", "\\u003c")
    metric_cards = "".join(
        "<article class='metric-card'>"
        f"<span>{escape(item.label)}</span>"
        f"<strong>{escape(format_number(item.value))}{escape(format_unit(item.unit))}</strong>"
        f"<small>{escape(item.scope)} · {escape(item.formula)}</small>"
        "</article>"
        for item in report.key_metrics
    )
    evidence_rows = "".join(
        "<tr>"
        f"<td>{escape(item.evidence_id)}</td><td>{escape(item.title)}</td>"
        f"<td>{escape(item.description)}</td><td>{escape(item.quality_status)}</td>"
        "</tr>"
        for item in report.evidence_list
    )
    conclusion_cards = "".join(
        "<article class='conclusion'>"
        f"<h3>{escape(item.title)}</h3><p>{escape(item.description)}</p>"
        f"<small>{escape(item.status)} · {escape(item.impact_level)} · "
        f"confidence {item.confidence:.2f} · evidence "
        f"{escape(', '.join(item.evidence_ids) or 'none')}</small></article>"
        for item in report.attribution_conclusions
    )
    missing_items = "".join(
        f"<li>{escape(item.reason)}；{escape(item.required_action)}</li>"
        for item in report.missing_data
    ) or "<li>无已识别的数据缺口</li>"
    action_items = "".join(
        f"<li><strong>{escape(item.title)}</strong>：{escape(item.description)}</li>"
        for item in report.next_actions
    )
    chart_nodes = "".join(
        f"<section><h2>{escape(item.title)}</h2><div id='{escape(item.chart_id)}' "
        "class='chart'></div></section>"
        for item in report.visualizations
        if item.type != "table"
    )
    table_nodes = "".join(
        render_table(item.model_dump(mode="json"))
        for item in report.visualizations
        if item.type == "table"
    )
    script = ECHARTS_SCRIPT.replace("__CHART_DATA__", chart_data)
    problem = report.problem_definition
    return "\n".join(
        [
            "<!doctype html>",
            '<html lang="zh-CN"><head><meta charset="utf-8">',
            '<meta name="viewport" content="width=device-width,initial-scale=1">',
            "<title>经营归因分析报告</title>",
            '<script src="https://cdn.jsdelivr.net/npm/echarts@6.1.0/dist/echarts.min.js"></script>',
            f"<style>{HTML_STYLE}</style></head><body><main>",
            "<header><h1>经营归因分析报告</h1>",
            f"<p>{escape(problem.question)}</p>",
            f"<small>{escape(problem.scope)} · {escape(problem.scenario)}</small></header>",
            "<section><h2>1. 问题定义</h2>",
            f"<p>指标：{escape(problem.metric)}；基线：{escape(problem.baseline)}</p>",
            "</section>",
            f'<section><h2>2. 关键指标</h2><div class="metrics">{metric_cards}</div></section>',
            "<section><h2>3. 证据列表</h2><table><thead><tr>",
            "<th>ID</th><th>证据</th><th>说明</th><th>质量</th>",
            f"</tr></thead><tbody>{evidence_rows}</tbody></table></section>",
            f"<section><h2>4. 归因结论</h2>{conclusion_cards}</section>",
            f"<section><h2>5. 待补充数据</h2><ul>{missing_items}</ul></section>",
            f"<section><h2>6. 下一步建议</h2><ol>{action_items}</ol></section>",
            chart_nodes,
            table_nodes,
            f"</main><script>{script}</script></body></html>",
        ]
    )


def render_table(item: dict[str, Any]) -> str:
    columns = item.get("columns", [])
    headers = "".join(f"<th>{escape(column)}</th>" for column in columns)
    rows = "".join(
        "<tr>" + "".join(f"<td>{escape(row.get(column))}</td>" for column in columns) + "</tr>"
        for row in item.get("rows", [])
    )
    return (
        f"<section><h2>{escape(item.get('title'))}</h2><table><thead><tr>"
        f"{headers}</tr></thead><tbody>{rows}</tbody></table></section>"
    )


def escape(value: object) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def format_number(value: float) -> str:
    return f"{value:,.4f}".rstrip("0").rstrip(".")


def format_unit(unit: str | None) -> str:
    return {
        "currency": " 元",
        "count": "",
        "ratio": "",
        "day": " 天",
        "item": " 个",
    }.get(unit or "", f" {unit}" if unit else "")
