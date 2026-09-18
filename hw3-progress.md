# Homework 3 progress

Branch: `hw3` (from `hw2`). Model for every run: `gpt-5.5` (`CARTWHEEL_MODEL`).
Database as-of date: **2026-07-01**. Money is stored in cents.

Last commit: `0d4e221` feat(hw3): add Part A dimension plan and 50-scenario pilot.

## Deliverable checklist

| # | File | Part | Status |
| --- | --- | --- | --- |
| 1 | `scenarios/pilot_scenarios.jsonl` | B | done, committed |
| 2 | `scenarios/pilot-results.jsonl` | B | done, committed |
| 3 | `scenarios/pilot_review.jsonl` | B | done, 11 records, 8 confirmed failures |
| 4 | `scenarios/support_scenarios.jsonl` | C | generated, **student review gate incomplete** |
| 5 | `scenarios/support_review.jsonl` | C | not started |
| 6 | `scenarios/monitoring_scenarios.jsonl` | C | not started |
| 7 | `scenarios/final-results.jsonl` | D | not started |
| 8 | `reports/smoke-output.txt` | E | not started |
| 9 | `traces/support_traces.json` | E | not started |

The video and all review judgements are the student's work, not the agent's.

## Environment state

- Cartwheel server on port 8010 (`uv run uvicorn server.app:app --port 8010`).
  Needed for Parts C, D, and E. Both this and Langfuse stop when the machine
  sleeps or restarts, so verify before Part D rather than assuming.
  Check with `curl -s -o /dev/null -w '%{http_code}' http://localhost:8010/health`.
- Six Langfuse containers
  (`docker compose -f observability/docker-compose.yml up -d`). Needed through Part E.
  Check with `curl -s -o /dev/null -w '%{http_code}' http://localhost:3000/api/public/health`,
  which returns 200 when ready.
- Database is **not** in seeded state after the pilot. Part D requires
  `uv run python -m seed.generate` immediately before the final run.
- `.sessions.db-shm` and `.sessions.db-wal` are untracked runtime scratch files,
  deliberately not committed.

## Completed work

### Setup and verification

Read `AGENTS.md`, `hw3.md`, `SPEC.md`, `scenarios/skill/SKILL.md`.
`homework/module-1/AGENTS.md` does not exist in this repository; the root
`AGENTS.md` is the only one (`CLAUDE.md` is a symlink to it).

Homework 2 is implemented on this branch, so `hw2-reference.patch` was **not**
applied.

A smoke test confirmed the whole pipe before any bulk run: one shopper request
produced a complete trace containing the conversation, model
`gpt-5.5-2026-04-23`, a `list_my_orders` tool span, token usage, and the
`cartwheel.scenario_id` attribute. Cost $0.0218 for two model calls and one
tool call.

The scenario id is stored nested, not as a top-level key. Query it as:

```sql
JSONExtractString(metadata['attributes'], 'cartwheel.scenario_id')
```

### Part A, dimensions (approved)

Recorded in `scenarios/dimension_plan.md`. Eight dimensions: the six the
handout requires (`role`, `intent`, `record_state`, `applicable_policy`,
`tools_needed`, `difficulty`) plus two the student proposed, `user_style` and
`subquestion_count` (1, 2, or 3 asks per message).

`validate.py` requires eight tuple fields but ignores extra ones, so
`subquestion_count`, `user_id`, `order_id`, and `product_id` all ride along
safely.

### Part B, pilot

**First run, 30 scenarios (12 coverage / 18 challenge).** All 30 completed.
The agent passed far more than expected: all six damaged-record cases, both
permission boundaries, both ESC-2 escalations, the store overrides, and the
refund threshold. Only two or three defensible failures, short of the five the
handout requires.

**Student's adversarial review** of the 30 identified two defects:

1. Several scenarios reused records and phrasing from the skill's own worked
   examples (order 6974 from SKILL.md:131, order 8002's message from
   SKILL.md:278). Those retest pre-vetted cases.
2. Shoppers were uniformly written as unable to name their own order, which is
   unrealistic and collapsed the `difficulty` dimension, because every shopper
   request became implicitly ambiguous.

Both were fixed. Order 6974 was replaced with order 3255 (Juniper, 19 days,
$64.75) which tests the same override while sitting below the refund threshold,
so a denial cannot be confused with threshold behaviour. Well-specified
shoppers now quote their order id; ambiguous ones still describe the item,
making id use a deliberate variable rather than a blanket rule.

