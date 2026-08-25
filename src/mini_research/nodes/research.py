"""研究阶段的三个 LLM 适配器：查询规划、证据提取、信息缺口分析。

每个职责都先定义 ``Protocol``，再提供真实 LLM 实现。测试只要提供同样方法签名的 Fake，
就能验证整张图的编排，而无需真实联网。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from langchain_core.messages import HumanMessage

from mini_research.models import (
    Evidence,
    EvidenceBatch,
    GapAssessment,
    QueryPlan,
    ResearchBrief,
    ResearchState,
    SourceRecord,
)
from mini_research.prompts import EVIDENCE_PROMPT, GAP_PROMPT, QUERY_PROMPT


class QueryPlanner(Protocol):
    """为下一轮规划聚焦且不重复的搜索词。"""

    def plan(self, state: ResearchState, *, max_queries: int) -> list[str]: ...


class EvidenceExtractor(Protocol):
    """从一个已登记来源中抽取与研究问题相关的证据。"""

    def extract(
        self,
        brief: ResearchBrief,
        source: SourceRecord,
        *,
        max_items: int,
    ) -> list[Evidence]: ...


class GapAnalyzer(Protocol):
    """判断证据是否充分，并指出下一轮要补的信息。"""

    def analyze(
        self,
        brief: ResearchBrief,
        evidence: Sequence[Evidence],
        sources: Mapping[str, SourceRecord],
    ) -> GapAssessment: ...


class LLMQueryPlanner:
    """使用结构化输出生成下一轮查询。"""

    def __init__(self, model: Any) -> None:
        self._model = model.with_structured_output(QueryPlan)

    def plan(self, state: ResearchState, *, max_queries: int) -> list[str]:
        brief = state["research_brief"]
        if brief is None:
            raise ValueError("A research brief is required before query planning")
        prompt = QUERY_PROMPT.format(
            objective=brief.objective,
            subquestions="\n".join(f"- {item}" for item in brief.subquestions),
            gaps="\n".join(f"- {item}" for item in state["information_gaps"]) or "None yet",
            searched_queries="\n".join(f"- {item}" for item in state["searched_queries"]) or "None",
            max_queries=max_queries,
        )
        response: QueryPlan = self._model.invoke([HumanMessage(content=prompt)])
        # 即使模型返回过多查询，也在程序侧再次截断，预算不能只依赖 Prompt。
        return response.queries[:max_queries]


class LLMEvidenceExtractor:
    """从网页提取短证据，而不是生成难以校验的整页长摘要。"""

    def __init__(self, model: Any) -> None:
        self._model = model.with_structured_output(EvidenceBatch)

    def extract(
        self,
        brief: ResearchBrief,
        source: SourceRecord,
        *,
        max_items: int,
    ) -> list[Evidence]:
        prompt = EVIDENCE_PROMPT.format(
            objective=brief.objective,
            subquestions="\n".join(f"- {item}" for item in brief.subquestions),
            title=source.title,
            source_id=source.source_id,
            content=source.content,
            max_items=max_items,
        )
        response: EvidenceBatch = self._model.invoke([HumanMessage(content=prompt)])
        # 信任边界：source_id 来自程序当前正在处理的 SourceRecord，模型无权指定它。
        # TODO(next-step) [G1]: 在规范化网页正文中机械查找 excerpt，并保存字符位置或
        # hash；找不到原文的摘录应被拒绝，不能只相信结构化模型输出。
        return [
            Evidence(source_id=source.source_id, **item.model_dump())
            for item in response.items[:max_items]
        ]


class LLMGapAnalyzer:
    """识别信息缺口，用它驱动下一轮而不是盲目重复搜索。"""

    def __init__(self, model: Any) -> None:
        self._model = model.with_structured_output(GapAssessment)

    def analyze(
        self,
        brief: ResearchBrief,
        evidence: Sequence[Evidence],
        sources: Mapping[str, SourceRecord],
    ) -> GapAssessment:
        # sources 当前没有直接进入 Prompt；保留该参数是为了下一阶段加入来源类型、
        # 独立性和可信度策略，而不需要改变接口。
        evidence_text = (
            "\n".join(
                f"- [{item.source_id}] {item.claim} | excerpt: {item.excerpt}" for item in evidence
            )
            or "No usable evidence has been collected."
        )
        prompt = GAP_PROMPT.format(
            objective=brief.objective,
            subquestions="\n".join(f"- {item}" for item in brief.subquestions),
            evidence=evidence_text,
        )
        return self._model.invoke([HumanMessage(content=prompt)])
