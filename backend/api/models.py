"""Pydantic models for the API."""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field, field_validator


class AnalyzeRequest(BaseModel):
    project_path: str
    ignore_dirs: Optional[List[str]] = None

    @field_validator("ignore_dirs", mode="before")
    @classmethod
    def _validate_ignore_dirs(cls, v: Any) -> Optional[List[str]]:
        if v is None:
            return v
        result = []
        for entry in v:
            if not isinstance(entry, str) or not entry.strip():
                continue
            # Reject anything that looks like a path — only simple names allowed.
            if ".." in entry or "/" in entry or "\\" in entry:
                raise ValueError(
                    f"ignore_dirs entries must be simple directory names, not paths: {entry!r}"
                )
            result.append(entry.strip())
        return result or None


class TaskStatus(BaseModel):
    task_id: str
    status: Literal["pending", "processing", "completed", "failed"]
    progress: int = Field(default=0, ge=0, le=100)
    message: str = ""
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
