"""应用组装入口和命令行界面。

这个文件是“纯业务代码”和“真实外部服务”的分界线：只有真正运行 CLI 时，才读取
``.env``、创建模型和 Tavily 客户端。测试可以绕开这些真实依赖，完全离线运行。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv
from langchain.chat_models import init_chat_model

from mini_research.config import ResearchConfig, Settings
from mini_research.graph import WorkflowDependencies, build_graph, initial_state
from mini_research.models import ResearchState
from mini_research.nodes import (
    LLMBriefGenerator,
    LLMEvidenceExtractor,
    LLMGapAnalyzer,
    LLMQueryPlanner,
    LLMReportWriter,
)
from mini_research.tools import TavilySearchProvider


def create_default_dependencies(settings: Settings) -> WorkflowDependencies:
    """在 CLI 启动时创建真实依赖。

    ``WorkflowDependencies`` 看起来多了一层包装，但它让我们可以在测试中把模型与搜索
    服务替换成 Fake，而不需要联网或消耗额度。
    """

    model = init_chat_model(model=settings.model, temperature=0)
    return WorkflowDependencies(
        brief_generator=LLMBriefGenerator(model),
        query_planner=LLMQueryPlanner(model),
        search_provider=TavilySearchProvider(
            api_key=settings.tavily_api_key.get_secret_value(),
            max_content_chars=settings.max_content_chars,
        ),
        evidence_extractor=LLMEvidenceExtractor(model),
        gap_analyzer=LLMGapAnalyzer(model),
        report_writer=LLMReportWriter(model),
    )


def run_research(
    topic: str,
    *,
    settings: Settings,
    config: ResearchConfig | None = None,
) -> ResearchState:
    """运行一次研究任务，并返回可检查的完整状态。"""

    research_config = config or ResearchConfig()
    graph = build_graph(create_default_dependencies(settings), research_config)
    return graph.invoke(initial_state(topic, research_config))


def build_parser() -> argparse.ArgumentParser:
    """定义 CLI 参数。

    默认值直接来自 ``ResearchConfig``，避免配置类和命令行各维护一套数字。
    """

    defaults = ResearchConfig()
    parser = argparse.ArgumentParser(description="Run the mini web research assistant.")
    parser.add_argument("topic", help="Topic or research question")
    parser.add_argument("--output", type=Path, help="Optional Markdown output path")
    parser.add_argument("--max-rounds", type=int, default=defaults.max_rounds)
    parser.add_argument("--max-searches", type=int, default=defaults.max_searches)
    parser.add_argument("--max-pages", type=int, default=defaults.max_pages)
    parser.add_argument(
        "--show-trace",
        action="store_true",
        help="Print the workflow trace to stderr after the report finishes",
    )
    parser.add_argument(
        "--show-draft-on-error",
        action="store_true",
        help="Print an invalid, unpublished draft to stderr for citation debugging",
    )
    return parser


def print_trace(result: ResearchState) -> None:
    """把图执行轨迹打印到 stderr，帮助初学者观察每一步发生了什么。"""

    print("\nWorkflow trace:", file=sys.stderr)
    for index, event in enumerate(result["trace"], start=1):
        print(f"  {index}. {event}", file=sys.stderr)
    print(f"  stop_reason: {result['stop_reason']}", file=sys.stderr)
    print(
        "  totals: "
        f"{result['search_count']} search(es), "
        f"{len(result['sources'])} source(s), "
        f"{len(result['evidence'])} evidence item(s)",
        file=sys.stderr,
    )


def print_invalid_draft(result: ResearchState) -> None:
    """打印未通过引用校验的草稿，并明确标记它不是最终报告。

    默认不显示失败草稿，避免用户误把它当成已经验证的结果。只有显式传入
    ``--show-draft-on-error`` 时，CLI 才调用这个调试函数。
    """

    draft = result["draft_report"].strip()
    if not draft:
        return

    print("\n--- Invalid draft (debug only; not published) ---", file=sys.stderr)
    print(draft, file=sys.stderr)
    print("--- End invalid draft ---", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    """CLI 入口：解析参数、加载配置、运行工作流并输出报告。"""

    args = build_parser().parse_args(argv)
    load_dotenv()
    try:
        settings = Settings.from_env()
        config = ResearchConfig(
            max_rounds=args.max_rounds,
            max_searches=args.max_searches,
            max_pages=args.max_pages,
        )
        result = run_research(args.topic, settings=settings, config=config)
    except Exception as exc:
        print(f"mini-research failed: {exc}", file=sys.stderr)
        return 1

    if args.show_trace:
        # 轨迹写入 stderr，因此不会污染 stdout 中可重定向保存的 Markdown 报告。
        print_trace(result)

    validation = result["citation_validation"]
    if validation is None or not validation.valid:
        print("Research completed, but citation validation failed.", file=sys.stderr)
        for error in result["errors"]:
            print(f"- {error}", file=sys.stderr)
        if args.show_draft_on_error:
            print_invalid_draft(result)
        return 2

    report = result["final_report"]
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report, encoding="utf-8")
        print(f"Report written to {args.output}")
    else:
        print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
