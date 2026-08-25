from mini_research.app import build_parser, print_invalid_draft, print_trace
from mini_research.config import ResearchConfig
from mini_research.graph import initial_state


def test_parser_budget_defaults_come_from_research_config() -> None:
    args = build_parser().parse_args(["测试主题"])
    defaults = ResearchConfig()

    assert args.max_rounds == defaults.max_rounds
    assert args.max_searches == defaults.max_searches
    assert args.max_pages == defaults.max_pages
    assert not args.show_draft_on_error


def test_parser_accepts_show_draft_on_error() -> None:
    args = build_parser().parse_args(["测试主题", "--show-draft-on-error"])
    assert args.show_draft_on_error


def test_print_trace_writes_diagnostics_to_stderr(capsys) -> None:
    state = initial_state("测试主题")
    state["trace"] = ["research brief generated"]
    state["stop_reason"] = "max_rounds_reached"

    print_trace(state)

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "research brief generated" in captured.err
    assert "stop_reason: max_rounds_reached" in captured.err


def test_print_invalid_draft_marks_it_as_unpublished(capsys) -> None:
    state = initial_state("测试主题")
    state["draft_report"] = "草稿使用了不被接受的引用 [S1, S2]。"

    print_invalid_draft(state)

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "debug only; not published" in captured.err
    assert "[S1, S2]" in captured.err
