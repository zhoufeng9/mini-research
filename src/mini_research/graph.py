"""单 Agent 的 Scope → Research → Write → Validate 工作流。

LangGraph 节点接收完整 ``state``，但只返回本节点修改的字段。当前列表和字典字段没有
reducer，所以需要先复制旧值再显式累加。``build_graph`` 通过闭包持有不可变预算和
依赖，这些运行参数不需要混进业务状态。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from langgraph.graph import END, START, StateGraph

from mini_research.citations import render_report, validate_citations
from mini_research.config import ResearchConfig
from mini_research.models import GapAssessment, ResearchState
from mini_research.nodes import (
    BriefGenerator,
    EvidenceExtractor,
    GapAnalyzer,
    QueryPlanner,
    ReportWriter,
)
from mini_research.tools import SearchProvider, register_search_results


@dataclass(frozen=True)
class WorkflowDependencies:
    """工作流节点使用的可替换服务集合。

    CLI 注入真实 LLM/Tavily；测试注入内存 Fake。这种依赖注入让我们验证“图是否走对”，
    而不会把模型随机性和网络问题混入单元测试。
    """

    brief_generator: BriefGenerator
    query_planner: QueryPlanner
    search_provider: SearchProvider
    evidence_extractor: EvidenceExtractor
    gap_analyzer: GapAnalyzer
    report_writer: ReportWriter


def initial_state(topic: str, config: ResearchConfig | None = None) -> ResearchState:
    """为一次任务创建全新状态，避免共享可变默认值。"""

    normalized_topic = " ".join(topic.split())
    if not normalized_topic:
        raise ValueError("Research topic must not be empty.")

    # 配置由 build_graph 的闭包持有，不存入 state。保留该参数只是让调用形式直观；
    # 后续若引入每次调用不同的运行时配置，可再把它正式放入 state/context。
    del config  # The compiled graph owns its immutable hard-budget configuration.
    return {
        "topic": normalized_topic,
        "research_brief": None,
        "current_queries": [],
        "searched_queries": [],
        "pending_source_ids": [],
        "sources": {},
        "evidence": [],
        "information_gaps": [],
        "gap_assessment": None,
        "round_count": 0,
        "search_count": 0,
        "pages_processed": 0,
        "errors": [],
        "trace": [],
        "stop_reason": None,
        "draft_report": "",
        "citation_validation": None,
        "final_report": "",
    }


def determine_stop_reason(state: ResearchState, config: ResearchConfig) -> str | None:
    """按固定优先级返回第一个研究停止原因。"""

    # 判断顺序就是优先级：已记录原因和“证据充分”优先于各类预算耗尽。
    if state["stop_reason"]:
        return state["stop_reason"]
    if state["gap_assessment"] and state["gap_assessment"].sufficient:
        return "evidence_sufficient"
    if state["round_count"] >= config.max_rounds:
        return "max_rounds_reached"
    if state["search_count"] >= config.max_searches:
        return "max_searches_reached"
    if state["pages_processed"] >= config.max_pages:
        return "max_pages_reached"
    return None


def decide_next(
    state: ResearchState,
    config: ResearchConfig,
) -> Literal["plan_queries", "write_report"]:
    """决定继续搜索还是进入写作；纯函数因此可以独立单测。"""

    return "write_report" if determine_stop_reason(state, config) else "plan_queries"


def build_graph(dependencies: WorkflowDependencies, config: ResearchConfig):
    """构建由代码强制预算的单研究员状态图。"""

    def build_brief(state: ResearchState) -> dict:
        brief = dependencies.brief_generator.generate(state["topic"])
        return {
            "research_brief": brief,
            "trace": state["trace"] + ["research brief generated"],
        }

    def plan_queries(state: ResearchState) -> dict:
        # 先计算剩余搜索预算，再把本轮最多查询数压到这个范围内。
        remaining = config.max_searches - state["search_count"]
        max_queries = min(config.max_queries_per_round, remaining)
        if max_queries <= 0:
            return {"current_queries": [], "stop_reason": "max_searches_reached"}

        errors = list(state["errors"])
        try:
            proposed = dependencies.query_planner.plan(state, max_queries=max_queries)
        except Exception as exc:  # Keep a partial research task alive where possible.
            errors.append(f"query planning failed: {exc}")
            # 首轮规划失败时，至少尝试直接搜索原主题；后续轮失败则安全停止。
            proposed = [state["topic"]] if not state["searched_queries"] else []

        # 程序侧再次清洗空白、历史重复和本轮重复，不能只相信模型遵守 Prompt。
        already_used = {query.casefold() for query in state["searched_queries"]}
        queries: list[str] = []
        for query in proposed:
            normalized = " ".join(query.split())
            if not normalized or normalized.casefold() in already_used:
                continue
            if normalized.casefold() in {item.casefold() for item in queries}:
                continue
            queries.append(normalized)
            if len(queries) >= max_queries:
                break

        stop_reason = state["stop_reason"]
        if not queries:
            stop_reason = "no_new_queries"
        return {
            "current_queries": queries,
            "errors": errors,
            "stop_reason": stop_reason,
            "trace": state["trace"] + [f"planned {len(queries)} query/queries"],
        }

    def route_after_plan(state: ResearchState) -> Literal["search_web", "write_report"]:
        if state["current_queries"] and not state["stop_reason"]:
            return "search_web"
        return "write_report"

    def search_web(state: ResearchState) -> dict:
        sources = dict(state["sources"])
        new_ids: list[str] = []
        errors = list(state["errors"])
        search_count = state["search_count"]
        searched_queries = list(state["searched_queries"])

        for query in state["current_queries"]:
            if search_count >= config.max_searches or len(sources) >= config.max_pages:
                break
            remaining_pages = config.max_pages - len(sources)
            max_results = min(config.max_results_per_query, remaining_pages)
            try:
                results = dependencies.search_provider.search(query, max_results=max_results)
                sources, registered = register_search_results(
                    sources,
                    results,
                    max_new_sources=remaining_pages,
                )
                new_ids.extend(registered)
            except Exception as exc:
                # 具体重试策略属于 SearchProvider 适配器；图只记录可解释的失败。
                errors.append(f"search failed for {query!r}: {exc}")
            finally:
                # 失败的调用也消耗搜索预算，否则持续故障可能形成无限循环。
                search_count += 1
                searched_queries.append(query)

        return {
            "sources": sources,
            "pending_source_ids": new_ids,
            "searched_queries": searched_queries,
            "current_queries": [],
            "search_count": search_count,
            "round_count": state["round_count"] + 1,
            "pages_processed": len(sources),
            "errors": errors,
            "trace": state["trace"] + [f"registered {len(new_ids)} new source(s)"],
        }

    def extract_evidence(state: ResearchState) -> dict:
        brief = state["research_brief"]
        if brief is None:
            raise ValueError("A research brief is required before evidence extraction")

        evidence = list(state["evidence"])
        errors = list(state["errors"])
        known = {(item.source_id, item.claim.casefold()) for item in evidence}
        accepted = 0
        for source_id in state["pending_source_ids"]:
            source = state["sources"][source_id]
            try:
                extracted = dependencies.evidence_extractor.extract(
                    brief,
                    source,
                    max_items=config.max_evidence_per_source,
                )
                for item in extracted:
                    # 再次用当前 source_id 覆盖返回值：来源归属由程序决定，不信任适配器
                    # 或模型自行声明的 ID。
                    item = item.model_copy(update={"source_id": source_id})
                    key = (source_id, item.claim.casefold())
                    if item.relevance_score < config.min_relevance_score or key in known:
                        continue
                    evidence.append(item)
                    known.add(key)
                    accepted += 1
            except Exception as exc:
                errors.append(f"evidence extraction failed for {source_id}: {exc}")

        return {
            "evidence": evidence,
            "pending_source_ids": [],
            "errors": errors,
            "trace": state["trace"] + [f"accepted {accepted} evidence item(s)"],
        }

    def analyze_gaps(state: ResearchState) -> dict:
        brief = state["research_brief"]
        if brief is None:
            raise ValueError("A research brief is required before gap analysis")

        errors = list(state["errors"])
        try:
            assessment = dependencies.gap_analyzer.analyze(
                brief,
                state["evidence"],
                state["sources"],
            )
        except Exception as exc:
            errors.append(f"gap analysis failed: {exc}")
            assessment = GapAssessment(
                sufficient=False,
                gaps=["Gap analysis failed; continue only while hard budget remains."],
                rationale=str(exc),
            )

        # LLM 说 sufficient 仍不能绕过代码设定的最低独立来源数和证据数。
        cited_source_count = len({item.source_id for item in state["evidence"]})
        minimums_met = (
            cited_source_count >= config.min_sources
            and len(state["evidence"]) >= config.min_evidence
        )
        if assessment.sufficient and not minimums_met:
            assessment = assessment.model_copy(
                update={
                    "sufficient": False,
                    "gaps": assessment.gaps
                    + ["Collect more independent sources/evidence to meet the configured minimum."],
                }
            )

        # state 里还是上一轮 assessment；先构造候选状态，才能用本轮新结果判断停止。
        candidate = dict(state)
        candidate["gap_assessment"] = assessment
        stop_reason = determine_stop_reason(candidate, config)
        return {
            "gap_assessment": assessment,
            "information_gaps": assessment.gaps,
            "stop_reason": stop_reason,
            "errors": errors,
            "trace": state["trace"] + [f"gap assessment: sufficient={assessment.sufficient}"],
        }

    def write_report(state: ResearchState) -> dict:
        brief = state["research_brief"]
        if brief is None:
            raise ValueError("A research brief is required before report writing")
        if not state["evidence"]:
            # 没证据时采用 fail closed：生成说明性草稿，但它没有引用，下一节点不会把它
            # 发布为 final_report。
            draft = "# Research incomplete\n\nNo verifiable evidence was collected."
        else:
            draft = dependencies.report_writer.write(
                brief,
                state["evidence"],
                state["sources"],
            )
        return {
            "draft_report": draft,
            "stop_reason": state["stop_reason"] or "report_requested",
            "trace": state["trace"] + ["draft report generated"],
        }

    def validate_and_render(state: ResearchState) -> dict:
        validation = validate_citations(state["draft_report"], state["sources"])
        errors = list(state["errors"])
        final_report = ""
        if validation.valid:
            final_report = render_report(state["draft_report"], state["sources"])
        else:
            errors.extend(f"citation validation: {message}" for message in validation.messages)
            # TODO(next-step) [C1]: 增加最多一次的受限修复，只向模型提供合法来源 ID；
            # 再次失败仍保持 final_report 为空，绝不静默发布未校验草稿。
        return {
            "citation_validation": validation,
            "final_report": final_report,
            "errors": errors,
            "trace": state["trace"] + [f"citation validation: valid={validation.valid}"],
        }

    builder = StateGraph(ResearchState)
    builder.add_node("build_brief", build_brief)
    builder.add_node("plan_queries", plan_queries)
    builder.add_node("search_web", search_web)
    builder.add_node("extract_evidence", extract_evidence)
    builder.add_node("analyze_gaps", analyze_gaps)
    builder.add_node("write_report", write_report)
    builder.add_node("validate_citations", validate_and_render)

    # 直线边：确定会按顺序执行。
    builder.add_edge(START, "build_brief")
    builder.add_edge("build_brief", "plan_queries")
    # 条件边：没有新查询或预算已尽时，直接进入写作。
    builder.add_conditional_edges(
        "plan_queries",
        route_after_plan,
        {"search_web": "search_web", "write_report": "write_report"},
    )
    builder.add_edge("search_web", "extract_evidence")
    builder.add_edge("extract_evidence", "analyze_gaps")
    # 循环边：证据仍不足且有预算时，从缺口分析回到查询规划。
    builder.add_conditional_edges(
        "analyze_gaps",
        lambda state: decide_next(state, config),
        {"plan_queries": "plan_queries", "write_report": "write_report"},
    )
    builder.add_edge("write_report", "validate_citations")
    # 只有引用校验与渲染结束后，整张图才完成。
    builder.add_edge("validate_citations", END)
    return builder.compile()
