"""Append-only log of model predictions for later, honest evaluation."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Optional

LOG_DIR = Path("data_files/pick_log")


def source_version(paths: Iterable[Path]) -> str:
    """Short hash of source files, so logged picks show which logic made them."""
    digest = hashlib.sha256()
    for path in sorted(Path(p) for p in paths):
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes().replace(b"\r\n", b"\n"))
    return digest.hexdigest()[:10]


def append_pick_log(
    records: Iterable[dict],
    log_dir: Path = LOG_DIR,
    now: Optional[datetime] = None,
) -> Optional[Path]:
    """Append records, one JSON object per line, to this month's log file."""
    records = list(records)
    if not records:
        return None

    stamp = now or datetime.now(timezone.utc)
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / f"{stamp:%Y-%m}.jsonl"
    logged_at = stamp.isoformat()

    with path.open("a", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps({"logged_at": logged_at, **record}, ensure_ascii=False) + "\n")
    return path


def read_pick_log(log_dir: Path = LOG_DIR) -> List[dict]:
    """Read every logged record, oldest file first."""
    log_dir = Path(log_dir)
    rows: List[dict] = []
    if not log_dir.exists():
        return rows
    for path in sorted(log_dir.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows
