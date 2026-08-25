"""使用 Fake 服务离线验证整张图。

这些 Fake 不评价模型回答质量；它们让输入输出完全可预测，用来验证节点顺序、预算、
URL 去重、停止条件和引用渲染是否正确，而且不会消耗任何 API 额度。
"""

from collections.abc import Mapping, Sequence

from mini_research.config import ResearchConfig
from mini_research.graph import WorkflowDependencies, build_graph, initial_state
from mini_research.models import (
    Evidence,
    GapAssessment,
    ResearchBrief,
    ResearchState,
    SearchResult,
    SourceRecord,
)


class FakeBriefGenerator:
    def generate(self, topic: str) -> ResearchBrief:
        return ResearchBrief(
            topic=topic,
            objective=f"Research {topic}",
            subquestions=["What is the key technique?"],
            output_language="Chinese",
        )


class FakeQueryPlanner:
    def plan(self, state: ResearchState, *, max_queries: int) -> list[str]:
        return ["test query"][:max_queries]


class FakeSearchProvider:
    calls = 0

    def search(self, query: str, *, max_results: int) -> list[SearchResult]:
        self.calls += 1
        return [
            SearchResult(
                query=query,
                title="Primary source",
                url="https://example.com/paper?utm_source=search",
                content="The technique reduces latency.",
                score=0.9,
            ),
            SearchResult(
                query=query,
                title="Duplicate",
                url="https://example.com/paper#details",
                content="The technique reduces latency.",
                score=0.8,
            ),
        ][:max_results]


class FakeEvidenceExtractor:
    def extract(
        self,
        brief: ResearchBrief,
        source: SourceRecord,
        *,
        max_items: int,
    ) -> list[Evidence]:
        return [
            Evidence(
                source_id=source.source_id,
                claim="该技术能够降低延迟。",
                excerpt="The technique reduces latency.",
                relevance_score=0.95,
                quality_score=0.9,
            )
        ][:max_items]


class FakeGapAnalyzer:
    def analyze(
        self,
        brief: ResearchBrief,
        evidence: Sequence[Evidence],
        sources: Mapping[str, SourceRecord],
    ) -> GapAssessment:
        return GapAssessment(sufficient=True, gaps=[], rationale="Enough for fixture")


# TODO(next-step) [T1]: 新增一个“首轮不足、第二轮充分”的 FakeGapAnalyzer 与测试，
# 断言查询规划和搜索确实走了两轮，并且第二轮查询由 information_gaps 驱动。


class FakeReportWriter:
    def write(
        self,
        brief: ResearchBrief,
        evidence: Sequence[Evidence],
        sources: Mapping[str, SourceRecord],
    ) -> str:
        return "# 研究结果\n\n该技术能够降低延迟 [S1]。"


def test_full_graph_runs_offline_with_stable_verified_citation() -> None:
    # Arrange：组装与真实服务拥有相同接口的 Fake 依赖。
    search = FakeSearchProvider()
    dependencies = WorkflowDependencies(
        brief_generator=FakeBriefGenerator(),
        query_planner=FakeQueryPlanner(),
        search_provider=search,
        evidence_extractor=FakeEvidenceExtractor(),
        gap_analyzer=FakeGapAnalyzer(),
        report_writer=FakeReportWriter(),
    )
    config = ResearchConfig(
        max_rounds=2,
        max_searches=2,
        max_pages=3,
        min_sources=1,
        min_evidence=1,
    )

    # Act：执行的仍然是真实 LangGraph，只替换了图外部的模型和搜索服务。
    result = build_graph(dependencies, config).invoke(initial_state("测试主题", config))

    # Assert：检查编排结果，而不是检查一段随机模型文本。
    assert search.calls == 1
    assert list(result["sources"]) == ["S1"]
    assert result["stop_reason"] == "evidence_sufficient"
    assert result["citation_validation"].valid
    assert "[S1](https://example.com/paper?utm_source=search)" in result["final_report"]
    assert "## Sources" in result["final_report"]
