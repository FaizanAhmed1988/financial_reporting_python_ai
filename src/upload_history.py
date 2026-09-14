"""
src/upload_history.py
=====================
UP4 — Upload History / Audit Trail + file-level duplicate prevention.

Every upload attempt is recorded, whether or not it ended in a dataset: what
file, which sheet, what the detector thought it was, how validation ended, what
the user chose to do with it, and what came out. The trail is the answer to
"where did this number come from?" — the question an accountant asks first.

FILE-LEVEL DUPLICATE PREVENTION
-------------------------------
UP3's `detect_duplicates()` compares transaction ROWS. This module works one
level up: it fingerprints the uploaded bytes (SHA-256) so re-uploading the same
file is caught before any parsing happens, and reports when and how that file
was handled last time. Content is fingerprinted, not the filename — a renamed
copy is still recognised.

Neither check blocks the user. Both report, and the user decides.

ARCHITECTURE COMPLIANCE
-----------------------
- NO streamlit import — pure logic, headlessly testable, like coa_mapper,
  validation_engine and dataset_manager. Rendering lives in file_upload.py.
- Persists to `data/processed/upload_history.json`, alongside the UP2 mapping
  store. That path is gitignored, so an audit trail of real financial uploads
  never reaches the repository.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
HISTORY_PATH = PROJECT_ROOT / "data" / "processed" / "upload_history.json"

HISTORY_VERSION = 1
MAX_ENTRIES = 500

# Outcome vocabulary
OUTCOME_PREVIEWED = "Previewed"
OUTCOME_BLOCKED = "Blocked by validation"
OUTCOME_PROCESSED = "Processed into dataset"
OUTCOME_FAILED = "Failed"


# ============================================================
# 1. FINGERPRINTING
# ============================================================

def fingerprint(data: bytes) -> str:
    """SHA-256 of the uploaded bytes — identifies content, not filename."""
    return hashlib.sha256(data).hexdigest()


def short_fingerprint(digest: str) -> str:
    return (digest or "")[:12]


# ============================================================
# 2. ENTRY
# ============================================================

@dataclass
class HistoryEntry:
    """One recorded upload action."""
    timestamp: str
    file_name: str
    file_hash: str
    sheet: Optional[str] = None
    detected_type: Optional[str] = None
    slot: Optional[str] = None
    confidence: Optional[float] = None
    rows: int = 0
    columns: int = 0
    validation_status: Optional[str] = None
    errors: int = 0
    warnings: int = 0
    mode: Optional[str] = None
    dataset_name: Optional[str] = None
    outcome: str = OUTCOME_PREVIEWED
    rows_appended: Optional[int] = None
    duplicates_excluded: Optional[int] = None
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def new_entry(**kwargs) -> HistoryEntry:
    """Build an entry stamped with the current UTC time."""
    kwargs.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
    return HistoryEntry(**kwargs)


# ============================================================
# 3. STORE
# ============================================================

def _empty_store() -> Dict[str, Any]:
    return {"version": HISTORY_VERSION, "updated_at": None, "entries": []}


def load_history(path: Optional[Path] = None) -> Dict[str, Any]:
    """Load the audit trail. A missing or corrupt file yields an empty trail
    rather than blocking an upload."""
    p = Path(path) if path is not None else HISTORY_PATH
    if not p.exists():
        return _empty_store()
    try:
        with open(p, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (json.JSONDecodeError, OSError):
        return _empty_store()
    if not isinstance(data, dict):
        return _empty_store()
    data.setdefault("version", HISTORY_VERSION)
    data.setdefault("entries", [])
    data.setdefault("updated_at", None)
    return data


def save_history(store: Dict[str, Any], path: Optional[Path] = None) -> Path:
    """Persist the trail, newest entries kept, oldest trimmed past MAX_ENTRIES."""
    p = Path(path) if path is not None else HISTORY_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    store = dict(store)
    store["updated_at"] = datetime.now(timezone.utc).isoformat()
    store["entries"] = list(store.get("entries", []))[-MAX_ENTRIES:]
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(store, fh, indent=2, ensure_ascii=False)
    return p


def record(store: Dict[str, Any], entry: HistoryEntry) -> Dict[str, Any]:
    """Append an entry. The trail is append-only — nothing is ever rewritten."""
    store = dict(store)
    store["entries"] = list(store.get("entries", [])) + [entry.to_dict()]
    return store


# ============================================================
# 4. DUPLICATE PREVENTION
# ============================================================

@dataclass
class PriorUpload:
    """What the trail knows about a file that has been seen before."""
    entries: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def seen(self) -> bool:
        return bool(self.entries)

    @property
    def processed_entries(self) -> List[Dict[str, Any]]:
        return [e for e in self.entries if e.get("outcome") == OUTCOME_PROCESSED]

    @property
    def was_processed(self) -> bool:
        return bool(self.processed_entries)

    def message(self) -> str:
        """Human-readable summary of what happened to this file before."""
        if not self.seen:
            return ""
        last = self.entries[-1]
        when = str(last.get("timestamp", ""))[:19].replace("T", " ")
        if self.was_processed:
            done = self.processed_entries[-1]
            return (
                f"This exact file was already uploaded on {when} UTC and processed "
                f"into dataset **{done.get('dataset_name')}** "
                f"({done.get('mode')}). Processing it again will create a second, "
                "separate dataset — it will not overwrite the first."
            )
        return (
            f"This exact file was uploaded before ({len(self.entries)} time(s), last "
            f"on {when} UTC) but was never processed into a dataset "
            f"(last outcome: {last.get('outcome')})."
        )


def find_prior_uploads(store: Dict[str, Any], file_hash: str,
                       sheet: Optional[str] = None) -> PriorUpload:
    """
    Every prior entry for this exact file content. When `sheet` is given, only
    entries for that sheet count — one workbook legitimately yields several
    datasets from different sheets, which is not a duplicate.
    """
    if not file_hash:
        return PriorUpload()
    hits = [
        e for e in store.get("entries", [])
        if e.get("file_hash") == file_hash
        and (sheet is None or e.get("sheet") == sheet)
    ]
    return PriorUpload(entries=hits)


# ============================================================
# 5. PRESENTATION
# ============================================================

HISTORY_COLUMNS = [
    ("timestamp", "When (UTC)"),
    ("file_name", "File"),
    ("sheet", "Sheet"),
    ("detected_type", "Detected As"),
    ("rows", "Rows"),
    ("validation_status", "Validation"),
    ("errors", "Errors"),
    ("warnings", "Warnings"),
    ("mode", "Mode"),
    ("outcome", "Outcome"),
    ("dataset_name", "Dataset"),
    ("rows_appended", "Rows Added"),
    ("duplicates_excluded", "Dupes Excluded"),
    ("file_hash", "Fingerprint"),
]


def to_dataframe(store: Dict[str, Any], newest_first: bool = True) -> pd.DataFrame:
    """Render the trail as a display-ready table."""
    entries = list(store.get("entries", []))
    if not entries:
        return pd.DataFrame(columns=[label for _, label in HISTORY_COLUMNS])

    df = pd.DataFrame(entries)
    for key, _ in HISTORY_COLUMNS:
        if key not in df.columns:
            df[key] = None
    df = df[[key for key, _ in HISTORY_COLUMNS]].copy()
    df["timestamp"] = df["timestamp"].astype(str).str[:19].str.replace("T", " ", regex=False)
    df["file_hash"] = df["file_hash"].astype(str).str[:12]
    df.columns = [label for _, label in HISTORY_COLUMNS]
    if newest_first:
        df = df.iloc[::-1].reset_index(drop=True)
    return df


def summarise(store: Dict[str, Any]) -> Dict[str, int]:
    """Headline counts for the audit trail."""
    entries = store.get("entries", [])
    return {
        "Total Uploads": len(entries),
        "Processed": sum(1 for e in entries if e.get("outcome") == OUTCOME_PROCESSED),
        "Blocked": sum(1 for e in entries if e.get("outcome") == OUTCOME_BLOCKED),
        "Distinct Files": len({e.get("file_hash") for e in entries if e.get("file_hash")}),
    }
