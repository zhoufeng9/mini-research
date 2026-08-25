"""项目配置。

这里刻意只定义“数据”，不在导入模块时读取 ``.env`` 或创建网络客户端。这样做有两个
好处：离线测试不需要 API Key；工作流依赖也能在应用入口处清楚地组装。
"""

from __future__ import annotations

import os

from pydantic import BaseModel, ConfigDict, Field, SecretStr


class ResearchConfig(BaseModel):
    """一次研究任务的硬预算与最低质量门槛。

    所有预算都由 Python 代码强制执行，而不只是写在 Prompt 里。模型可能不遵守“少搜
    几次”这样的自然语言要求，代码预算才是控制费用和运行时间的可靠边界。
    """

    # frozen=True 防止工作流运行到一半时预算被意外修改。
    model_config = ConfigDict(frozen=True)

    # 初学阶段先使用偏小的默认预算；需要更深入时可通过 CLI 覆盖。
    max_rounds: int = Field(default=2, ge=1)
    max_searches: int = Field(default=3, ge=1)  # 失败的搜索尝试也会计数。
    max_pages: int = Field(default=6, ge=1)  # 实际限制任务内登记的唯一来源数量。
    max_queries_per_round: int = Field(default=2, ge=1)
    max_results_per_query: int = Field(default=2, ge=1)
    max_evidence_per_source: int = Field(default=3, ge=1)
    min_sources: int = Field(default=2, ge=1)
    min_evidence: int = Field(default=3, ge=1)
    min_relevance_score: float = Field(default=0.55, ge=0.0, le=1.0)


class Settings(BaseModel):
    """由应用入口加载的外部服务配置。

    ``SecretStr`` 会避免 Pydantic 在日志或异常中直接展示搜索密钥，但它不能替代正确的
    密钥管理：真实值仍然只能放在被 Git 忽略的 ``.env`` 中。
    """

    model_config = ConfigDict(frozen=True)

    model: str = "openai:gpt-4.1-mini"
    tavily_api_key: SecretStr
    max_content_chars: int = Field(default=12_000, ge=1_000)

    @classmethod
    def from_env(cls) -> Settings:
        """从环境变量构造配置，并在缺少必填项时给出清楚的错误。"""

        tavily_api_key = os.getenv("TAVILY_API_KEY")
        if not tavily_api_key:
            raise ValueError("TAVILY_API_KEY is required. Copy .env.example to .env first.")

        model = os.getenv("MINI_RESEARCH_MODEL", "openai:gpt-4.1-mini")
        if model.startswith("openai:") and not os.getenv("OPENAI_API_KEY"):
            raise ValueError("OPENAI_API_KEY is required for an OpenAI model.")

        return cls(
            model=model,
            tavily_api_key=SecretStr(tavily_api_key),
            max_content_chars=int(os.getenv("MAX_CONTENT_CHARS", "12000")),
        )
