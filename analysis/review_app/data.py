"""Session-grouped sample builder for the HW4 review interface.

Cartwheel records one Langfuse trace per user turn, so a multi-turn
conversation is spread across several traces. The reviewer needs the whole
conversation in one place: in the live store 81 of 322 sessions carry more
than one trace, and their failures are frequently only visible across turns
(a request dropped in turn 1 and never answered by turn 3).

``fetch_traces`` flattens a subset of the trace metadata into ``meta`` and
that subset omits the session id, so this module reads ``cartwheel.session_id``
from the full ``metadata`` mapping instead.

The output shape is a list of session records:

    {session_id, role, user_id, scenario_id, prompt_version,
     traces: [{trace_id, timestamp, permalink, features, segments}, ...],
     features: {...aggregated...}, flags: [...]}

Traces inside a session are ordered by timestamp, which is the order the
shopper actually experienced them.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
OFFLINE_EXPORT = REPO_ROOT / "traces" / "support_traces.json"

# Percentiles measured over the live store; a trace outside these is flagged in
# the session header so the reviewer knows it is structurally unusual before
# reading it. Recomputed from the loaded sample rather than hardcoded when the
# sample is large enough to be meaningful.
_FLAG_FEATURES = ("turn_count", "tool_call_count", "tokens")

META_SESSION = "cartwheel.session_id"
META_ROLE = "cartwheel.user_role"
META_USER = "cartwheel.user_id"
META_SCENARIO = "cartwheel.scenario_id"
META_PROMPT = "cartwheel.prompt_version"


def _langfuse_host() -> str:
    return os.getenv("LANGFUSE_HOST", "http://localhost:3000").rstrip("/")


def _project_id() -> str:
    return os.getenv("LANGFUSE_PROJECT_ID", "cartwheel-dev")


def permalink(trace_id: str) -> str:
    """Return the Langfuse UI URL for a trace.

    ``fetch_traces`` leaves ``permalink`` as None, so the interface builds the
    URL from the host and project. The reviewer opens this to check a saved
    score against the canonical store.
    """
    return f"{_langfuse_host()}/project/{_project_id()}/traces/{trace_id}"


def load_live_traces(limit: int = 1000) -> list[dict[str, Any]]:
    """Pull normalized Module 1 traces from Langfuse."""
    from analysis.helpers import langfuse_io

    return langfuse_io.fetch_traces(limit=limit)


def load_offline_traces(path: Path | None = None) -> list[dict[str, Any]]:
    """Normalize the Module 1 export, for use when Langfuse is unavailable.

    The handout allows the export as an offline source and asks for the reason
    to be recorded in the interface comparison. The export is smaller than the
    live store (324 traces against 404), so prefer live whenever it is up.
    """
    from analysis.helpers.normalization import normalize_traces

    src = path or OFFLINE_EXPORT
    payload = json.loads(src.read_text())
    records = payload["traces"] if isinstance(payload, dict) else payload
    return normalize_traces(records)


CACHE = Path(__file__).resolve().parents[1] / "state" / "trace_cache.json"


def load_traces(
    source: str = "auto", limit: int = 1000, use_cache: bool = True
) -> tuple[list[dict[str, Any]], str]:
    """Return (traces, source_name).

    ``auto`` prefers the live Langfuse store and falls back to the committed
    export, so a stopped container degrades to offline review instead of an
    empty interface.

    Paging the live store takes about 30 seconds, which is too slow to pay on
    every restart during a review session, so a successful live pull is cached
    to ``state/trace_cache.json``. Pass ``use_cache=False`` (or ``--refresh``)
    to re-pull after new runs land in Langfuse.
    """
    if source in ("auto", "langfuse"):
        if use_cache and CACHE.exists():
            try:
                payload = json.loads(CACHE.read_text())
                if payload.get("traces"):
                    return payload["traces"], f"{payload.get('source', 'langfuse')} (cached)"
            except (json.JSONDecodeError, OSError):
                pass
        try:
            from analysis.helpers import langfuse_io

            if langfuse_io.is_configured():
                traces = load_live_traces(limit=limit)
                if traces:
                    CACHE.parent.mkdir(parents=True, exist_ok=True)
                    CACHE.write_text(
                        json.dumps({"source": "langfuse", "traces": traces})
                    )
                    return traces, "langfuse"
        except Exception:
            if source == "langfuse":
                raise
    return load_offline_traces(), "export"


def _session_metadata(trace: dict[str, Any]) -> dict[str, Any]:
    """Read the cartwheel.* attributes from the full metadata mapping."""
    md = trace.get("metadata") or {}
    return {
        "session_id": md.get(META_SESSION),
        "role": md.get(META_ROLE),
        "user_id": md.get(META_USER),
        "scenario_id": md.get(META_SCENARIO),
        "prompt_version": md.get(META_PROMPT),
    }


def _percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, int(q * len(ordered)))
    return ordered[idx]


def _structural_flags(
    features: dict[str, Any], thresholds: dict[str, float]
) -> list[str]:
    """Flag the dimensions where a session is a clear high outlier.

    Kept to the header and kept minimal: most sessions carry zero flags, so a
    badge means the session is genuinely unusual rather than decorating every
    record.
    """
    labels = {
        "turn_count": "turns",
        "tool_call_count": "tool calls",
        "tokens": "tokens",
    }
    flags = []
    for key in _FLAG_FEATURES:
        value = features.get(key) or 0
        hi = thresholds.get(key)
        if hi and value > hi:
            flags.append(f"{value} {labels[key]} (top 10%)")
    return flags


def build_sessions(
    traces: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Group normalized traces into session records ordered by timestamp."""
    grouped: dict[str, list[dict[str, Any]]] = {}
    for trace in traces:
        meta = _session_metadata(trace)
        sid = meta["session_id"] or f"_ungrouped_{trace['trace_id']}"
        grouped.setdefault(sid, []).append(trace)

    thresholds = {
        key: _percentile([t.get("features", {}).get(key, 0) for t in traces], 0.9)
        for key in _FLAG_FEATURES
    }

    sessions: list[dict[str, Any]] = []
    for sid, members in grouped.items():
        members = sorted(members, key=lambda t: t.get("timestamp") or "")
        head = _session_metadata(members[0])

        turns = []
        for trace in members:
            turns.append(
                {
                    "trace_id": trace["trace_id"],
                    "timestamp": trace.get("timestamp"),
                    "permalink": permalink(trace["trace_id"]),
                    "scenario_id": (trace.get("meta") or {}).get("scenario_id"),
                    "features": trace.get("features") or {},
                    "segments": trace.get("trace") or [],
                }
            )

        aggregate = {
            "trace_count": len(turns),
            "turn_count": sum(t["features"].get("turn_count", 0) for t in turns),
            "tool_call_count": sum(
                t["features"].get("tool_call_count", 0) for t in turns
            ),
            "tokens": sum(t["features"].get("tokens", 0) for t in turns),
            "has_retrieval": int(
                any(t["features"].get("has_retrieval") for t in turns)
            ),
            "distinct_tools": len(
                {
                    seg.get("name")
                    for t in turns
                    for seg in t["segments"]
                    if seg.get("role") == "tool_call"
                }
            ),
        }

        sessions.append(
            {
                "session_id": sid,
                "role": head["role"],
                "user_id": head["user_id"],
                "scenario_id": head["scenario_id"],
                "prompt_version": head["prompt_version"],
                "traces": turns,
                "features": aggregate,
                "flags": _structural_flags(aggregate, thresholds),
            }
        )

    sessions.sort(key=lambda s: s["traces"][0]["timestamp"] or "")
    return sessions


def session_index(sessions: list[dict[str, Any]]) -> dict[str, str]:
    """Map every trace id to its session id, for label bookkeeping."""
    return {
        turn["trace_id"]: session["session_id"]
        for session in sessions
        for turn in session["traces"]
    }
