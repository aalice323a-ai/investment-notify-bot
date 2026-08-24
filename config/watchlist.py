"""新規検討候補として監視している銘柄マスタ定義。data/watchlist.json を読み込む。

Claudeが「新規監視銘柄の提案」を行った場合も、自動追加はせず、
GitHub Actionsの `Update Watchlist (manual)` ワークフロー(workflow_dispatch)
から更新するか、data/watchlist.json を直接編集してください。
"""
from __future__ import annotations

import json
from pathlib import Path

from config.holdings import Holding

_DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "watchlist.json"


def _load() -> list[Holding]:
    records = json.loads(_DATA_PATH.read_text(encoding="utf-8"))
    return [Holding(code=r["code"], name=r["name"], market=r["market"]) for r in records]


_ALL: list[Holding] = _load()
JP_WATCHLIST: list[Holding] = [h for h in _ALL if h.market == "JP"]
US_WATCHLIST: list[Holding] = [h for h in _ALL if h.market == "US"]


def all_watchlist() -> list[Holding]:
    return JP_WATCHLIST + US_WATCHLIST