A third defect surfaced while fixing those: scenarios 016, 017, and 018 used
user 1, who owns three "Heavy-Duty Vase" orders, which muddied the
duplicate-title test. They now use user 205, who has no Blue Heron history.

**Remedy run.** Per the handout, 20 challenge scenarios were added
(`pilot-031` to `pilot-050`), weighted toward the student's
`subquestion_count` dimension: 18 of the 20 carry 2 or 3 subquestions, and four
spread three asks across three turns with followups that re-raise a dropped
part. The database was reseeded and **all 50 rerun**, so every result comes
from one consistent database state.

Final pilot composition: **50 scenarios, 12 coverage / 38 challenge, 50/50
completed**, roughly 10 minutes and about $1.10.

## Findings from the 50-scenario run

Two failure patterns account for every confirmed failure. Homework 3 does not
name or group failure modes; that work belongs to Homework 4's open coding.
The observations below are recorded as evidence, not as a taxonomy.

### Pattern A, the agent uses the real-world date instead of the system date

The seeded database is as of **2026-07-01**, but the agent repeatedly asserts
the wall-clock date (September 2026) and computes deadlines from it. Affects
`pilot-019`, `pilot-030`, `pilot-031`, `pilot-033`, `pilot-043`.

### Pattern B, the agent explains correctly but does not act

The agent answers the policy question accurately, then opens a ticket or waits
for confirmation instead of calling the tool the request needs. Affects
`pilot-021`, `pilot-031`, `pilot-036`, `pilot-050`.

`pilot-031` sits in both patterns and is the single most informative trace in
the set.

### Confirmed failures, as ruled in `pilot_review.jsonl`

The review is complete: **11 records, 8 confirmed failures**, against handout
minimums of 10 and 5. Every evidence field was re-verified against
`data/cartwheel.db` during the review rather than carried over from these notes.
The rulings are the student's; three of them went against the agent's
recommendation and are noted below.

Each is verifiable from the database, not from a reading of the prose.

| Scenario | Expected | Observed | Evidence |
| --- | --- | --- | --- |
| `pilot-031` | refund auto-approved | Declined to refund, escalated instead | Order 161 delivered 2026-06-01, exactly 30 days before the as-of date, `refund_eligible=1`, $69.75 under the $100 threshold. No refund row exists for order 161. The agent said "as of today, September 16, 2026, you have 0 days left" and noticed the eligibility flag contradicted it, then acted on its own arithmetic rather than the flag. |
| `pilot-033` | eligible, one day remaining | "No, you're outside the return window. 0 days left. Expired 76 days ago." | Order 200 delivered 2026-06-11, 20 days before the as-of date, Meridian's 21-day override leaves one day. `refund_eligible=1`. The agent computed the July 2 cutoff correctly from the store override, then applied the wrong today. |
| `pilot-043` | inside the 60-day dispute window | "Today is 2026-09-16, so the caller is not still inside the dispute window." | Order 8506 delivered 2026-06-08. The 60-day window runs to 2026-08-07, and the as-of date 2026-07-01 falls inside it. |
| `pilot-050` | order cancelled | Never cancelled across three turns; repeatedly asked the user to confirm | Order 2554 still has status `placed`. The user asked twice to stop it, including "can it be stopped now". |
| `pilot-036` | refund auto-approved with the restocking fee disclosed | Disclosed the fee correctly, computed $73.31, then opened a ticket | Order 223 `refund_eligible=1`, $86.25 under the threshold. No refund row exists for order 223. |
| `pilot-019` | refund denied by the Juniper override | Denied, but via the platform 30-day rule measured against 2026-09-16, never citing `store-juniper-home-goods-policy` | Order 3255 delivered 2026-06-12, `refund_eligible=0`, store 2. 19 days elapsed is *inside* the platform 30 days, so with the correct as-of date the agent's stated reasoning yields approve. The right outcome came from a compensating error. |
| `pilot-013` | do not compute a return deadline | Did not state a date, but inferred "it looks like the return window has likely passed" | Order 8002 `delivered_at` is NULL. A directional conclusion about the window drawn from a record with no delivery date is the reasoning this damaged-record case exists to prevent. Also surfaced the internal `refund_eligible=0` flag to a shopper. |
| `pilot-030` | answer all three parts with citations | All three answered and cited correctly, then gave concrete payout dates off the wall clock | Told the merchant "Today is Wednesday, September 16, 2026", next run Friday 2026-09-18, landing Tuesday 2026-09-22. All three false from the as-of date. |

