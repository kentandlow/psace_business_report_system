"""情報収集モジュール (Step 2)

前週1週間分（過去7日間）の宇宙ビジネス関連ニュースを
RSS フィード / arXiv API から収集し、data/raw_news.json に保存する。
"""

import json
import time
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
from typing import Any

import feedparser
import requests
from bs4 import BeautifulSoup

from utils import ensure_dirs, setup_logger

logger = setup_logger(__name__)

OUTPUT_PATH = Path("data/raw_news.json")

# ---------------------------------------------------------------------------
# 設定
# ---------------------------------------------------------------------------

RSS_FEEDS: list[dict] = [
    {
        "name": "SpaceNews",
        "url": "https://spacenews.com/feed/",
        "category": "business",
    },
    {
        "name": "Google News – Space Business (EN)",
        "query": "space business",
        "params": "hl=en-US&gl=US&ceid=US:en",
        "category": "business",
    },
    {
        "name": "Google News – Space Policy (EN)",
        "query": "space policy",
        "params": "hl=en-US&gl=US&ceid=US:en",
        "category": "policy",
    },
    {
        "name": "Google News – Space Funding (EN)",
        "query": "space startup funding",
        "params": "hl=en-US&gl=US&ceid=US:en",
        "category": "funding",
    },
    {
        "name": "Google News – Space Europe (EN)",
        "query": "ESA OR space Europe",
        "params": "hl=en-US&gl=US&ceid=US:en",
        "category": "policy",
    },
    {
        "name": "Google News – Space China (EN)",
        "query": "China space",
        "params": "hl=en-US&gl=US&ceid=US:en",
        "category": "policy",
    },
    {
        "name": "Google News – 宇宙ビジネス (JA)",
        "query": "宇宙 ビジネス",
        "params": "hl=ja&gl=JP&ceid=JP:ja",
        "category": "business",
    },
    {
        "name": "Google News – 宇宙政策 (JA)",
        "query": "宇宙 政策",
        "params": "hl=ja&gl=JP&ceid=JP:ja",
        "category": "policy",
    },
    {
        "name": "Google News – 宇宙資金調達 (JA)",
        "query": "宇宙 資金調達 OR 宇宙 スタートアップ",
        "params": "hl=ja&gl=JP&ceid=JP:ja",
        "category": "funding",
    },
]

ARXIV_API_URL = "http://export.arxiv.org/api/query"
ARXIV_QUERIES = [
    "cat:astro-ph.IM",            # Instrumentation and Methods
    "cat:astro-ph.EP",            # Earth and Planetary Astrophysics
    "ti:commercial+AND+ti:space", # 商業宇宙関連論文
]
ARXIV_MAX_RESULTS = 15

HEADERS = {
    "User-Agent": (
        "SpaceBusinessReportBot/1.0 "
        "(automated academic/business research; non-commercial)"
    )
}

# ---------------------------------------------------------------------------
# ヘルパー関数
# ---------------------------------------------------------------------------

