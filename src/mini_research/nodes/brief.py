"""研究 Brief 生成节点所需的接口与真实实现。"""

from __future__ import annotations

from datetime import date
from typing import Any, Protocol

from langchain_core.messages import HumanMessage

from mini_research.models import ResearchBrief
from mini_research.prompts import BRIEF_PROMPT


class BriefGenerator(Protocol):
    """把主题转换成结构化 Brief 的接口契约。

    工作流只依赖这个接口，不关心背后是真实 LLM 还是离线 Fake。
    """

    def generate(self, topic: str) -> ResearchBrief: ...


class LLMBriefGenerator:
    """使用 LLM 结构化输出生成 Brief。"""

    def __init__(self, model: Any, *, today: str | None = None) -> None:
        # with_structured_output 会把自由文本模型包装成返回 ResearchBrief 的调用器。
        self._model = model.with_structured_output(ResearchBrief)
        # 日期允许从外部注入，使涉及“最新”的测试可以固定时间、保持可复现。
        self._today = today or date.today().isoformat()

    def generate(self, topic: str) -> ResearchBrief:
        prompt = BRIEF_PROMPT.format(topic=topic, date=self._today)
        return self._model.invoke([HumanMessage(content=prompt)])
