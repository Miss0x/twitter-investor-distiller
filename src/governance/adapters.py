"""Adapters that convert existing project artifacts into SignalCandidate objects."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from src.governance.models import EvidenceRef, SignalCandidate
from src.governance.repository import GovernanceRepository


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value if v is not None and str(v)]
    if isinstance(value, tuple | set):
        return [str(v) for v in value if v is not None and str(v)]
    text = str(value).strip()
    return [text] if text else []


def _first_text(*values: Any) -> str | None:
    for value in values:
        if value is None:
            continue
        if isinstance(value, list) and value:
            return str(value[0]).strip() or None
        text = str(value).strip()
        if text:
            return text
    return None


def _stable_signal_id(item: dict, ticker: str) -> str:
    seed = "|".join(
        [
            ticker,
            str(item.get("signal_id") or item.get("id") or item.get("tweet_id") or ""),
            str(item.get("analyzed_at") or item.get("created_at") or item.get("timestamp") or ""),
            str(item.get("text") or item.get("content") or ""),
        ]
    )
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]
    return f"SIG-{ticker}-{digest}"


def _parse_score(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def candidate_from_analysis_item(item: dict, source_file: str | None = None) -> SignalCandidate:
    """Convert one existing analyzed pipeline item into a SignalCandidate."""
    ticker = _first_text(item.get("ticker"), item.get("symbol"), item.get("mentioned_stocks")) or "UNKNOWN"
    signal_id = str(item.get("signal_id") or _stable_signal_id(item, ticker))
    tweet_ids = _as_list(item.get("source_tweet_ids") or item.get("tweet_ids") or item.get("tweet_id") or item.get("id"))
    usernames = _as_list(item.get("source_usernames") or item.get("username") or item.get("author"))
    generated_at = str(
        item.get("generated_at")
        or item.get("analyzed_at")
        or item.get("created_at")
        or datetime.now(timezone.utc).isoformat()
    )

    evidence: list[EvidenceRef] = []
    text = _first_text(item.get("text"), item.get("content"), item.get("tweet_text"))
    if text or tweet_ids:
        evidence.append(
            EvidenceRef(
                source_type="tweet",
                source_id=tweet_ids[0] if tweet_ids else signal_id,
                url=_first_text(item.get("url"), item.get("tweet_url")),
                title="Tweet evidence",
                excerpt=text or "Tweet reference exists",
                timestamp=_first_text(item.get("created_at"), item.get("timestamp")),
                reliability=0.7,
            )
        )

    analysis_text = _first_text(item.get("analysis"), item.get("summary"), item.get("reasoning"), item.get("llm_output"))
    if analysis_text:
        evidence.append(
            EvidenceRef(
                source_type="analysis",
                source_id=f"{signal_id}-analysis",
                title="Analysis evidence",
                excerpt=analysis_text,
                timestamp=_first_text(item.get("analyzed_at"), item.get("generated_at")),
                reliability=0.7,
            )
        )

    for price_ref in item.get("price_evidence", []) or []:
        if isinstance(price_ref, dict):
            evidence.append(EvidenceRef(source_type="price", **{k: v for k, v in price_ref.items() if k != "source_type"}))

    raw_payload = dict(item)
    if source_file:
        raw_payload["source_file"] = source_file
    if ticker == "UNKNOWN":
        raw_payload["governance_adapter_warning"] = "ticker_missing"

    return SignalCandidate(
        signal_id=signal_id,
        ticker=ticker,
        asset_name=_first_text(item.get("asset_name"), item.get("company_name"), item.get("name")),
        generated_at=generated_at,
        source_tweet_ids=tweet_ids,
        source_usernames=usernames,
        stance=_first_text(item.get("stance"), item.get("action"), item.get("sentiment")),
        signal_score=_parse_score(item.get("signal_score") or item.get("score") or item.get("confidence_score")),
        confidence=_first_text(item.get("confidence"), item.get("confidence_label")),
        evidence=evidence,
        raw_payload=raw_payload,
    )


def candidate_from_payload(payload: dict, repo: GovernanceRepository | None = None) -> SignalCandidate:
    """Convert a PipelineTask payload into a SignalCandidate."""
    if "candidate" in payload:
        candidate = payload["candidate"]
        if isinstance(candidate, SignalCandidate):
            return candidate
        if isinstance(candidate, dict):
            evidence = [EvidenceRef(**e) if isinstance(e, dict) else e for e in candidate.get("evidence", [])]
            return SignalCandidate(**{**candidate, "evidence": evidence})
        raise ValueError("candidate payload must be a SignalCandidate or dict")

    if "analysis_item" in payload:
        return candidate_from_analysis_item(payload["analysis_item"], source_file=payload.get("source_file"))

    if "signal_id" in payload:
        repo = repo or GovernanceRepository()
        return repo.load_candidate(str(payload["signal_id"]), signal_date=payload.get("signal_date"))

    raise ValueError("governance payload requires candidate, analysis_item, or signal_id")