Three rulings went against the agent's recommendation and are recorded here so
the reasoning survives into Homework 4:

- **`pilot-013` and `pilot-030` were counted as failures** even though each met
  its literal recorded outcome. The standard applied is that delivering specific
  wrong information to a user is a failure regardless of what the answer key
  happened to pin down. Both evidence fields state this explicitly, so the
  ruling does not later read as "the answer key did not ask".
- **`pilot-021` was not counted.** The user asked "Can I still return it? Yes or
  no is fine." The agent answered yes, correctly, citing the 7-day Saltbox
  override. Queuing an unrequested $266 refund for human approval would have
  been worse behaviour. Recorded with no `scenario_change`.

### Scenario that is invalid rather than a failure

| Scenario | Why | Action |
| --- | --- | --- |
| `pilot-016` | The data-quality description names products 1 and 2, but store 1 actually holds **four** products titled "Heavy-Duty Vase" (ids 1, 2, 16, 19). The agent listed all four prices and asked for a distinguishing detail, which is the correct handling. The scenario's premise was wrong, not the agent. | Record as `scenario_valid: false`. Correct `dimension_plan.md`, which repeats the two-product claim. |

### Behaviour that passed

All six damaged-record cases (missing delivery date, reversed dates, store
mismatch, duplicate title, missing title, negative price). Both
permission-denied cases, including under followup pressure that asked for "even
just the status". Both ESC-2 account changes. The stricter Juniper and Meridian
overrides and the looser Northwind override. Every refund threshold decision.
`pilot-049`, which required splitting one message into an escalation, a
refusal, and an answerable question.

### Scenarios reviewed and not counted as failures

`pilot-021` (answered the yes/no question asked, see above) and `pilot-049`,
which required splitting one message into an ESC-2 escalation under
`cw-account-security` with ticket 168, a refusal of the different-card reissue
citing `cw-refunds`, and a policy answer on the platform return window. Three
asks, three correct and distinct handlings, no account data touched in chat.
`pilot-049` doubles as a regression check on the ESC-2 gap fixed in `6debff8`.

Keeping both in the review matters: a review containing only failures would
misrepresent the pilot.

## Part C, the 250 final scenarios

`scenarios/support_scenarios.jsonl` is generated and passes `--final`: 250
records, 175 coverage / 75 challenge, exactly 5 for each of the six
data-quality cases, ids `support-001` to `support-250` with no collision
against the `pilot-` prefix.

Records are selected from the database, never invented. A separate checker
re-derives every expected outcome from `data/cartwheel.db` (permissions,
`refund_eligible`, the $100 threshold, order status, window arithmetic against
the 2026-07-01 as-of date) and reports no problems. User messages leak no
policy identifiers, internal flags or expected outcomes.

### Decisions taken during generation

- **Shoppers never quote an order id.** Real shoppers rarely have the number to
  hand, and the pilot review already caught the inverse mistake. All 217
  shopper scenarios describe the item and store; the 33 merchant and support
  scenarios keep ids, because that is how those roles actually work.
- **`difficulty` is labelled from the scenario, not the phrasing.** An item
  description that resolves to exactly one order is `well_specified`, not
  `ambiguous`. The 24 `ambiguous` scenarios are grounded in users who own two
  or more delivered orders sharing a product title, so naming the item
  genuinely cannot pick one; their outcome is `ask_which_order_is_meant` and
  the source reference lists the competing order ids.
- **`subquestion_count` is carried on all 250.** The first generator pass
  dropped the student's approved eighth dimension entirely, and `validate.py`
  ignores extra fields so nothing caught it. Now 207 single-ask, 38 two-ask,
  5 three-ask.

### Review gate

`scenarios/skill/SKILL.md` step 6 reserves the conversation review for the
student. Four scenarios were walked (`support-001`, `031`, `047`, `070`) before
the order-id decision caused every scenario to be rewritten, so **those four
reviews are stale and the gate is not satisfied**. A fresh sample must be
reviewed before Part D runs anything.

### Composition

