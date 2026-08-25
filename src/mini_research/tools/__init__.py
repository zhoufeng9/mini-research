"""集中导出 mini_research 使用的外部工具适配器。"""

from mini_research.tools.search import (
    SearchProvider,
    TavilySearchProvider,
    canonicalize_url,
    register_search_results,
)

__all__ = [
    "SearchProvider",
    "TavilySearchProvider",
    "canonicalize_url",
    "register_search_results",
]
