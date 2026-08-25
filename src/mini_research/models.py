"""工作流节点共享的数据模型。

可以把本文件理解为整个项目的“数据合同”：

- ``BaseModel`` 描述某一步模型调用的结构化输入/输出；
- ``ResearchState`` 描述 LangGraph 从头到尾传递的完整状态；
- 来源、证据不使用大段拼接字符串，而是保持结构化，方便后续去重、筛选和校验。
"""

from __future__ import annotations

from typing import TypedDict

from pydantic import BaseModel, ConfigDict, Field


class ResearchBrief(BaseModel):
    """把用户的宽泛主题整理成可执行的研究任务。"""

    topic: str
    objective: str
    subquestions: list[str] = Field(default_factory=list)
    scope_notes: list[str] = Field(default_factory=list)
    output_language: str = "Chinese"


class QueryPlan(BaseModel):
    """模型为下一轮提出的搜索词。"""

    queries: list[str] = Field(default_factory=list)


class SearchResult(BaseModel):
    """搜索供应商刚返回的一条临时结果。

    它还没有稳定来源编号；登记进任务级来源台账后才会变成 ``SourceRecord``。
    ``extra='ignore'`` 让供应商将来增加字段时不至于破坏我们的解析。
    """

    model_config = ConfigDict(extra="ignore")

    query: str
    title: str
    url: str
    # 网页正文可能很长，不让它出现在对象 repr 中，避免日志被整页文本淹没。
    content: str = Field(default="", repr=False)
    score: float | None = None
    published_at: str | None = None


# TODO(next-step) [Q1]: 增加来源类型、是否第一手资料和程序化质量规则；不要只依赖
# 模型给出的 quality_score 判断来源可信度。
class SourceRecord(BaseModel):
    """登记在本次任务来源台账中的稳定记录。

    ``source_id``（S1、S2……）只在一次研究任务内稳定。模型只能引用这个 ID，真实 URL
    最后由程序填入，从而减少模型虚构链接的机会。
    """

    source_id: str
    url: str
    canonical_url: str
    title: str
    domain: str
    discovered_by: list[str] = Field(default_factory=list)
    content: str = Field(default="", repr=False)
    search_score: float | None = None
    published_at: str | None = None


class ExtractedEvidence(BaseModel):
    """模型刚提取、尚未由程序绑定来源 ID 的证据。"""

    claim: str
    excerpt: str
    relevance_score: float = Field(ge=0.0, le=1.0)
    quality_score: float = Field(ge=0.0, le=1.0)


class EvidenceBatch(BaseModel):
    """一次结构化模型调用返回的一批证据。"""

    items: list[ExtractedEvidence] = Field(default_factory=list)


class Evidence(BaseModel):
    """由程序绑定到已登记来源的“结论 + 支持摘录”。"""

    source_id: str
    claim: str
    excerpt: str
    relevance_score: float = Field(ge=0.0, le=1.0)
    quality_score: float = Field(ge=0.0, le=1.0)


# TODO(next-step) [Q2]: 从一个总的 sufficient 布尔值扩展为“每个 subquestion 的覆盖
# 状态”，让下一轮查询精确针对尚未回答的子问题。
class GapAssessment(BaseModel):
    """现有证据是否充分，以及下一轮还要补什么。"""

    sufficient: bool
    gaps: list[str] = Field(default_factory=list)
    rationale: str = ""


class CitationValidation(BaseModel):
    """对报告引用进行机械校验后的结果。

    注意：它能判断 S999 不存在，却不能判断 S1 是否真的支持某句话；语义支持度属于后续
    独立的 groundedness 检查节点。
    """

    valid: bool
    referenced_ids: list[str] = Field(default_factory=list)
    unknown_ids: list[str] = Field(default_factory=list)
    bare_urls: list[str] = Field(default_factory=list)
    messages: list[str] = Field(default_factory=list)


class ResearchState(TypedDict):
    """LangGraph 在所有节点之间传递的完整状态。

    当前字段没有配置 reducer，因此节点更新 list/dict 时必须先复制旧值，再显式累加；
    如果只返回本轮新增项，就会覆盖历史数据。
    """

    # ① 用户输入与研究范围
    topic: str
    research_brief: ResearchBrief | None

    # ② 当前轮与历史搜索词
    current_queries: list[str]
    searched_queries: list[str]
    pending_source_ids: list[str]

    # ③ 任务级来源台账与已接受证据
    sources: dict[str, SourceRecord]
    evidence: list[Evidence]
    information_gaps: list[str]
    gap_assessment: GapAssessment | None

    # ④ 代码强制执行的预算计数
    round_count: int
    search_count: int
    pages_processed: int

    # ⑤ 诊断信息；非致命错误也会保留，便于最后排查
    errors: list[str]
    trace: list[str]
    stop_reason: str | None

    # ⑥ 草稿、引用校验和最终可发布报告
    draft_report: str
    citation_validation: CitationValidation | None
    final_report: str
