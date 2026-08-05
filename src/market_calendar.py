"""東証(JPX)・米国市場(NYSE)の休場日判定。

近似判定であり、イレギュラーな臨時休場等には対応していない(README参照)。
"""
from __future__ import annotations

import datetime as dt

import jpholiday
import pandas_market_calendars as mcal

_NYSE = mcal.get_calendar("XNYS")


def is_jpx_trading_day(date: dt.date) -> bool:
    if date.weekday() >= 5:  # 土日
        return False
    if jpholiday.is_holiday(date):
        return False
    if (date.month == 12 and date.day == 31) or (date.month == 1 and date.day in (1, 2, 3)):
        return False
    return True


def is_us_trading_day(date: dt.date) -> bool:
    schedule = _NYSE.schedule(start_date=date, end_date=date)
    return not schedule.empty
