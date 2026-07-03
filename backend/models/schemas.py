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


class QueryRequest(BaseModel):
    query: str


class OpenFileRequest(BaseModel):
    path: str


class DeletePreviewRequest(BaseModel):
    paths: list[str]


class DeleteRequest(BaseModel):
    paths: list[str]
    dry_run: bool = False


class ReportSaveRequest(BaseModel):
    name: str
