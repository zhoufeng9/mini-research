"""确定性的引用校验与 Markdown 链接渲染。

“确定性”表示相同输入总会得到相同结果，不需要再调用模型。本模块只做机械规则校验：
来源 ID 是否存在、是否出现裸 URL；它暂时不判断某条来源是否在语义上支持结论。
"""

from __future__ import annotations

import re
from collections.abc import Mapping

from mini_research.models import CitationValidation, SourceRecord

# ``(?!\()`` 避免把已经渲染成 ``[S1](url)`` 的引用再次处理。
_CITATION_PATTERN = re.compile(r"\[S(?P<number>[1-9]\d*)\](?!\()")
_BARE_URL_PATTERN = re.compile(r"https?://[^\s)>\]]+")


def extract_citation_ids(markdown: str) -> list[str]:
    """按首次出现顺序返回不重复的引用 ID。"""

    seen: set[str] = set()
    ordered: list[str] = []
    for match in _CITATION_PATTERN.finditer(markdown):
        source_id = f"S{match.group('number')}"
        if source_id not in seen:
            seen.add(source_id)
            ordered.append(source_id)
    return ordered


def validate_citations(
    markdown: str,
    sources: Mapping[str, SourceRecord],
    *,
    require_at_least_one: bool = True,
) -> CitationValidation:
    """检查模型是否只使用来源 ID，并且每个 ID 都已登记。"""

    referenced_ids = extract_citation_ids(markdown)
    unknown_ids = [source_id for source_id in referenced_ids if source_id not in sources]
    bare_urls = _BARE_URL_PATTERN.findall(markdown)
    messages: list[str] = []

    if require_at_least_one and not referenced_ids:
        messages.append("The draft contains no source citations.")
    if unknown_ids:
        messages.append(f"Unknown source IDs: {', '.join(unknown_ids)}")
    if bare_urls:
        messages.append("The model wrote URL text directly instead of using source IDs.")

    return CitationValidation(
        valid=not messages,
        referenced_ids=referenced_ids,
        unknown_ids=unknown_ids,
        bare_urls=bare_urls,
        messages=messages,
    )


def render_report(markdown: str, sources: Mapping[str, SourceRecord]) -> str:
    """把通过校验的 ID 渲染成链接，再追加确定性的来源列表。"""

    validation = validate_citations(markdown, sources)
    if not validation.valid:
        raise ValueError("; ".join(validation.messages))

    def replace(match: re.Match[str]) -> str:
        source_id = f"S{match.group('number')}"
        return f"[{source_id}]({sources[source_id].url})"

    rendered = _CITATION_PATTERN.sub(replace, markdown).rstrip()
    source_lines = []
    # 来源表按正文首次引用顺序生成，只列实际使用过的来源。
    for source_id in validation.referenced_ids:
        source = sources[source_id]
        safe_title = source.title.replace("[", "\\[").replace("]", "\\]")
        source_lines.append(f"- [{source_id}] [{safe_title}]({source.url})")

    return f"{rendered}\n\n## Sources\n\n" + "\n".join(source_lines) + "\n"