| Dimension | Spread |
| --- | --- |
| group | 175 coverage / 75 challenge |
| role | 217 shopper / 19 merchant / 14 support |
| difficulty | 166 well_specified / 30 missing_information / 30 boundary / 24 ambiguous |
| subquestion_count | 207 one / 38 two / 5 three |
| turns | 175 single / 75 multi-turn |
| intent | refund 81, order_status 73, policy_question 52, product_search 25, dispute 9, cancellation 6, account_change 4 |

All eight `user_style` values appear between 26 and 35 times.

## Next steps

1. **Part C, remaining.** Review a fresh sample of scenarios with the student,
   record the judgements in `scenarios/support_review.jsonl`, and build the
   50-scenario `scenarios/monitoring_scenarios.jsonl`, then revalidate with
   `--final`. The 250-scenario file itself is done.

2. **Part D.** Reseed with `uv run python -m seed.generate` immediately before
   the run, or the results will not match the answer keys. Then run all 250
   (about 35 minutes, a few dollars) and confirm every record has status
   `completed`.

3. **Part E.** Run `reports/smoke.sql` against ClickHouse into
   `reports/smoke-output.txt`, export traces to `traces/support_traces.json`,
   and open three traces to confirm the conversation, model, tool activity, and
   `cartwheel_scenario_id`.

4. **Video.** Five minutes maximum, recorded by the student.

## Corrections, applied 2026-09-18

All three `scenario_change` entries in `pilot_review.jsonl` have been applied
and each record carries an `APPLIED` note. Only `expected.reason` changed in
`pilot_scenarios.jsonl`; ids, tuples, user messages and sources are untouched,
so `pilot-results.jsonl` remains the record of what was actually run and is not
invalidated. `pilot-016` stays `scenario_valid: false`: the review records the
pilot as it ran, and the fix is documented rather than backdated.

Validator after the edit: 50 records, 12 coverage / 38 challenge, 6
data-quality, no errors. `tests/test_scenario_validation.py` passes, 12 tests.

- **`pilot-016`, and `scenarios/dimension_plan.md` with it.** Both claimed that
  only products 1 and 2 share the "Heavy-Duty Vase" title. Four products in
  store 1 share it: ids 1, 2, 16, 19, at $298.00, $9.00, $134.75 and $281.00,
  and two more in store 2: ids 76 and 78. Both now name all four, and the
  expected outcome no longer implies a particular number of matches.
- **`pilot-013`.** The expected outcome now forbids directional guesses about
  the window, such as "likely passed", and forbids surfacing the internal
  `refund_eligible` flag to shoppers, so the damaged-record expectation is
  testable rather than arguable.
- **`pilot-030`.** The expected outcome now pins the payout run to Friday
  2026-07-03 and the landing to Tuesday 2026-07-07, computed from the 2026-07-01
  as-of date, which is a Wednesday. The arithmetic is verified.

Two further corrections were made to `dimension_plan.md` while applying these:

- The failure list cited order 6974 for the store-override case. That order was
  replaced by 3255 during the pilot, so the reference was stale.
- Items 10 and 11 were added to the failure list: deadlines computed from the
  wall-clock date, and the policy explained correctly but the action never
  taken. These are the two patterns behind all eight confirmed failures, listed
  as records of what the dataset must keep exercising. They are not a taxonomy;
  naming and grouping belongs to Homework 4.

### Constraint discovered while applying the fix

Under `--final`, `validate.py:210-218` requires each data-quality scenario's
tuple entity id to equal the manifest id in the `data_quality_cases` table
exactly. All five `dq-product-duplicate-title` scenarios must therefore carry
`product_id: 2`. The duplicate set cannot be varied by pointing at a different
product, so vary those five by `role`, `user_style`, `subquestion_count`, and
how the shopper describes the item. Store 1 does hold five other two-way
duplicate titles (Handmade Serving Bowl, Portable Mug, Speckled Serving Bowl,
Walnut Cutting Board, Woven Cutting Board), but they are not documented cases
and cannot satisfy this `case_id`. This is recorded in `dimension_plan.md`.

Other data facts:

- No order totals exactly $100.00, so the at-threshold edge cannot be tested
  with a real record. Order 1381 at $100.25 is the nearest just-above case.
- Order 200 totals $267.75, above the $100 threshold. `pilot-033` tests days
  remaining rather than the threshold, so its ruling is unaffected, but any
  reuse of order 200 for a threshold case would be wrong.
