"""Review server for HW4, session-grouped.

Extends the reference server's file-backed API (analysis/server.py) rather
than replacing it: the endpoint contract, the atomic writes, and the Langfuse
score sync are reused unchanged, because that contract is what the error
analysis skill specifies and what the agent's watcher polls.

What this adds over the reference:

    GET  /api/sessions     traces grouped by cartwheel.session_id
    GET  /api/labels       per-mode binary judgments (structured labeling view)
    POST /api/labels       save a judgment; writes Langfuse + state/labels/
    GET  /api/progress     review coverage, per batch and overall

Run it:

    uv run python -m analysis.review_app.server
    uv run python -m analysis.review_app.server --port 8021 --source export
"""

from __future__ import annotations

import argparse
import json
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any

from analysis.server import (
    API_DEFAULTS,
    API_FILES,
    ReviewHandler,
    _read_json,
    _write_json,
)
from analysis.review_app import data

HERE = Path(__file__).resolve().parent
UI_FILE = HERE / "ui" / "index.html"
STATE_DIR = Path(__file__).resolve().parents[1] / "state"
LABELS_DIR = STATE_DIR / "labels"
MANIFEST = STATE_DIR / "sample_manifest.json"

# Populated at startup so every request serves the same grouped view.
SESSIONS: list[dict[str, Any]] = []
SOURCE = "unset"


def _load(
    source: str,
    limit: int,
    use_cache: bool = True,
    prefix: str | None = "support-",
) -> None:
    """Load traces and group them into sessions.

    ``prefix`` restricts the review set by scenario id. It defaults to
    ``support-`` because the store also holds HW1 line traces, HW3 pilot
    traces, and smoke tests, all from the earlier model. Sessions sort oldest
    first, so without the filter those leftovers occupy the first ~70 screens
    and the reviewer pages through another model's behaviour before reaching
    the run they mean to open-code. Pass ``--prefix ''`` to review everything.
    """
    global SESSIONS, SOURCE
    traces, SOURCE = data.load_traces(
        source=source, limit=limit, use_cache=use_cache
    )
    total = len(traces)
    if prefix:
        traces = [
            t
            for t in traces
            if str((t.get("metadata") or {}).get(data.META_SCENARIO, "")).startswith(
                prefix
            )
        ]
    SESSIONS = data.build_sessions(traces)

    models: dict[str, int] = {}
    for t in traces:
        for m in t.get("models") or []:
            models[m] = models.get(m, 0) + 1

    dropped = total - len(traces)
    print(f"loaded {total} traces from {SOURCE}")
    if dropped:
        print(f"  filtered to scenario prefix {prefix!r}: {len(traces)} kept, {dropped} excluded")
    print(f"  models: {models or 'none'}")
    print(f"  -> {len(SESSIONS)} sessions")


def _reviewed_trace_ids() -> set[str]:
    """Trace ids carrying at least one human annotation.

    An explicit "no failure observed" note counts as reviewed, which is what
    separates a reviewed-and-clean trace from one nobody has opened yet.
    """
    annotations = _read_json(API_FILES["/api/annotations"], [])
    if isinstance(annotations, dict):
        annotations = annotations.get("annotations", [])
    return {
        a.get("trace_id")
        for a in annotations
        if isinstance(a, dict) and a.get("trace_id")
    }


def _manifest() -> dict[str, Any]:
    return _read_json(MANIFEST, {"batches": {}, "traces": {}})


def _progress() -> dict[str, Any]:
    """Coverage for the progress view.

    Reports per-batch counts against the handout's four batches plus the
    overall distinct-trace total, which is the number that must reach 100.
    """
    reviewed = _reviewed_trace_ids()
    manifest = _manifest()
    assigned = manifest.get("traces", {})

    per_batch: dict[str, dict[str, int]] = {}
    for trace_id, entry in assigned.items():
        batch = entry.get("batch", "unassigned") if isinstance(entry, dict) else "unassigned"
        bucket = per_batch.setdefault(batch, {"selected": 0, "reviewed": 0})
        bucket["selected"] += 1
        if trace_id in reviewed:
            bucket["reviewed"] += 1

    all_trace_ids = {t["trace_id"] for s in SESSIONS for t in s["traces"]}
    labels = _all_labels()
    modes = sorted({row["mode"] for row in labels})
    judged: dict[str, int] = {mode: 0 for mode in modes}
    for row in labels:
        judged[row["mode"]] = judged.get(row["mode"], 0) + 1

    missing = 0
    if modes:
        have = {(row["trace_id"], row["mode"]) for row in labels}
        missing = sum(
            1 for tid in reviewed for mode in modes if (tid, mode) not in have
        )

    return {
        "source": SOURCE,
        "sessions": len(SESSIONS),
        "traces_total": len(all_trace_ids),
        "traces_reviewed": len(reviewed & all_trace_ids),
        "target": 100,
        "batches": per_batch,
        "modes": modes,
        "labels_per_mode": judged,
        "missing_judgments": missing,
    }


