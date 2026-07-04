"""Pydantic API schemas."""

from typing import Optional
from pydantic import BaseModel


class SettingsUpdate(BaseModel):
    api_key: Optional[str] = None
    model: Optional[str] = None
    theme: Optional[str] = None
    setup_complete: Optional[bool] = None


class SettingsTestRequest(BaseModel):
    api_key: Optional[str] = None
    model: Optional[str] = None


class ScanRequest(BaseModel):
    path: str
    name: Optional[str] = None
    run_in_background: bool = False
    scan_type: Optional[str] = "ai"  # "ai" or "script"


class QueryRequest(BaseModel):
    query: str


class OpenFileRequest(BaseModel):
    path: str


class DeletePreviewRequest(BaseModel):
    paths: list[str]


class DeleteRequest(BaseModel):
    paths: list[str]
    dry_run: bool = False


class EmptyDirectoriesDeleteRequest(BaseModel):
    paths: list[str]


class RenameApplyRequest(BaseModel):
    paths: list[str]


class ReportSaveRequest(BaseModel):
    name: str
