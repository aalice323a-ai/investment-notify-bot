"""GitHub Actions の workflow_dispatch テキスト入力から data/holdings.json を
全件置き換えるスクリプト。

LINEからのメッセージで更新するにはWebhookサーバーが必要になり構成が複雑に
なるため、代わりに Actions の「Run workflow」実行時にテキストを貼り付けて
保有銘柄リストを更新できるようにしたもの(部分更新ではなく全件置き換え)。

入力フォーマット(1行1銘柄、カンマ区切り。空行・#始まりの行は無視):
    コード,名称,市場(JP または US)[,dividend_hold]

例:
    2802,味の素,JP
    8001,伊藤忠商事,JP,dividend_hold
    AMD,AMD,US

1行でも形式が不正な場合は全体を更新せずエラー終了する(中途半端な
置き換えを避けるため)。
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import git_publish, line_client
from src.log import log

HOLDINGS_PATH = Path(__file__).resolve().parent.parent / "data" / "holdings.json"


def parse_line(line_no: int, line: str) -> dict:
    parts = [p.strip() for p in line.split(",")]
    if len(parts) not in (3, 4):
        raise ValueError(f"{line_no}行目: フィールド数が不正です(3または4つ必要): {line!r}")

    code, name, market = parts[0], parts[1], parts[2].upper()
    if not code or not name:
        raise ValueError(f"{line_no}行目: コードまたは名称が空です: {line!r}")
    if market not in ("JP", "US"):
        raise ValueError(f"{line_no}行目: 市場は JP または US を指定してください: {line!r}")

    dividend_hold = False
    if len(parts) == 4:
        flag = parts[3].strip().lower()
        if flag != "dividend_hold":
            raise ValueError(f"{line_no}行目: 4つ目のフィールドは 'dividend_hold' のみ指定できます: {line!r}")
        dividend_hold = True

    return {"code": code, "name": name, "market": market, "dividend_hold": dividend_hold}


def parse_holdings_text(text: str) -> list[dict]:
    holdings: list[dict] = []
    for i, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        holdings.append(parse_line(i, line))
    if not holdings:
        raise ValueError("有効な銘柄が1件もありませんでした")
    return holdings


def main() -> None:
    text = os.environ.get("HOLDINGS_TEXT", "")
    log(f"[UpdateHoldings] input length={len(text)} chars")

    try:
        holdings = parse_holdings_text(text)
    except ValueError as e:
        log(f"[UpdateHoldings] ERROR parsing input: {e}")
        line_client.notify_failure("保有銘柄リストの更新(入力エラー)", str(e))
        raise

    log(f"[UpdateHoldings] parsed {len(holdings)} holding(s)")

    HOLDINGS_PATH.write_text(
        json.dumps(holdings, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    try:
        git_publish.commit_and_push(
            [HOLDINGS_PATH], "chore: update holdings via workflow_dispatch"
        )
    except Exception as e:
        log(f"[UpdateHoldings] ERROR committing: {type(e).__name__}: {e}")
        line_client.notify_failure("保有銘柄リストの更新(コミット失敗)", str(e))
        raise

    jp = [h for h in holdings if h["market"] == "JP"]
    us = [h for h in holdings if h["market"] == "US"]
    summary_lines = [
        "保有銘柄リストを更新しました。",
        f"日本株 {len(jp)}銘柄 / 米国株 {len(us)}銘柄(合計{len(holdings)}銘柄)",
        "",
    ] + [f"・{h['name']}({h['code']})" + ("[配当目的]" if h["dividend_hold"] else "") for h in holdings]
    line_client.push_report("\n".join(summary_lines)[:4900])
    log("[UpdateHoldings] done")


if __name__ == "__main__":
    main()
