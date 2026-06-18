from typing import Any

from pydantic import BaseModel


class ErrorResponse(BaseModel):
    error: str
    details: Any = None


class MessageResponse(BaseModel):
    message: str


class PaginatedResponse(BaseModel):
    items: list[Any]
    total: int
    page: int
    per_page: int
    pages: int
