import pytest

from mini_research.config import ResearchConfig
from mini_research.graph import decide_next, initial_state
from mini_research.models import GapAssessment


def test_initial_state_normalizes_topic_and_rejects_blank_input() -> None:
    state = initial_state("  大模型   推理优化  ")
    assert state["topic"] == "大模型 推理优化"

    with pytest.raises(ValueError, match="must not be empty"):
        initial_state("   \n\t")


def test_budget_is_a_hard_stop() -> None:
    config = ResearchConfig(max_searches=1)
    state = initial_state("topic", config)
    state["search_count"] = 1
    assert decide_next(state, config) == "write_report"


def test_sufficient_evidence_stops_before_budget_is_exhausted() -> None:
    config = ResearchConfig()
    state = initial_state("topic", config)
    state["gap_assessment"] = GapAssessment(sufficient=True)
    assert decide_next(state, config) == "write_report"


def test_missing_evidence_with_budget_continues() -> None:
    config = ResearchConfig()
    state = initial_state("topic", config)
    state["gap_assessment"] = GapAssessment(sufficient=False, gaps=["missing fact"])
    assert decide_next(state, config) == "plan_queries"
