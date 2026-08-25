"""根据已接受证据生成最终报告草稿。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from langchain_core.messages import HumanMessage

from mini_research.models import Evidence, ResearchBrief, SourceRecord
from mini_research.prompts import REPORT_PROMPT


class ReportWriter(Protocol):
    """只允许引用已登记来源 ID 的写作接口。"""

    def write(
        self,
        brief: ResearchBrief,
        evidence: Sequence[Evidence],
        sources: Mapping[str, SourceRecord],
    ) -> str: ...


class LLMReportWriter:
    """LLM 负责组织文字；URL 渲染继续交给确定性代码。"""

    def __init__(self, model: Any) -> None:
        self._model = model

    def write(
        self,
        brief: ResearchBrief,
        evidence: Sequence[Evidence],
        sources: Mapping[str, SourceRecord],
    ) -> str:
        # relevance × quality 是首版的简单排序规则，不代表严格的来源可信度模型。
        ranked = sorted(
            evidence,
            key=lambda item: item.relevance_score * item.quality_score,
            reverse=True,
        )
        evidence_text = "\n".join(
            f"- [{item.source_id}] {item.claim}\n  Supporting excerpt: {item.excerpt}"
            for item in ranked
        )
        # sources 参数暂不直接传给模型，防止 Writer 绕过证据自行使用网页内容；它为后续
        # 在报告中展示来源类型、发布日期等安全元数据保留接口位置。
        prompt = REPORT_PROMPT.format(
            objective=brief.objective,
            subquestions="\n".join(f"- {item}" for item in brief.subquestions),
            output_language=brief.output_language,
            evidence=evidence_text,
        )
        response = self._model.invoke([HumanMessage(content=prompt)])
        # 这里只返回含 [S1] 的草稿；graph.py 的最后节点验证通过后才会变成可发布报告。
        return str(response.content)
