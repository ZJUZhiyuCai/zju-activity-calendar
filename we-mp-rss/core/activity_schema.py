from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator


class ActivityRecord(BaseModel):
    model_config = ConfigDict(extra="allow", str_strip_whitespace=True)

    id: str
    title: str
    college_id: str
    college_name: str
    activity_type: str
    activity_date: str
    source_url: str
    source_type: str
    source_channel: str = "website"
    speaker: Optional[str] = None
    speaker_title: Optional[str] = None
    speaker_intro: Optional[str] = None
    activity_time: Optional[str] = None
    location: Optional[str] = None
    organizer: Optional[str] = None
    description: Optional[str] = None
    cover_image: Optional[str] = None
    registration_required: bool = False
    registration_link: Optional[str] = None
    raw_date_text: Optional[str] = None
    mp_name: Optional[str] = None
    publish_time: Optional[int] = None

    @field_validator(
        "id",
        "title",
        "college_id",
        "college_name",
        "activity_type",
        "activity_date",
        "source_url",
        "source_type",
        "source_channel",
    )
    @classmethod
    def validate_required_strings(cls, value: str) -> str:
        if not value:
            raise ValueError("must not be empty")
        return value

    @field_validator("activity_date")
    @classmethod
    def validate_activity_date(cls, value: str) -> str:
        if len(value) != 10 or value[4] != "-" or value[7] != "-":
            raise ValueError("must use YYYY-MM-DD")
        return value


def validate_activity_record(item: dict[str, Any]) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    try:
        validated = ActivityRecord.model_validate(item)
    except ValidationError as exc:
        return None, exc.errors()[0]["msg"]
    return validated.model_dump(), None
