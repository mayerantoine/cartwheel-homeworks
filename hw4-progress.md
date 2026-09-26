# Homework 4 progress

Branch: `hw4` (from `hw3`). Model for every trace under review:
**`gpt-6-luna`**. Database as-of date: **2026-07-01**.

Homework 4 is human trace review and failure taxonomy: review at least 100
traces, open-code the failures, and organise them into 5 to 8 binary failure
modes.

**Status: Part A done, Part B in progress (55 of 100 traces). Parts C, D and E
not started.**

## Deliverable checklist

| # | File | Part | Status |
| --- | --- | --- | --- |
| 1 | `analysis/review_app/` | A | done, committed |
| 2 | `analysis/report/interface_comparison.md` | A | **not written** |
| 3 | `analysis/state/sample_manifest.json` | B | partial, 2 of 4 batches |
| 4 | `analysis/state/annotations.json` | B | 64 annotations over 55 traces |
| 5 | `analysis/state/patterns.json` | D | **empty, no taxonomy yet** |
| 6 | `analysis/state/suggestions.json` | D | **empty, no depth scan run** |
| 7 | `analysis/state/labels/<mode>.jsonl` | E | **none** |
| 8 | `analysis/report/review_summary.md` | — | **not written** |
| 9 | `analysis/report/workshop_notes.md` | C | **not written** |
| 10 | `analysis/report/spec_revisions.md` | D | done, one revision |
| 11 | Video | — | student's work |

## Why the traces were regenerated

HW3 ran the 250 scenarios on `gpt-5.5`, which passed far more than expected:
its 50-scenario pilot produced only 8 confirmed failures. A taxonomy built on
that store would carry 3 to 5 positives per mode, short of the 30 Pass and 30
Fail per mode Homework 5 needs to validate a judge.

`gpt-6-luna` was chosen for failure density and cost. A 21-scenario pilot
against a freshly seeded database failed roughly 43% of the time, and the
failures cluster rather than scatter. The full run cost about **$0.27** against
HW3's **$14.21**.

Cost comparison over 8 identical scenarios, from the OpenAI published rates:

| Model | est. 250-run | vs gpt-5.5 |
| --- | --- | --- |
| `gpt-6-luna` | **$0.27** | 0.012x |
| `gpt-5.6-luna` | $0.51 | 0.023x |
| `gpt-5.4-nano` | $1.10 | 0.050x |
| `gpt-5.4-mini` | $2.35 | 0.107x |
| `gpt-5.5` | $21.92 | 1.000x |

`gpt-4o-mini` was ruled out: `agent/agent.py:145` applies
`reasoning={"effort": "high"}` to every model whose name starts with `gpt-`,
and 4o-mini rejects it with `400 Unsupported parameter`. The luna models accept
it, so the agent runs unchanged.

## Environment state

Checked 2026-09-26:

- Docker running; six Langfuse containers up, `localhost:3000` healthy.
- Cartwheel server on port 8010 (`uv run uvicorn server.app:app --port 8010`).
- Review interface on port 8020
  (`uv run python -m analysis.review_app.server`).
- Database seeded, as of 2026-07-01, no drift.

**Two traps that cost time, both worth re-checking before any run:**

1. **A dead `OPENAI_API_KEY` is exported in the shell**, an `sk-None-...`
   placeholder masking the real 164-character key in `.env`. `python-dotenv`
   does not override a variable already in the environment, so every command
   needs `env -u OPENAI_API_KEY` or a shell where it is unset. This is the same
   failure that cost HW3 attempt 3 its 101 scenarios.
2. **The database drifts under the agent's own writes.** Before the re-run, 13
   of the 207 scenarios naming an order expected a state change on an order
   already cancelled or refunded by HW3. Reseeding returns drift to 0. Reseed
   before every run, including pilots.

## Part A, the review interface

`analysis/review_app/` (`data.py`, `server.py`, `ui/index.html`), adapted from
the course reference.

**Retained:** the reference server's file-backed API and its Langfuse score
sync, plus the inline annotation flow with margin notes.

**Changed:** the interface groups by `cartwheel.session_id` and renders each
conversation in timestamp order. Cartwheel writes one trace per user turn, so
74 of the 250 scenarios are split across traces; the reference renders one
trace per screen, which leaves a followup turn showing none of the tool calls
from the turn before it. `fetch_traces` flattens only a subset of trace
metadata into `meta` and that subset omits the session id, so `data.py` reads
`cartwheel.*` from the full `metadata` mapping instead.

Two fixes came out of using it:

- A transient Langfuse `422 Request timed out` while paging made the app fall
  back to `traces/support_traces.json` and report `source: "export"`, which
  reads like a normal startup line but is a **different trace set** (HW3's
  gpt-5.5 run). Now retries three times and warns loudly before falling back.
- The store also holds 67 `pilot-*` traces and some HW1 leftovers, all
  gpt-5.5. Sessions sort oldest first, so those filled the first ~70 screens.
  The app now filters by scenario prefix, defaulting to `support-`, and the
  session list can be filtered to one review batch.

`interface_comparison.md` still has to be written; the material for it is here.

## Part B, review progress

**55 of 100 traces reviewed. 64 annotations: 41 failure notes, 23 "no failure
observed" verdicts.**

Reviewed sample composition, 51 distinct scenarios:

