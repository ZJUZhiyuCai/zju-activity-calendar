from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

import requests
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from core.print import print_warning


LLM_MODEL = os.getenv("ACTIVITY_LLM_MODEL", "GLM-5")
LLM_TIMEOUT_SECONDS = int(os.getenv("ACTIVITY_LLM_TIMEOUT_SECONDS", "45"))
LLM_MAX_INPUT_CHARS = int(os.getenv("ACTIVITY_LLM_MAX_INPUT_CHARS", "8000"))


class ActivityLLMResult(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    is_activity: bool = Field(description="是否是一条可加入活动日历的校园活动")
    needs_review: bool = Field(default=False, description="信息不足或模型不确定时为 true")
    activity_date: str | None = Field(default=None, description="YYYY-MM-DD")
    activity_time: str | None = Field(default=None, description="原文中的完整时间表达")
    campus: str | None = Field(default=None, description="紫金港/玉泉/西溪/华家池/之江/海宁/线上/其他")
    location: str | None = None
    speaker: str | None = None
    speaker_title: str | None = None
    speaker_intro: str | None = None
    organizer: str | None = None
    activity_type: str | None = None
    bonus_type: str | None = Field(default=None, description="none/second_class/aesthetic/both/unknown")
    bonus_detail: str | None = None
    summary: str | None = Field(default=None, description="80 字以内中文摘要")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    @field_validator("activity_date")
    @classmethod
    def validate_activity_date(cls, value: str | None) -> str | None:
        if not value:
            return None
        try:
            datetime.strptime(value, "%Y-%m-%d")
        except ValueError as exc:
            raise ValueError("activity_date must use YYYY-MM-DD") from exc
        return value

    @field_validator("bonus_type")
    @classmethod
    def validate_bonus_type(cls, value: str | None) -> str | None:
        if not value:
            return None
        allowed = {"none", "second_class", "aesthetic", "both", "unknown"}
        if value not in allowed:
            raise ValueError(f"bonus_type must be one of {sorted(allowed)}")
        return value


@dataclass
class ActivityLLMParseOutcome:
    result: ActivityLLMResult | None
    pending: bool
    error: str | None = None
    raw_response: str | None = None


def is_activity_llm_enabled() -> bool:
    return os.getenv("ACTIVITY_LLM_ENABLED", "false").lower() in {"1", "true", "yes", "on"}


def _get_api_key() -> str | None:
    return os.getenv("DS_API_KEY") or os.getenv("XB_API_KEY")


def _resolve_api_url(raw_url: str) -> str:
    candidate = (raw_url or "").strip()
    if not candidate:
        return ""

    parsed = urlparse(candidate)
    if parsed.scheme and parsed.netloc:
        path = parsed.path.rstrip("/")
        if path.endswith("/chat/completions"):
            return candidate
        if path.endswith("/v1"):
            return candidate.rstrip("/") + "/chat/completions"
        if path in {"", "/"}:
            return candidate.rstrip("/") + "/chat/completions"
    return candidate


def _strip_json_fence(text: str) -> str:
    candidate = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", candidate, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        candidate = fenced.group(1).strip()
    if candidate.startswith("{") and candidate.endswith("}"):
        return candidate
    start = candidate.find("{")
    end = candidate.rfind("}")
    if start >= 0 and end > start:
        return candidate[start : end + 1]
    return candidate


def _load_result(raw_text: str) -> ActivityLLMResult:
    payload = json.loads(_strip_json_fence(raw_text))
    return ActivityLLMResult.model_validate(payload)


def _build_messages(*, title: str, description: str, body_text: str, publish_year: int | None) -> list[dict[str, str]]:
    content = body_text[:LLM_MAX_INPUT_CHARS]
    system_prompt = (
        "你是浙江大学校园活动信息抽取器。只返回一个 JSON 对象，不要 Markdown，不要解释。"
        "只有仍可报名、可参加、即将举行或明确预告的活动才能 is_activity=true。"
        "活动报道、新闻稿、总结、回顾、纪实，或标题/正文出现“顺利举办、顺利举行、成功举办、圆满举办、活动回顾”等已发生信号时，"
        "即使文中包含讲座、分享会、论坛等词，也必须 is_activity=false。"
        "无法确定的字段填 null；不是活动则 is_activity=false。"
        "activity_date 必须是 YYYY-MM-DD；如果原文只有月日，优先使用 publish_year。"
        "bonus_type 只能是 none、second_class、aesthetic、both、unknown。"
        "校区只在原文有明确线索时填写。summary 用中文，不超过 80 字。"
    )
    user_payload = {
        "publish_year": publish_year,
        "title": title,
        "description": description,
        "article_text": content,
        "required_json_shape": {
            "is_activity": True,
            "needs_review": False,
            "activity_date": "YYYY-MM-DD 或 null",
            "activity_time": "原文时间 或 null",
            "campus": "紫金港/玉泉/西溪/华家池/之江/海宁/线上/其他/null",
            "location": "地点 或 null",
            "speaker": "主讲人/嘉宾 或 null",
            "speaker_title": "职称头衔 或 null",
            "speaker_intro": "简介 或 null",
            "organizer": "主办方 或 null",
            "activity_type": "讲座/论坛/分享会/训练营/比赛/展览/其他",
            "bonus_type": "none/second_class/aesthetic/both/unknown",
            "bonus_detail": "加分说明 或 null",
            "summary": "80字以内摘要 或 null",
            "confidence": 0.0,
        },
    }
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
    ]


def parse_activity_with_llm(
    *,
    title: str,
    description: str = "",
    body_text: str = "",
    publish_year: int | None = None,
    max_retries: int = 2,
) -> ActivityLLMParseOutcome:
    api_key = _get_api_key()
    if not api_key:
        return ActivityLLMParseOutcome(result=None, pending=True, error="DS_API_KEY / XB_API_KEY is not configured")
    api_url = _resolve_api_url(os.getenv("ACTIVITY_LLM_API_URL", ""))
    if not api_url:
        return ActivityLLMParseOutcome(result=None, pending=True, error="ACTIVITY_LLM_API_URL is not configured")

    messages = _build_messages(
        title=title,
        description=description,
        body_text=body_text,
        publish_year=publish_year,
    )
    last_error = None
    last_raw = None
    attempts = max_retries + 1

    for attempt in range(1, attempts + 1):
        try:
            response = requests.post(
                api_url,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}",
                },
                json={
                    "model": LLM_MODEL,
                    "messages": messages,
                    "temperature": 0,
                    "response_format": {"type": "json_object"},
                },
                timeout=LLM_TIMEOUT_SECONDS,
            )
            if not response.ok:
                body_prefix = response.text[:500].replace("\n", " ")
                raise requests.HTTPError(
                    f"{response.status_code} from LLM API: {body_prefix}",
                    response=response,
                )
            data: dict[str, Any] = response.json()
            last_raw = data["choices"][0]["message"]["content"]
            return ActivityLLMParseOutcome(result=_load_result(last_raw), pending=False, raw_response=last_raw)
        except (requests.RequestException, KeyError, IndexError, json.JSONDecodeError, ValidationError, ValueError) as exc:
            last_error = str(exc)
            if attempt < attempts:
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "上一次返回无法解析或不符合字段约束。请只返回合法 JSON，"
                            "不要包含 Markdown 或额外文字；无法确定的字段填 null。"
                        ),
                    }
                )

    print_warning(f"LLM 活动解析失败，标记待处理: {last_error}")
    return ActivityLLMParseOutcome(result=None, pending=True, error=last_error, raw_response=last_raw)