def _all_labels() -> list[dict[str, Any]]:
    """Read every per-mode JSON Lines label file.

    Later lines win, so a flipped label supersedes the earlier one while the
    full history stays on disk (the skill requires the flip history to remain
    inspectable).
    """
    rows: dict[tuple[str, str], dict[str, Any]] = {}
    if not LABELS_DIR.exists():
        return []
    for path in sorted(LABELS_DIR.glob("*.jsonl")):
        mode = path.stem
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("superseded_by"):
                continue
            row.setdefault("mode", mode)
            trace_id = row.get("trace_id")
            if trace_id:
                rows[(trace_id, row["mode"])] = row
    return list(rows.values())


def _append_label(payload: dict[str, Any]) -> dict[str, Any]:
    """Append one binary judgment and mirror it to Langfuse.

    Appends rather than rewrites, so changing a judgment keeps the earlier
    line on disk. Langfuse remains canonical for accepted judgments; a failed
    score write still leaves the local record and is reported to the caller.
    """
    mode = str(payload.get("mode") or "").strip()
    trace_id = str(payload.get("trace_id") or "").strip()
    label = payload.get("label")
    if not mode or not trace_id or label not in (0, 1, "0", "1"):
        raise ValueError("label requires mode, trace_id, and a 0/1 label")

    record = {
        "trace_id": trace_id,
        "mode": mode,
        "label": int(label),
        "source": payload.get("source", "human"),
        "evidence": payload.get("evidence", ""),
        "ts": payload.get("ts"),
    }

    LABELS_DIR.mkdir(parents=True, exist_ok=True)
    path = LABELS_DIR / f"{mode}.jsonl"
    with path.open("a") as handle:
        handle.write(json.dumps(record) + "\n")

    synced = False
    error = None
    try:
        from analysis.helpers import langfuse_io

        if langfuse_io.is_configured():
            langfuse_io.write_label_score(
                trace_id=trace_id,
                mode=mode,
                label=int(label),
                comment=record["evidence"] or None,
            )
            synced = True
    except Exception as exc:  # network-only path
        error = str(exc)

    return {"ok": True, "written": record, "langfuse": synced, "error": error}


class AppHandler(ReviewHandler):
    """Adds the session, label, and progress routes to the reference handler."""

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]

        if path in ("/", "/index.html"):
            self._send_file(UI_FILE, "text/html; charset=utf-8")
            return
        if path == "/api/sessions":
            self._send_json({"source": SOURCE, "sessions": SESSIONS})
            return
        if path == "/api/labels":
            self._send_json(_all_labels())
            return
        if path == "/api/progress":
            self._send_json(_progress())
            return
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path == "/api/labels":
            body = self._read_body()
            if not isinstance(body, dict):
                self._send_json({"error": "expected a JSON object"}, status=400)
                return
            try:
                self._send_json(_append_label(body))
            except ValueError as exc:
                self._send_json({"error": str(exc)}, status=400)
            return
        super().do_POST()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8020)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument(
        "--source",
        default="auto",
        choices=["auto", "langfuse", "export"],
        help="trace source; auto prefers live Langfuse and falls back to the export",
    )
    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="re-pull from Langfuse instead of using state/trace_cache.json",
    )
    parser.add_argument(
        "--prefix",
        default="support-",
        help="only review traces whose cartwheel.scenario_id starts with this "
        "(default: support-; pass '' to review every trace in the store)",
    )
    args = parser.parse_args()

    try:
        from dotenv import load_dotenv

        load_dotenv(Path(__file__).resolve().parents[2] / ".env")
    except ImportError:
        pass

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    _load(
        args.source,
        args.limit,
        use_cache=not args.refresh,
        prefix=args.prefix or None,
    )

    for endpoint, default in API_DEFAULTS.items():
        target = API_FILES[endpoint]
        if not target.exists():
            _write_json(target, default)

    server = ThreadingHTTPServer((args.host, args.port), AppHandler)
    print(f"review interface on http://{args.host}:{args.port}/")
    print(f"serving state from {STATE_DIR}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nshutting down")
        server.shutdown()


if __name__ == "__main__":
    main()
