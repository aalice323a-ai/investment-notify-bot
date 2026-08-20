"""LINE送信機能のみを単体で検証するための最小スクリプト。

株価取得・YouTube・Gemini要約など、他の機能には一切依存しない。
本番と同じ line_client.push_report() を使い、LINE Messaging API
そのものが正常に呼び出せるかどうかだけを確認する。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import line_client
from src.log import log


def main() -> None:
    log("=== LINE send test start ===")
    line_client.push_report("テスト送信です")
    log("=== LINE send test end (no exception raised = success) ===")


if __name__ == "__main__":
    main()
