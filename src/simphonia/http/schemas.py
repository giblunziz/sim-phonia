from typing import Any

from pydantic import BaseModel, Field


class BusDTO(BaseModel):
    name: str
    command_count: int


class CommandDTO(BaseModel):
    code: str
    description: str


class DispatchRequest(BaseModel):
    code: str = Field(..., min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)


class DispatchResponse(BaseModel):
    result: Any


class ErrorBody(BaseModel):
    type: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorBody
