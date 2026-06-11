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

from src.governance.models import EvidenceRef, SignalCandidate, SignalPackage


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

    def __init__(self, base_dir: str | Path = "data/governance") -> None:
        self.base_dir = Path(base_dir)

    # ── helpers ──

    def _date_dir(self, signal_date: str | None = None) -> Path:
        label = signal_date or date.today().isoformat()
        return self.base_dir / "candidates" / label

    def _ensure_dir(self, path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)

    def _write_json(self, path: Path, data: object) -> None:
        self._ensure_dir(path.parent)
        path.write_text(
            json.dumps(data, default=_serialize, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _read_json(self, path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))

    # ── candidate ──

    def save_candidate(self, candidate: SignalCandidate) -> Path:
        raw = _serialize(candidate)
        path = self._date_dir() / f"{candidate.signal_id}.json"
        self._write_json(path, raw)
        return path

    def load_candidate(self, signal_id: str, signal_date: str | None = None) -> SignalCandidate:
        path = self._date_dir(signal_date) / f"{signal_id}.json"
        data = self._read_json(path)
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

    def save_package(self, package: SignalPackage) -> Path:
        raw = _serialize(package)
        path = self.base_dir / "packages" / date.today().isoformat() / f"{package.signal_id}.json"
        self._write_json(path, raw)
        return path

    def load_package(self, signal_id: str, signal_date: str | None = None) -> SignalPackage:
        label = signal_date or date.today().isoformat()
        path = self.base_dir / "packages" / label / f"{signal_id}.json"
        data = self._read_json(path)
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
            candidate=candidate,
            quality=data.get("quality", {}),
            data_gaps=data.get("data_gaps", []),
            acknowledged_gaps=data.get("acknowledged_gaps", []),
            panel=data.get("panel", {}),
            debate=data.get("debate", {}),
            risk=data.get("risk", {}),
            publish_review=data.get("publish_review", {}),
            evidence=pkg_evidence,
            html_report_path=data.get("html_report_path"),
        )
