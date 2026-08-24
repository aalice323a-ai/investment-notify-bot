"""GitHub Actions の workflow_dispatch テキスト入力から data/watchlist.json を
全件置き換えるスクリプト(update_holdings.py の監視銘柄版)。

入力フォーマット(1行1銘柄、カンマ区切り。空行・#始まりの行は無視):
    コード,名称,市場(JP または US)

例:
    8035,東京エレクトロン,JP
    NVDA,NVIDIA,US

1行でも形式が不正な場合は全体を更新せずエラー終了する(中途半端な
置き換えを避けるため)。監視銘柄には dividend_hold の概念が無いため
保有銘柄用フォーマットと異なり常に3フィールド。
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import git_publish, line_client
from src.log import log

WATCHLIST_PATH = Path(__file__).resolve().parent.parent / "data" / "watchlist.json"


def parse_line(line_no: int, line: str) -> dict:
    parts = [p.strip() for p in line.split(",")]
    if len(parts) != 3:
        raise ValueError(f"{line_no}行目: フィールド数が不正です(3つ必要): {line!r}")

    code, name, market = parts[0], parts[1], parts[2].upper()
    if not code or not name:
        raise ValueError(f"{line_no}行目: コードまたは名称が空です: {line!r}")
    if market not in ("JP", "US"):
        raise ValueError(f"{line_no}行目: 市場は JP または US を指定してください: {line!r}")

    return {"code": code, "name": name, "market": market}


def parse_watchlist_text(text: str) -> list[dict]:
    watchlist: list[dict] = []
    for i, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        watchlist.append(parse_line(i, line))
    if not watchlist:
        raise ValueError("有効な銘柄が1件もありませんでした")
    return watchlist


def main() -> None:
    text = os.environ.get("WATCHLIST_TEXT", "")
    log(f"[UpdateWatchlist] input length={len(text)} chars")

    try:
        watchlist = parse_watchlist_text(text)
    except ValueError as e:
        log(f"[UpdateWatchlist] ERROR parsing input: {e}")
        line_client.notify_failure("監視銘柄リストの更新(入力エラー)", str(e))
        raise

    log(f"[UpdateWatchlist] parsed {len(watchlist)} ticker(s)")

    WATCHLIST_PATH.write_text(
        json.dumps(watchlist, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    try:
        git_publish.commit_and_push(
            [WATCHLIST_PATH], "chore: update watchlist via workflow_dispatch"
        )
    except Exception as e:
        log(f"[UpdateWatchlist] ERROR committing: {type(e).__name__}: {e}")
        line_client.notify_failure("監視銘柄リストの更新(コミット失敗)", str(e))
        raise

    jp = [w for w in watchlist if w["market"] == "JP"]
    us = [w for w in watchlist if w["market"] == "US"]
    summary_lines = [
        "監視銘柄リストを更新しました。",
        f"日本株 {len(jp)}銘柄 / 米国株 {len(us)}銘柄(合計{len(watchlist)}銘柄)",
        "",
    ] + [f"・{w['name']}({w['code']})" for w in watchlist]
    line_client.push_report("\n".join(summary_lines)[:4900])
    log("[UpdateWatchlist] done")


if __name__ == "__main__":
    main()
