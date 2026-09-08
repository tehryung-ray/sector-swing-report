# -*- coding: utf-8 -*-
"""한국거래소 개장일 판정.

휴장일에 리포트를 만들면 '오늘의 추천'이 열리지도 않는 장을 가리키게 된다.
판정에 실패하면(라이브러리 부재/캘린더 범위 밖) None 을 돌려주고, 호출부는
'모르면 일단 생성한다' 쪽으로 처리한다. 안 만드는 것보다 만드는 쪽이 덜 나쁘다.
"""
from __future__ import annotations

import warnings

warnings.filterwarnings("ignore")

CAL = "XKRX"


def is_kr_session(date) -> bool | None:
    """해당 날짜가 한국 정규장 개장일인가. 판정 불가 시 None."""
    try:
        import exchange_calendars as xcals
        import pandas as pd

        ts = pd.Timestamp(date).normalize()
        cal = xcals.get_calendar(CAL)
        if not (cal.first_session <= ts <= cal.last_session):
            return None
        return bool(cal.is_session(ts))
    except Exception:
        return None


def next_kr_session(date) -> str | None:
    try:
        import exchange_calendars as xcals
        import pandas as pd

        cal = xcals.get_calendar(CAL)
        ts = pd.Timestamp(date).normalize()
        # next_session 은 인자가 개장일이어야 한다. 휴장일에도 동작하도록
        # date_to_session(direction="next") 를 쓴다.
        nxt = cal.date_to_session(ts, direction="next")
        if nxt == ts:
            nxt = cal.next_session(ts)
        return str(nxt.date())
    except Exception:
        return None
