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

JST = dt.timezone(dt.timedelta(hours=9))


def main() -> None:
    today = dt.datetime.now(JST).date()
    if not market_calendar.is_jpx_trading_day(today):
        return  # 東証休場日はスキップ

    chart_dir = report.CHARTS_ROOT / today.isoformat() / "jp"
    # YouTube動画の判定は保有・監視銘柄全体(日本株+米国株)を対象にする
    all_names = [h.name for h in JP_HOLDINGS + US_HOLDINGS + JP_WATCHLIST + US_WATCHLIST]

    video_summaries, video_state = report.collect_video_facts(all_names)
    ticker_facts, chart_paths = report.collect_ticker_facts(JP_HOLDINGS, JP_WATCHLIST, chart_dir)
    macro_events = report.collect_macro_events()
    new_candidates = report.collect_new_candidate_research()

    report.save_processed_videos(video_state)

    facts = {
        "session": "jp",
        "date": today.isoformat(),
        "video_summaries": video_summaries,
        "tickers": ticker_facts,
        "macro_events_search_results": macro_events,
        "new_candidate_research_search_results": new_candidates,
    }

    image_urls: list[str] = []
    try:
        image_urls = report.publish_charts_and_state(chart_paths)
    except Exception as e:
        line_client.notify_failure("チャート画像のアップロード", str(e))

    try:
        text = claude_client.compose_report(facts)
    except Exception as e:
        line_client.notify_failure("レポート生成", str(e))
        text = "本日のレポート生成に失敗しました。個別の失敗通知をご確認ください。"

    line_client.push_report(text, image_urls)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        line_client.notify_failure("日本株パート全体の処理", f"{e}\n{traceback.format_exc()[:400]}")
        raise
