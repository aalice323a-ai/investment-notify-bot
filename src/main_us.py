"""米国株パート エントリポイント。平日翌7:00 JST(米国市場引け後)に実行する想定。"""
from __future__ import annotations

import datetime as dt
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.holdings import US_HOLDINGS
from config.watchlist import US_WATCHLIST
from src import claude_client, line_client, market_calendar, report

JST = dt.timezone(dt.timedelta(hours=9))


def main() -> None:
    today_jst = dt.datetime.now(JST).date()
    # 7:00 JSTに引けを報告する対象は、前日(JST基準)の米国市場セッション
    us_session_date = today_jst - dt.timedelta(days=1)
    if not market_calendar.is_us_trading_day(us_session_date):
        return  # 米国市場休場日はスキップ

    chart_dir = report.CHARTS_ROOT / today_jst.isoformat() / "us"
    ticker_facts, chart_paths = report.collect_ticker_facts(US_HOLDINGS, US_WATCHLIST, chart_dir)
    macro_events = report.collect_macro_events()

    facts = {
        "session": "us",
        "date": today_jst.isoformat(),
        "us_session_date": us_session_date.isoformat(),
        "tickers": ticker_facts,
        "macro_events_search_results": macro_events,
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
        line_client.notify_failure("米国株パート全体の処理", f"{e}\n{traceback.format_exc()[:400]}")
        raise