| Dimension | Spread |
| --- | --- |
| group | 40 coverage / 11 challenge |
| role | **51 shopper, 0 merchant, 0 support** |
| intent | order_status 29, dispute 8, refund 8, policy_question 3, product_search 3 |
| difficulty | 22 ambiguous, 20 well_specified, 5 boundary, 4 missing_information |

The sample is **not representative and should not be reported as prevalence**.
Two reasons:

1. The first 18 traces were read in scenario-id order before batching began,
   and `support_scenarios.jsonl` is ordered so that the opening stretch is
   almost entirely ambiguous shopper order_status coverage scenarios. All 75
   challenge scenarios sit at ids 176 to 250.
2. No merchant or support trace has been reviewed yet, against 19 and 14 in
   the store.

Batches so far, recorded in `sample_manifest.json`:

| Batch | Selected | Reviewed |
| --- | --- | --- |
| `batch0_sequential_browse` | 18 | 18 |
| `batch1_uniform_and_clusters` | 30 | 15 |

`batch0` is not one of the handout's four batches. It is recorded separately so
the review summary can describe the sample honestly rather than folding an
order-biased browse into a batch it was not drawn for.

`batch1` was drawn with `select_traces(strategy="diversity")`, which returns
roughly two thirds cluster representatives and one third random rather than the
handout's explicit 15 uniform plus 15 cluster representatives. It skews to
challenge scenarios (24 of 30), which is better material for finding modes but
is not uniform sampling. **This has to be stated in the review summary.**

## Candidate failure modes

Not yet a taxonomy. These are groupings of the human notes, not accepted modes,
and no name or definition has been agreed.

| Candidate | Notes | Traces | Likely evaluator |
| --- | --- | --- | --- |
| policy identifier shown to a shopper | 27 | 24 | code check |
| over-escalation on invented delivery concepts | 6 | 6 | LLM judge |
| refuses to compute a deadline it has the data for | 5 | 4 | LLM judge |
| wrong product match | 2 | 2 | code check |

Three of the four are below the handout's minimum of three confirmed positives
plus three close negatives, so they need targeted retrieval during Part D.

**Discovery rate:** traces 1 to 35 produced all four candidates; traces 36 to
55 produced no new candidate, only repeats. That is what approaching saturation
on *naming* looks like. The remaining 45 traces are needed for **coverage and
counts**, not for discovery, and Homework 5's 30-Fail-per-mode requirement
cannot be met from 55 traces for the thin modes.

## Specification revision

One revision, recorded in `analysis/report/spec_revisions.md`.

**RESP-1 split by audience.** 27 annotations across 24 traces objected to the
agent printing raw policy identifiers to shoppers ("agent handles them
(cw-disputes)"). Every one is a shopper trace, and 163 of the 279 shopper
traces in the run carry an identifier in an assistant reply.

The agent was obeying the specification: RESP-1 required citing the policy
identifier for every policy claim. The disagreement was with the
specification, so per the handout it was resolved before any label was
assigned. RESP-1 now splits into RESP-1a (shoppers: plain language and
human-readable titles, no raw identifier), RESP-1b (merchant and support: cite
the identifier) and RESP-1c (record the identifier in the trace regardless).

**This is a specification failure, not a generalization failure.**
`agent/agent.py:70` still instructs the model to cite the id "for example
cw-returns", so the fix is a prompt edit. Labels for this mode apply only to
traces produced after that edit; labelling the current traces measures the old
specification.

## Next steps

1. **Axial coding.** Group the 41 notes into named candidate modes with binary
   definitions, boundaries against the nearest neighbour, and close negatives.
   The coding agent proposes groupings from the notes; the rulings are the
   student's.
2. **Edit `agent/agent.py:70`** to match revised RESP-1, so the policy-id mode
   can be measured against the requirement that now exists.
3. **Part C, Workshop.** Install Raindrop Workshop, run `/instrument-agent`
   preserving the existing OpenTelemetry and Langfuse instrumentation, inspect
   5 to 10 runs across different roles and tools, and write
   `analysis/report/workshop_notes.md` with run identifiers, candidate
   failures, and one case where the agent reports uncertainty.
4. **Finish Part B to 100 traces.** Batch 2 must cover a product dimension
   chosen before looking at outcomes; **role is the obvious choice given that
   no merchant or support trace has been reviewed**. Batch 3 is 25 traces from
   depth searches, which should target the three thin candidates. Batch 4 is
   the final 15 uniform traces as a saturation check.
5. **Part D.** Build the taxonomy, compare it against the AgentDebug taxonomy
   for omissions, run a depth search for one confirmed mode, and record at
   least one rejected suggestion.
6. **Part E.** Apply every final mode to every reviewed trace, write the labels
   to Langfuse scores and `analysis/state/labels/`, and report counts as sample
   fractions rather than prevalence estimates.
7. **Write `interface_comparison.md` and `review_summary.md`.**
8. **Video**, five minutes maximum, recorded by the student.

## Open questions

- **Does the policy-id mode belong in this taxonomy at all?** It is a
  specification failure whose fix is a prompt edit, and the skill (phase 6)
  says to fix specification failures before building evaluators. It may be
  better reported as a fixed specification gap with a before-and-after
  prevalence, rather than carried as one of the 5 to 8 modes.
- **Are "over-escalation" and "refuses to compute a deadline" one mode or
  two?** Both end with the agent handing off rather than answering. The test is
  whether one product change fixes both, and that has not been decided.
- **The reviewed sample has no merchant or support traces.** Any mode that only
  appears under those roles has not been seen yet.
