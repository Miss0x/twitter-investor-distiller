"""Governance artifact repository.

GovernanceRepository handles JSON artifact persistence under
data/governance/YYYY-MM-DD/{signal_id}.json, keeping the storage
layer decoupled from models and gate logic.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from datetime import date, datetime, timezone
from pathlib import Path

from src.governance.models import AcknowledgedGap, DataGap, EvidenceRef, SignalCandidate, SignalPackage


def _serialize(obj):
    """Custom JSON serializer for dataclass types and datetime."""
    if hasattr(obj, "__dataclass_fields__"):
        return {k: _serialize(v) for k, v in asdict(obj).items()}
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, Path):
        return str(obj)
    return obj


class GovernanceRepository:
    """Read/write governance artifacts to the JSON artifact store."""

    _ALLOWED_KINDS = {
        "candidates",
        "data_gaps",
        "acknowledged_gaps",
        "quality",
        "panel",
        "debate",
        "risk",
        "publish",
        "packages",
        "runs",
        "audit",
    }

    def __init__(self, base_dir: str | Path = "data/governance") -> None:
        self.base_dir = Path(base_dir)

    # ── helpers ──

    def _date_dir(self, signal_date: str | None = None) -> Path:
        label = signal_date or date.today().isoformat()
        return self.base_dir / "candidates" / label

    def _artifact_path(self, kind: str, signal_id: str, signal_date: str | None = None) -> Path:
        if kind not in self._ALLOWED_KINDS:
            raise ValueError(f"Unsupported governance artifact kind: {kind}")
        if any(part in {"..", "", "."} for part in Path(signal_id).parts):
            raise ValueError(f"Invalid signal_id for artifact path: {signal_id}")
        if kind == "runs":
            return self.base_dir / kind / f"{signal_id}.json"
        label = signal_date or date.today().isoformat()
        return self.base_dir / kind / label / f"{signal_id}.json"

    def _ensure_dir(self, path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)

    def _write_json(self, path: Path, data: object) -> None:
        self._ensure_dir(path.parent)
        path.write_text(
            json.dumps(data, default=_serialize, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _read_json(self, path: Path):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid governance JSON artifact: {path}") from exc

    def save_artifact(self, kind: str, signal_id: str, data: object, signal_date: str | None = None) -> Path:
        path = self._artifact_path(kind, signal_id, signal_date)
        self._write_json(path, data)
        return path

    def load_artifact(self, kind: str, signal_id: str, signal_date: str | None = None):
        return self._read_json(self._artifact_path(kind, signal_id, signal_date))

    def audit_path(self, signal_id: str, signal_date: str | None = None) -> Path:
        if any(part in {"..", "", "."} for part in Path(signal_id).parts):
            raise ValueError(f"Invalid signal_id for audit path: {signal_id}")
        label = signal_date or date.today().isoformat()
        return self.base_dir / "audit" / label / f"{signal_id}.jsonl"

    def append_audit_event(self, signal_id: str, event: dict, signal_date: str | None = None) -> Path:
        path = self.audit_path(signal_id, signal_date=signal_date)
        self._ensure_dir(path.parent)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, default=_serialize, ensure_ascii=False) + "\n")
        return path

    # ── candidate ──

    def save_candidate(self, candidate: SignalCandidate) -> Path:
        return self.save_artifact("candidates", candidate.signal_id, candidate)

    def load_candidate(self, signal_id: str, signal_date: str | None = None) -> SignalCandidate:
        data = self.load_artifact("candidates", signal_id, signal_date)
        evidence = [EvidenceRef(**e) for e in data.get("evidence", [])]
        return SignalCandidate(
            signal_id=data["signal_id"],
            ticker=data["ticker"],
            asset_name=data.get("asset_name"),
            generated_at=data.get("generated_at", ""),
            source_tweet_ids=data.get("source_tweet_ids", []),
            source_usernames=data.get("source_usernames", []),
            stance=data.get("stance"),
            signal_score=data.get("signal_score"),
            confidence=data.get("confidence"),
            evidence=evidence,
            raw_payload=data.get("raw_payload", {}),
        )

    # ── package ──

    def _load_data_gaps(self, raw: list[dict]) -> list[DataGap]:
        return [g if isinstance(g, DataGap) else DataGap(**g) for g in raw]

    def _load_acknowledged_gaps(self, raw: list[dict]) -> list[AcknowledgedGap]:
        return [a if isinstance(a, AcknowledgedGap) else AcknowledgedGap(**a) for a in raw]

    def save_package(self, package: SignalPackage) -> Path:
        return self.save_artifact("packages", package.signal_id, package)

    def load_package(self, signal_id: str, signal_date: str | None = None) -> SignalPackage:
        data = self.load_artifact("packages", signal_id, signal_date)
        candidate_data = data.get("candidate") or {}
        cand_evidence = [EvidenceRef(**e) for e in candidate_data.get("evidence", [])]
        candidate = SignalCandidate(
            signal_id=candidate_data.get("signal_id", signal_id),
            ticker=candidate_data.get("ticker", ""),
            asset_name=candidate_data.get("asset_name"),
            generated_at=candidate_data.get("generated_at", ""),
            source_tweet_ids=candidate_data.get("source_tweet_ids", []),
            source_usernames=candidate_data.get("source_usernames", []),
            stance=candidate_data.get("stance"),
            signal_score=candidate_data.get("signal_score"),
            confidence=candidate_data.get("confidence"),
            evidence=cand_evidence,
            raw_payload=candidate_data.get("raw_payload", {}),
        )
        pkg_evidence = [EvidenceRef(**e) for e in data.get("evidence", [])]
        return SignalPackage(
            signal_id=data.get("signal_id", signal_id),
            ticker=data.get("ticker", ""),
            generated_at=data.get("generated_at", ""),
            publish_status=data.get("publish_status", "failed"),
            summary=data.get("summary", ""),
            candidate=candidate if candidate_data else None,
            quality=data.get("quality", {}),
            data_gaps=self._load_data_gaps(data.get("data_gaps", [])),
            acknowledged_gaps=self._load_acknowledged_gaps(data.get("acknowledged_gaps", [])),
            panel=data.get("panel", {}),
            debate=data.get("debate", {}),
            risk=data.get("risk", {}),
            publish_review=data.get("publish_review", {}),
            evidence=pkg_evidence,
            html_report_path=data.get("html_report_path"),
        )

    def latest_package_path(self) -> Path | None:
        packages_dir = self.base_dir / "packages"
        if not packages_dir.exists():
            return None
        paths = sorted(packages_dir.glob("*/*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        return paths[0] if paths else None

    def load_latest_package(self) -> SignalPackage | None:
        path = self.latest_package_path()
        if path is None:
            return None
        signal_date = path.parent.name
        signal_id = path.stem
        return self.load_package(signal_id, signal_date=signal_date)

    def latest_package_path_for_signal(self, signal_id: str) -> Path | None:
        packages_dir = self.base_dir / "packages"
        if not packages_dir.exists():
            return None
        paths = sorted(packages_dir.glob(f"*/{signal_id}.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        return paths[0] if paths else None

    def load_latest_package_for_signal(self, signal_id: str) -> SignalPackage | None:
        path = self.latest_package_path_for_signal(signal_id)
        if path is None:
            return None
        return self.load_package(signal_id, signal_date=path.parent.name)

    def list_latest_packages(self, limit: int = 20) -> list[SignalPackage]:
        packages_dir = self.base_dir / "packages"
        if not packages_dir.exists():
            return []
        paths = sorted(packages_dir.glob("*/*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        packages: list[SignalPackage] = []
        for path in paths[:limit]:
            packages.append(self.load_package(path.stem, signal_date=path.parent.name))
        return packages
