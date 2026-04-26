from __future__ import annotations

import re
from datetime import datetime


STRONG_ACTIVITY_PATTERNS = [
    r"活动报名",
    r"报名",
    r"活动预告",
    r"讲座预告",
    r"预告",
    r"会议通知",
    r"\b通知\b",
    r"讲座",
    r"论坛",
    r"分享会",
    r"研讨会",
    r"报告会",
    r"学术报告",
    r"沙龙",
    r"工作坊",
    r"训练营",
    r"展讯",
    r"招募",
    r"征集",
    r"抢票",
]

STRONG_NON_ACTIVITY_PATTERNS = [
    r"活动回顾",
    r"讲座回顾",
    r"论坛回顾",
    r"回顾",
    r"新闻[｜|丨]",
    r"顺利举办",
    r"圆满举办",
    r"顺利举行",
    r"成功举办",
    r"成功举行",
    r"圆满举行",
    r"顺利开展",
    r"圆满结束",
    r"正式发布",
    r"召开",
    r"返校",
    r"工作简报",
    r"纪实",
]

TITLE_RECAP_PATTERNS = [
    r"活动回顾",
    r"讲座回顾",
    r"论坛回顾",
    r"新闻[｜|丨]",
    r"顺利举办",
    r"圆满举办",
    r"顺利举行",
    r"成功举办",
    r"成功举行",
    r"圆满举行",
    r"顺利开展",
    r"圆满结束",
    r"纪实",
]

BODY_NON_ACTIVITY_PATTERNS = [
    r"活动回顾",
    r"顺利举办",
    r"顺利举行",
    r"圆满举办",
    r"成功举办",
    r"成功举行",
    r"圆满举行",
    r"顺利开展",
    r"圆满结束",
    r"正式发布",
    r"召开了",
    r"举行了",
    r"举办了",
    r"与会",
    r"活动现场",
    r"合影留念",
]

TIME_SIGNAL_PATTERNS = [
    r"\d{1,2}\s*月\s*\d{1,2}\s*日",
    r"\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日",
    r"\d{1,2}\s*[:：]\s*\d{2}",
    r"周[一二三四五六日天]",
    r"星期[一二三四五六日天]",
]


def _has_any(text: str, patterns: list[str]) -> bool:
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)


def classify_record_bucket(
    *,
    title: str | None,
    description: str | None = None,
    body_text: str | None = None,
    activity_time: str | None = None,
    location: str | None = None,
    activity_date: str | None = None,
    publish_time: int | None = None,
) -> tuple[str, str | None]:
    title_text = (title or "").strip()
    description_text = (description or "").strip()
    body = (body_text or "")[:4000]
    combined = "\n".join(part for part in [title_text, description_text, body] if part)

    has_activity_signal = _has_any(combined, STRONG_ACTIVITY_PATTERNS)
    has_recap_title = _has_any(title_text, TITLE_RECAP_PATTERNS)
    has_non_activity_title = _has_any(title_text, STRONG_NON_ACTIVITY_PATTERNS)
    has_non_activity_body = _has_any(combined, BODY_NON_ACTIVITY_PATTERNS)
    has_time_signal = bool(activity_time) or _has_any(combined, TIME_SIGNAL_PATTERNS)
    has_location = bool(location)

    if has_recap_title:
        return "non_activity", "title_recap_signal"

    if has_non_activity_title and not has_activity_signal:
        return "non_activity", "title_non_activity_signal"

    if has_non_activity_title and not has_time_signal and not has_location:
        return "non_activity", "title_signal_without_event_fields"

    if has_non_activity_body and not has_activity_signal and not has_time_signal:
        return "non_activity", "body_non_activity_signal"

    if publish_time and activity_date and re.match(r"^\d{4}-\d{2}-\d{2}$", activity_date):
        try:
            publish_date = datetime.fromtimestamp(publish_time).date()
            parsed_activity_date = datetime.strptime(activity_date, "%Y-%m-%d").date()
            if parsed_activity_date < publish_date and has_non_activity_body and not has_location:
                return "non_activity", "past_event_recap_signal"
        except ValueError:
            pass

    return "activity", None
