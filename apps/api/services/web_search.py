from __future__ import annotations

import logging

from duckduckgo_search import DDGS
from duckduckgo_search.exceptions import DuckDuckGoSearchException

from config import settings
from services.openai_runtime import get_tavily_api_key

logger = logging.getLogger(__name__)

SearchResult = dict[str, str]


def _normalize_ddg_result(item: dict) -> SearchResult | None:
    title = (item.get("title") or "").strip()
    url = (item.get("href") or item.get("url") or "").strip()
    snippet = (item.get("body") or item.get("snippet") or "").strip()
    if not url:
        return None
    return {
        "title": title or url,
        "url": url,
        "snippet": snippet,
    }


def _search_duckduckgo(query: str, max_results: int) -> list[SearchResult]:
    backends: list[str | None] = [None, "bing", "lite"]

    for backend in backends:
        try:
            kwargs: dict = {"max_results": max_results}
            if backend:
                kwargs["backend"] = backend

            with DDGS() as ddgs:
                raw_results = list(ddgs.text(query, **kwargs))

            results: list[SearchResult] = []
            for item in raw_results:
                normalized = _normalize_ddg_result(item)
                if normalized is not None:
                    results.append(normalized)
            if results:
                return results
        except DuckDuckGoSearchException as exc:
            logger.warning("DuckDuckGo search failed (backend=%s): %s", backend, exc)
        except Exception as exc:
            logger.warning("DuckDuckGo search error (backend=%s): %s", backend, exc)

    return []


def _clean_api_key(raw: str) -> str:
    return raw.strip().strip('"').strip("'")


def _search_tavily(query: str, max_results: int) -> list[SearchResult]:
    api_key = _clean_api_key(get_tavily_api_key() or "")
    if not api_key:
        logger.warning("Tavily selected but TAVILY_API_KEY is not set")
        return []

    if not api_key.isascii():
        logger.error(
            "TAVILY_API_KEY contains non-ASCII characters. "
            "Re-set it to your real tvly-... key (not a placeholder)."
        )
        return []

    try:
        from tavily import TavilyClient

        client = TavilyClient(api_key=api_key)
        response = client.search(
            query=query,
            max_results=max_results,
            search_depth="basic",
        )
    except UnicodeEncodeError:
        logger.error(
            "Tavily request failed: invalid TAVILY_API_KEY encoding. "
            "Use only the ASCII tvly-... key from Tavily dashboard."
        )
        return []
    except Exception as exc:
        logger.warning("Tavily search failed: %s", exc)
        return []

    results: list[SearchResult] = []
    for item in response.get("results", []):
        title = (item.get("title") or "").strip()
        url = (item.get("url") or "").strip()
        snippet = (item.get("content") or item.get("snippet") or "").strip()
        if not url:
            continue
        results.append(
            {
                "title": title or url,
                "url": url,
                "snippet": snippet[:500],
            }
        )
    return results


def search_web(query: str, max_results: int = 5) -> list[dict]:
    """
    Search the web using the configured provider.

    Provider is set via WEB_SEARCH_PROVIDER env var:
      - tavily (default when TAVILY_API_KEY is set)
      - duckduckgo

    Returns uniform format:
    [{"title": "...", "url": "https://...", "snippet": "..."}, ...]
    """
    trimmed = query.strip()
    if not trimmed:
        return []

    max_results = max(1, min(max_results, 10))
    provider = settings.web_search_provider.lower()

    if provider == "tavily":
        results = _search_tavily(trimmed, max_results)
        if results:
            return results
        logger.warning("Tavily returned no results; falling back to DuckDuckGo")
        return _search_duckduckgo(trimmed, max_results)

    return _search_duckduckgo(trimmed, max_results)
