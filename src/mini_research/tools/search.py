"""搜索接口、Tavily 适配器，以及任务内 URL 去重。

这里尽量保持供应商无关：工作流只认识 ``SearchProvider``，Tavily 的响应格式被隔离在
最下方的适配器中。以后替换搜索服务时，不需要重写 LangGraph。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from mini_research.models import SearchResult, SourceRecord

_TRACKING_PARAMETERS = {
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "ref",
    "source",
}


class SearchProvider(Protocol):
    """与具体供应商无关的最小搜索接口。"""

    def search(self, query: str, *, max_results: int) -> list[SearchResult]: ...


def canonicalize_url(url: str) -> str:
    """规范化常见跟踪参数、片段和尾斜杠，用于 URL 级去重。

    这只能判断两个 URL 是否指向同一个规范地址，不能判断两篇不同 URL 的文章是否转载
    了相同内容。
    """

    candidate = url.strip()
    if not candidate:
        raise ValueError("URL must not be empty")
    if "://" not in candidate:
        candidate = f"https://{candidate}"

    parts = urlsplit(candidate)
    scheme = parts.scheme.lower()
    if scheme not in {"http", "https"}:
        raise ValueError(f"Unsupported URL scheme: {scheme}")
    hostname = (parts.hostname or "").lower()
    if not hostname:
        raise ValueError(f"URL has no hostname: {url}")

    port = parts.port
    if port and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
        hostname = f"{hostname}:{port}"

    path = parts.path.rstrip("/")
    filtered_query = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        lowered = key.lower()
        if lowered.startswith("utm_") or lowered in _TRACKING_PARAMETERS:
            continue
        filtered_query.append((key, value))
    filtered_query.sort()

    return urlunsplit((scheme, hostname, path, urlencode(filtered_query), ""))


def register_search_results(
    existing: Mapping[str, SourceRecord],
    results: Sequence[SearchResult],
    *,
    max_new_sources: int,
) -> tuple[dict[str, SourceRecord], list[str]]:
    """把未见过的 URL 登记进稳定来源台账，并返回本轮新增 ID。

    重复 URL 不创建新 S 编号，而是合并发现它的查询、保留更长正文和更高搜索分数。
    """

    updated = dict(existing)
    canonical_to_id = {source.canonical_url: source_id for source_id, source in updated.items()}
    existing_numbers = [
        int(source_id[1:])
        for source_id in updated
        if source_id.startswith("S") and source_id[1:].isdigit()
    ]
    next_number = max(existing_numbers, default=0) + 1
    new_ids: list[str] = []

    for result in results:
        try:
            canonical_url = canonicalize_url(result.url)
        except ValueError:
            continue

        existing_id = canonical_to_id.get(canonical_url)
        if existing_id:
            # 同一来源可能被不同搜索词多次发现；合并信息而不是浪费页面预算。
            source = updated[existing_id]
            discovered_by = list(source.discovered_by)
            if result.query not in discovered_by:
                discovered_by.append(result.query)
            better_content = (
                result.content if len(result.content) > len(source.content) else source.content
            )
            scores = [score for score in (source.search_score, result.score) if score is not None]
            updated[existing_id] = source.model_copy(
                update={
                    "discovered_by": discovered_by,
                    "content": better_content,
                    "search_score": max(scores) if scores else None,
                    "published_at": source.published_at or result.published_at,
                }
            )
            continue

        if len(new_ids) >= max_new_sources:
            break

        source_id = f"S{next_number}"
        next_number += 1
        source = SourceRecord(
            source_id=source_id,
            url=result.url,
            canonical_url=canonical_url,
            title=result.title or canonical_url,
            domain=urlsplit(canonical_url).hostname or "",
            discovered_by=[result.query],
            content=result.content,
            search_score=result.score,
            published_at=result.published_at,
        )
        updated[source_id] = source
        canonical_to_id[canonical_url] = source_id
        new_ids.append(source_id)

    return updated, new_ids


class TavilySearchProvider:
    """把 Tavily 响应转换成项目领域对象的薄适配器。"""

    def __init__(self, *, api_key: str, max_content_chars: int = 12_000) -> None:
        # 惰性导入：只做离线测试时，不会因为缺少客户端或 Key 而导入失败。
        from tavily import TavilyClient

        self._client = TavilyClient(api_key=api_key)
        self._max_content_chars = max_content_chars

    def search(self, query: str, *, max_results: int) -> list[SearchResult]:
        """搜索网页，并保留足够正文供后续证据提取。"""

        # TODO(next-step) [R1]: 为超时、429 和临时 5xx 增加有上限的指数退避，并定义
        # SearchError 类型；供应商细节应留在本适配器，不要泄漏到 graph.py。
        response = self._client.search(
            query=query,
            max_results=max_results,
            include_raw_content=True,
            topic="general",
        )
        parsed: list[SearchResult] = []
        for item in response.get("results", []):
            content = item.get("raw_content") or item.get("content") or ""
            # 截断正文同时保护上下文窗口、费用和运行时间；它也意味着很长网页的尾部信息
            # 可能暂时无法被发现，后续可改成分块提取。
            parsed.append(
                SearchResult(
                    query=query,
                    title=item.get("title") or item.get("url") or "Untitled source",
                    url=item.get("url") or "",
                    content=content[: self._max_content_chars],
                    score=item.get("score"),
                    published_at=item.get("published_date"),
                )
            )
        return parsed
