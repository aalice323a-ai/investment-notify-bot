"""保有銘柄マスタ定義。data/holdings.json を読み込む。

銘柄の追加・削除・dividend_hold(長期配当目的保有=買い増し/売却判定対象外)の
変更は、GitHub Actionsの `Update Holdings (manual)` ワークフロー
(workflow_dispatch、LINEを経由せずリスト全体をテキストで貼り替える方式)
から行うか、data/holdings.json を直接編集してください。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

_DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "holdings.json"


@dataclass(frozen=True)
class Holding:
    code: str
    name: str
    market: str  # "JP" or "US"
    dividend_hold: bool = False

    @property
    def yf_ticker(self) -> str:
        """yfinance用のティッカーシンボル"""
        return f"{self.code}.T" if self.market == "JP" else self.code


def _load() -> list[Holding]:
    records = json.loads(_DATA_PATH.read_text(encoding="utf-8"))
    return [
        Holding(
            code=r["code"],
            name=r["name"],
            market=r["market"],
            dividend_hold=bool(r.get("dividend_hold", False)),
        )
        for r in records
    ]


_ALL: list[Holding] = _load()
JP_HOLDINGS: list[Holding] = [h for h in _ALL if h.market == "JP"]
US_HOLDINGS: list[Holding] = [h for h in _ALL if h.market == "US"]


def all_holdings() -> list[Holding]:
    return JP_HOLDINGS + US_HOLDINGS
