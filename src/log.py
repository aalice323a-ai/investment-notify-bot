"""GitHub Actionsのログにすぐ反映される共通ログ出力ヘルパー。"""
from __future__ import annotations

import datetime as dt


def log(message: str) -> None:
    ts = dt.datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {message}", flush=True)
