from fastapi import status
from pydantic import BaseModel
from typing import Generic, TypeVar, Optional
from enum import Enum

T = TypeVar('T')


class ErrorCategory(str, Enum):
    AUTH = "auth"
    VALIDATION = "validation"
    NOT_FOUND = "not_found"
    SERVICE_STATE = "service_state"
    EXTERNAL_DEPENDENCY = "external_dependency"
    CONFIG = "config"
    INTERNAL = "internal"

class BaseResponse(BaseModel):
    code: int = 0
    message: str = "success"
    data: Optional[T] = None

def success_response(data=None, message="success"):
    return {
        "code": 0,
        "message": message,
        "data": data
    }

def error_response(code: int, message: str, data=None):
    return {
        "code": code,
        "message": message,
        "data": data,
        "category": ErrorCategory.INTERNAL.value,
    }


def categorized_error_response(code: int, message: str, category: ErrorCategory, data=None):
    return {
        "code": code,
        "message": message,
        "data": data,
        "category": category.value,
    }
from sqlalchemy import and_,or_
from core.models import Article
def format_search_kw(keyword: str):
    words = keyword.replace("-"," ").replace("|"," ").split(" ")
    rule = or_(*[Article.title.like(f"%{w}%") for w in words])
    return rule
