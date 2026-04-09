from __future__ import annotations

import hashlib
import re
from datetime import date


DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/135.0.0.0 Safari/537.36"
    )
}

DETAIL_TITLE_SELECTORS = [
    "h1",
    ".arti_title",
    ".Article_Title",
    ".article-title",
    ".title h1",
    ".title",
]

DETAIL_CONTENT_SELECTORS = [
    "#vsb_content",
    ".wp_articlecontent",
    ".Article_Content",
    ".article-content",
    ".content",
    ".detail-content",
    ".v_news_content",
]

FALLBACK_ITEM_SELECTORS = [
    ".col_news_list .news",
    ".news_list .news",
    ".listcon .jzlb",
    ".col_news_list .jzlb",
    ".jzlb",
    ".list_ul .list-item",
    "li.list-item",
    "li.wow.fadeInUp",
    ".news_list li",
    ".list_box li",
]

FALLBACK_TITLE_SELECTORS = [
    ".news_title a",
    ".btt3 a",
    ".title .name",
    "p.p1",
    "a",
]

FALLBACK_DATE_SELECTORS = [
    ".news_sj .textcon",
    ".p2",
    ".news_meta",
    ".fbsj4",
    ".sj",
    ".date",
    ".time",
    "span.date",
    "span",
]

CORE_DISPLAY_NAMES = {
    "library": "图书馆讲座",
    "graduate_school": "研究生院",
    "undergraduate_school": "本科生院",
    "graduate_calendar": "研究生活动",
    "international_college": "国际教育学院",
}

SKIP_TITLES = {
    "联系我们",
    "加入我们",
    "场地预约",
}

DATE_PATTERNS = [
    re.compile(r"(20\d{2})[-/.年](\d{1,2})[-/.月](\d{1,2})"),
    re.compile(r"(20\d{2})[-/.](\d{2})(\d{2})"),
    re.compile(r"(20\d{2})(\d{2})(\d{2})"),
]

YEARLESS_DATE_PATTERNS = [
    re.compile(r"(?<!\d)(\d{1,2})月(\d{1,2})日"),
]

CAMPUS_KEYWORDS = [
    ("紫金港", "紫金港"),
    ("玉泉", "玉泉"),
    ("西溪", "西溪"),
    ("华家池", "华家池"),
    ("之江", "之江"),
    ("海宁", "海宁"),
]

HIGH_SIGNAL_SOURCE_IDS = {
    "library",
    "undergraduate_school",
    "international_college",
}

WECHAT_CORE_SOURCE_MAP = {
    "library": "library",
    "graduate": "graduate_school",
    "undergraduate": "undergraduate_school",
}

WECHAT_ARTICLE_LOOKBACK_DAYS = 180
DELETED_STATUS = 1000


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", value).replace("\xa0", " ").strip()


def to_iso_date(value: str | None) -> str | None:
    text = clean_text(value)
    if not text:
        return None
    for pattern in DATE_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        year, month, day = match.groups()
        return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
    return None


def build_activity_id(source_id: str, detail_url: str, title: str) -> str:
    raw = f"{source_id}|{detail_url}|{title}".encode("utf-8")
    return hashlib.sha1(raw).hexdigest()


def parse_iso_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        from datetime import datetime

        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def extract_campus(value: str | None) -> str | None:
    text = clean_text(value)
    if not text:
        return None
    for keyword, campus in CAMPUS_KEYWORDS:
        if keyword in text:
            return campus
    return None


def to_iso_date_with_default_year(value: str | None, default_year: int | None) -> str | None:
    resolved = to_iso_date(value)
    if resolved:
        return resolved
    if not value or not default_year:
        return None

    text = clean_text(value)
    for pattern in YEARLESS_DATE_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        month, day = match.groups()
        try:
            target = date(default_year, int(month), int(day))
        except ValueError:
            continue
        return target.isoformat()
    return None


def is_evening_time(value: str | None) -> bool:
    text = clean_text(value)
    if not text:
        return False
    return bool(re.search(r"(晚上|18[:：]|19[:：]|20[:：])", text))


def normalize_title_key(value: str | None) -> str:
    text = clean_text(value).lower()
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", text)


def strip_prefix(value: str | None, prefixes: list[str]) -> str | None:
    text = clean_text(value)
    if not text:
        return None
    for prefix in prefixes:
        if text.startswith(prefix):
            return clean_text(text[len(prefix):])
    return text


def split_selectors(value: str | None) -> list[str]:
    if not value:
        return []
    return [selector.strip() for selector in value.split(",") if selector.strip()]


def merge_selectors(custom: str | None, fallbacks: list[str], *, custom_first: bool) -> list[str]:
    selectors = []
    if custom_first:
        selectors.extend(split_selectors(custom))
        selectors.extend(fallbacks)
    else:
        selectors.extend(fallbacks)
        selectors.extend(split_selectors(custom))

    merged = []
    seen = set()
    for selector in selectors:
        if selector in seen:
            continue
        seen.add(selector)
        merged.append(selector)
    return merged


def dedupe_exact_items(items: list[dict]) -> list[dict]:
    deduped = []
    seen = set()
    for item in items:
        dedupe_key = (item.get("source_url"), item.get("title"), item.get("activity_date"))
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        deduped.append(item)
    return deduped
