from mini_research.app import build_parser, print_trace
from mini_research.config import ResearchConfig
from mini_research.graph import initial_state


def test_parser_budget_defaults_come_from_research_config() -> None:
    args = build_parser().parse_args(["测试主题"])
    defaults = ResearchConfig()

    assert args.max_rounds == defaults.max_rounds
    assert args.max_searches == defaults.max_searches
    assert args.max_pages == defaults.max_pages


def test_print_trace_writes_diagnostics_to_stderr(capsys) -> None:
    state = initial_state("测试主题")
    state["trace"] = ["research brief generated"]
    state["stop_reason"] = "max_rounds_reached"

    print_trace(state)

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "research brief generated" in captured.err
    assert "stop_reason: max_rounds_reached" in captured.err
