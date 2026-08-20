"""FOMC・日銀金融政策決定会合・米雇用統計・CPI発表の日程カレンダー。

Google Custom Search JSON APIが新規プロジェクトで利用不可になった(Google側の
方針変更)ため、検索ベースでの取得をやめ、各公式サイトが事前に公表している
確定日程をそのまま保持する方式にした。いずれも年1回まとめて公表される
確定スケジュールのため、検索より正確かつ無料・無依存で扱える。

年をまたぐ場合は _EVENTS に翌年分を追記すること。出典:
- FOMC: https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm
- 日銀: https://www.boj.or.jp/mopo/mpmsche_minu/index.htm (2026年分は2025/7/31公表)
- 米雇用統計(Employment Situation)・CPI: https://www.bls.gov/schedule/
  (政府機関の一時閉鎖等により実際の発表日が数日ずれることがある点に注意)
"""
from __future__ import annotations

import datetime as dt

# (発表日, イベント名)
_EVENTS: list[tuple[dt.date, str]] = [
    # --- FOMC政策金利発表(会合最終日) ---
    (dt.date(2026, 1, 28), "FOMC政策金利発表"),
    (dt.date(2026, 3, 18), "FOMC政策金利発表"),
    (dt.date(2026, 4, 29), "FOMC政策金利発表"),
    (dt.date(2026, 6, 17), "FOMC政策金利発表"),
    (dt.date(2026, 7, 29), "FOMC政策金利発表"),
    (dt.date(2026, 9, 16), "FOMC政策金利発表"),
    (dt.date(2026, 10, 28), "FOMC政策金利発表"),
    (dt.date(2026, 12, 9), "FOMC政策金利発表"),
    # --- 日銀金融政策決定会合(会合最終日) ---
    (dt.date(2026, 1, 23), "日銀金融政策決定会合"),
    (dt.date(2026, 3, 19), "日銀金融政策決定会合"),
    (dt.date(2026, 4, 28), "日銀金融政策決定会合"),
    (dt.date(2026, 6, 16), "日銀金融政策決定会合"),
    (dt.date(2026, 7, 31), "日銀金融政策決定会合"),
    (dt.date(2026, 9, 18), "日銀金融政策決定会合"),
    (dt.date(2026, 10, 30), "日銀金融政策決定会合"),
    (dt.date(2026, 12, 18), "日銀金融政策決定会合"),
    # --- 米雇用統計(Employment Situation) ---
    (dt.date(2026, 1, 9), "米雇用統計(2025年12月分)"),
    (dt.date(2026, 2, 11), "米雇用統計(1月分)"),
    (dt.date(2026, 3, 6), "米雇用統計(2月分)"),
    (dt.date(2026, 4, 3), "米雇用統計(3月分)"),
    (dt.date(2026, 5, 8), "米雇用統計(4月分)"),
    (dt.date(2026, 6, 5), "米雇用統計(5月分)"),
    (dt.date(2026, 7, 2), "米雇用統計(6月分)"),
    (dt.date(2026, 8, 7), "米雇用統計(7月分)"),
    (dt.date(2026, 9, 4), "米雇用統計(8月分)"),
    (dt.date(2026, 10, 2), "米雇用統計(9月分)"),
    (dt.date(2026, 11, 6), "米雇用統計(10月分)"),
    (dt.date(2026, 12, 4), "米雇用統計(11月分)"),
    # --- 米CPI(消費者物価指数) ---
    (dt.date(2026, 1, 13), "米CPI(2025年12月分)"),
    (dt.date(2026, 2, 13), "米CPI(1月分)"),
    (dt.date(2026, 3, 11), "米CPI(2月分)"),
    (dt.date(2026, 4, 10), "米CPI(3月分)"),
    (dt.date(2026, 5, 12), "米CPI(4月分)"),
    (dt.date(2026, 6, 10), "米CPI(5月分)"),
    (dt.date(2026, 7, 14), "米CPI(6月分)"),
    (dt.date(2026, 8, 12), "米CPI(7月分)"),
    (dt.date(2026, 9, 11), "米CPI(8月分)"),
    (dt.date(2026, 10, 14), "米CPI(9月分)"),
    (dt.date(2026, 11, 10), "米CPI(10月分)"),
    (dt.date(2026, 12, 10), "米CPI(11月分)"),
]


def upcoming_events(from_date: dt.date, days: int = 7) -> list[dict]:
    """from_date から days 日以内(両端含む)のマクロイベントを日付順で返す。"""
    to_date = from_date + dt.timedelta(days=days)
    return [
        {"date": d.isoformat(), "event": label}
        for d, label in sorted(_EVENTS)
        if from_date <= d <= to_date
    ]