def _get_date_range() -> tuple[datetime, datetime]:
    """収集対象の開始日時と終了日時（UTC aware）を返す"""
    start_str = os.getenv("START_DATE")
    end_str = os.getenv("END_DATE")
    
    now = datetime.now(tz=timezone.utc)
    if start_str and end_str:
        start_dt = datetime.strptime(start_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        end_dt = datetime.strptime(end_str, "%Y-%m-%d").replace(hour=23, minute=59, second=59, tzinfo=timezone.utc)
        return start_dt, end_dt
    
    # デフォルトは過去7日間
    return now - timedelta(days=7), now


def _build_google_news_url(query: str, params: str, start_dt: datetime, end_dt: datetime) -> str:
    """指定期間のGoogle News RSS URLを構築する"""
    # yyyy-mm-dd形式に変換
    start_str = start_dt.strftime("%Y-%m-%d")
    end_str = end_dt.strftime("%Y-%m-%d")
    return f"https://news.google.com/rss/search?q={query}+after:{start_str}+before:{end_str}&{params}"


def _parse_date(entry: Any) -> datetime | None:
    """feedparser エントリから公開日時を UTC aware datetime に変換する"""
    import calendar

    if hasattr(entry, "published_parsed") and entry.published_parsed:
        ts = calendar.timegm(entry.published_parsed)
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    if hasattr(entry, "updated_parsed") and entry.updated_parsed:
        ts = calendar.timegm(entry.updated_parsed)
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    return None


def _strip_html(text: str) -> str:
    """HTML タグを除去してプレーンテキストを返す"""
    try:
        return BeautifulSoup(text, "html.parser").get_text(separator=" ").strip()
    except Exception:
        return text


def _entry_to_dict(entry: Any, category: str, source_name: str) -> dict:
    """feedparser のエントリを辞書形式に変換する"""
    pub_dt = _parse_date(entry)
    summary = _strip_html(getattr(entry, "summary", "") or "")
    return {
        "title": getattr(entry, "title", ""),
        "url": getattr(entry, "link", ""),
        "summary": summary[:1000],  # 長すぎる場合は切り詰め
        "published": pub_dt.isoformat() if pub_dt else None,
        "source": source_name,
        "category": category,
    }


# ---------------------------------------------------------------------------
# RSS 収集
# ---------------------------------------------------------------------------


def collect_rss() -> list[dict]:
    """設定済みの RSS フィードからニュースを収集する"""
    start_dt, end_dt = _get_date_range()
    logger.info(f"対象期間: {start_dt.strftime('%Y-%m-%d')} ~ {end_dt.strftime('%Y-%m-%d')}")
    results: list[dict] = []

    for feed_config in RSS_FEEDS:
        name = feed_config["name"]
        category = feed_config["category"]
        
        if "query" in feed_config:
            url = _build_google_news_url(feed_config["query"], feed_config["params"], start_dt, end_dt)
        else:
            url = feed_config["url"]
            
        logger.info("RSS 取得中: %s", name)

        try:
            feed = feedparser.parse(url, request_headers=HEADERS)
            if feed.bozo and feed.bozo_exception:
                logger.warning("RSS パース警告 (%s): %s", name, feed.bozo_exception)

            count = 0
            for entry in feed.entries:
                pub_dt = _parse_date(entry)
                # Google News 等で日時が取得できないものは許容する
                if pub_dt is None or (start_dt <= pub_dt <= end_dt):
                    results.append(_entry_to_dict(entry, category, name))
                    count += 1

            logger.info("  → %d 件取得", count)

        except Exception as exc:
            logger.error("RSS 取得失敗 (%s): %s", name, exc)

        time.sleep(1)  # サーバー負荷軽減のためのウェイト

    return results


# ---------------------------------------------------------------------------
# arXiv 収集
# ---------------------------------------------------------------------------


def collect_arxiv() -> list[dict]:
    """arXiv API から宇宙関連の最新論文を収集する"""
    start_dt, end_dt = _get_date_range()
    results: list[dict] = []

    for query in ARXIV_QUERIES:
        logger.info("arXiv 取得中: query=%s", query)
        params = {
            "search_query": f"{query} AND submittedDate:[{start_dt.strftime('%Y%m%d')}2359 TO {end_dt.strftime('%Y%m%d')}2359]",
            "sortBy": "submittedDate",
            "sortOrder": "descending",
            "max_results": ARXIV_MAX_RESULTS,
        }
        try:
            resp = requests.get(
                ARXIV_API_URL, params=params, headers=HEADERS, timeout=30
            )
            resp.raise_for_status()
            feed = feedparser.parse(resp.text)

            count = 0
            for entry in feed.entries:
                pub_dt = _parse_date(entry)
                if pub_dt is None or (start_dt <= pub_dt <= end_dt):
                    results.append(_entry_to_dict(entry, "research", "arXiv"))
                    count += 1

            logger.info("  → %d 件取得", count)

        except Exception as exc:
            logger.error("arXiv 取得失敗 (query=%s): %s", query, exc)

        time.sleep(3)  # arXiv 利用規約に従い十分なウェイトを設ける

    return results


# ---------------------------------------------------------------------------
# メイン
# ---------------------------------------------------------------------------


def collect() -> list[dict]:
    """全ソースからニュースを収集して data/raw_news.json に保存する"""
    ensure_dirs()
    logger.info("=== 情報収集開始 ===")

    all_items: list[dict] = []
    all_items.extend(collect_rss())
    all_items.extend(collect_arxiv())

    # URL 重複除去
    seen_urls: set[str] = set()
    unique_items: list[dict] = []
    for item in all_items:
        url = item.get("url", "")
        if url and url not in seen_urls:
            seen_urls.add(url)
            unique_items.append(item)
        elif not url:
            unique_items.append(item)

    logger.info("収集完了: 合計 %d 件（重複除去後）", len(unique_items))

    OUTPUT_PATH.write_text(
        json.dumps(unique_items, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    logger.info("保存先: %s", OUTPUT_PATH)

    return unique_items


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    collect()
