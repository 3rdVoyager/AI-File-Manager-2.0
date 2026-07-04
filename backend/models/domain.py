"""Domain dataclasses."""

from dataclasses import dataclass, field, asdict
from typing import Any


VALID_ACTIONS = {"Keep", "Delete", "Archive", "Review"}
VALID_LIFECYCLES = {"Active", "Dormant", "Archived", "Transient", "Unknown"}
TRASH_CONFIDENCE_TIERS = {"high": 70, "medium": 50, "low": 30}


@dataclass
class AnalysisResult:
    file: str = ""
    path: str = ""
    summary: str = ""
    category: str = ""
    subcategory: str = ""
    tags: list = field(default_factory=list)
    project: str = ""
    importance: int = 5
    sentimental_value: int = 1
    confidence: int = 50
    lifecycle: str = "Unknown"
    action: str = "Review"
    reasoning: str = ""
    suggested_filename: str = ""
    rename_reason: str = ""
    rename_confidence: int = 0
    requires_review: bool = False
    duplicate_group: str = ""
    prefiltered: bool = False
    size_bytes: int = 0
    size_human: str = ""
    extension: str = ""
    modified: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ScanProgress:
    scan_id: int
    status: str = "pending"
    progress: float = 0.0
    files_found: int = 0
    files_processed: int = 0
    current_file: str = ""
    error: str = ""
    cancel_requested: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
