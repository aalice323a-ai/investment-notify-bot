"""日本株パート エントリポイント。平日21:00 JST(東証終値確定後)に実行する想定。"""
from __future__ import annotations

import datetime as dt
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.holdings import JP_HOLDINGS, US_HOLDINGS
from config.watchlist import JP_WATCHLIST, US_WATCHLIST
from src import claude_client, line_client, market_calendar, report
from src.log import log

JST = dt.timezone(dt.timedelta(hours=9))


def main() -> None:
    log("=== JP session start ===")
    today = dt.datetime.now(JST).date()
    log(f"today(JST)={today.isoformat()} weekday={today.strftime('%A')}")

    if not market_calendar.is_jpx_trading_day(today):
        log("today is NOT a JPX trading day -> skip (no LINE message sent)")
        return  # 東証休場日はスキップ
    log("today IS a JPX trading day -> proceeding")

    # YouTube動画の判定は保有・監視銘柄全体(日本株+米国株)を対象にする
    all_names = [h.name for h in JP_HOLDINGS + US_HOLDINGS + JP_WATCHLIST + US_WATCHLIST]

    video_summaries, video_state = report.collect_video_facts(all_names)
    ticker_facts = report.collect_ticker_facts(JP_HOLDINGS, JP_WATCHLIST)
    macro_events = report.collect_macro_events(today)

    report.save_processed_videos(video_state)
    log("processed_videos.json saved locally")

    facts = {
        "session": "jp",
        "date": today.isoformat(),
        "video_summaries": video_summaries,
        "tickers": ticker_facts,
        "macro_events": macro_events,
    }

    try:
        report.publish_state()
    except Exception as e:
        log(f"ERROR publishing state: {type(e).__name__}: {e}")
        line_client.notify_failure("状態ファイルのアップロード", str(e))

    log("requesting report composition from Claude")
    try:
        text = claude_client.compose_report(facts)
        log(f"report composed: {len(text)} character(s)")
    except Exception as e:
        log(f"ERROR composing report: {type(e).__name__}: {e}")
        line_client.notify_failure("レポート生成", str(e))
        text = "本日のレポート生成に失敗しました。個別の失敗通知をご確認ください。"

    log("pushing report to LINE")
    line_client.push_report(text)
    log("=== JP session end ===")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"FATAL: {type(e).__name__}: {e}\n{traceback.format_exc()}")
        line_client.notify_failure("日本株パート全体の処理", f"{e}\n{traceback.format_exc()[:400]}")
        raise
