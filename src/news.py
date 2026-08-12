"""Google Custom Search JSON API を用いたニュース・マクロイベント検索。

GOOGLE_CSE_API_KEY / GOOGLE_CSE_CX は環境変数からのみ取得する。
無料枠(100クエリ/日)に収めるため、個別銘柄のニュース深掘りは
値動き・出来高が異常な銘柄のみに限定して呼び出すこと(呼び出し側の責務)。
"""
from __future__ import annotations

import datetime as dt
import os

import requests

from src.log import log

_ENDPOINT = "https://www.googleapis.com/customsearch/v1"


def _search(query: str, date_restrict: str | None = None, num: int = 5) -> list[dict]:
    params = {
        "key": os.environ["GOOGLE_CSE_API_KEY"],
        "cx": os.environ["GOOGLE_CSE_CX"],
        "q": query,
        "num": num,
        "hl": "ja",
        "gl": "jp",
    }
    if date_restrict:
        params["dateRestrict"] = date_restrict
    resp = requests.get(_ENDPOINT, params=params, timeout=20)
    if not resp.ok:
        log(f"[GoogleCSE] HTTP {resp.status_code} body={resp.text[:500]}")
    resp.raise_for_status()
    data = resp.json()
    results = []
    for item in data.get("items", []):
        results.append(
            {
                "title": item.get("title", ""),
                "snippet": item.get("snippet", ""),
                "link": item.get("link", ""),
            }
        )
    return results


def search_stock_news(name: str, code: str) -> list[dict]:
    """直近24時間以内の個別銘柄ニュースを検索する(値動き・出来高の異常時のみ呼び出す)。"""
    query = f"{name} {code} 株価 決算 OR 受注 OR 業界動向"
    return _search(query, date_restrict="d1", num=5)


def search_macro_events() -> list[dict]:
    """今後1週間程度のマクロイベント(FOMC・日銀会合・米雇用統計・CPI等)を検索する。"""
    year = dt.date.today().year
    query = f"FOMC 日銀金融政策決定会合 米国雇用統計 CPI 発表 スケジュール {year}年"
    return _search(query, num=8)


def search_new_candidates() -> list[dict]:
    """AIボトルネック(HBM/CoWoS/電力/光通信/パッケージ不足等)を解決する新規候補企業を探索する。"""
    query = "AI 半導体 ボトルネック HBM CoWoS 電力 光通信 パッケージ不足 新技術 企業 ニュース"
    return _search(query, date_restrict="w1", num=8)
