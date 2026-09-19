# Homework 3 progress

Branch: `hw3` (from `hw2`). Model for every run: `gpt-5.5` (`CARTWHEEL_MODEL`).
Database as-of date: **2026-07-01**. Money is stored in cents.

Last commit: Parts D and E.

**All nine deliverable files exist. Only the student's video remains.**

## Deliverable checklist

| # | File | Part | Status |
| --- | --- | --- | --- |
| 1 | `scenarios/pilot_scenarios.jsonl` | B | done, committed |
| 2 | `scenarios/pilot-results.jsonl` | B | done, committed |
| 3 | `scenarios/pilot_review.jsonl` | B | done, 11 records, 8 confirmed failures |
| 4 | `scenarios/support_scenarios.jsonl` | C | done, 250 records, validator clean |
| 5 | `scenarios/support_review.jsonl` | C | done, 42 records, 23 accept / 19 revise |
| 6 | `scenarios/monitoring_scenarios.jsonl` | C | done, 50 records |
| 7 | `scenarios/final-results.jsonl` | D | done, **250/250 completed** |
| 8 | `reports/smoke-output.txt` | E | done, all 8 queries |
| 9 | `traces/support_traces.json` | E | done, **324 traces / 250 scenarios** |

The video and all review judgements are the student's work, not the agent's.

Parts A to C were verified **offline** against `data/cartwheel.db`. Part D was
the first time the agent's behaviour met these answer keys; the results have
not yet been judged against the expected outcomes, and that judging is
Homework 4's work, not something this file records.

## Environment state

Checked 2026-09-19, after the Part D and E runs:

- Cartwheel server on port 8010 (`uv run uvicorn server.app:app --port 8010`).
  Up. Needed again only for Homework 7's rerun.
- Six Langfuse containers
  (`docker compose -f observability/docker-compose.yml up -d`). Up and healthy.
  **Keep them.** Homework 4 uses Langfuse as the canonical trace and annotation
  store; `traces/support_traces.json` is its offline fallback, not a
  replacement.
- Database is in seeded state as of the last reseed before the final run.
- `.sessions.db-shm` and `.sessions.db-wal` are untracked runtime scratch files,
  deliberately not committed.

Two checks before trusting this note, because both services stop when the
machine sleeps:

```bash
curl -s -o /dev/null -w '%{http_code}' http://localhost:8010/health
curl -s -o /dev/null -w '%{http_code}' http://localhost:3000/api/public/health
```

A 200 from `/health` is **not** sufficient for the Cartwheel server. It kept
answering 200 while every `POST /sessions` returned 500. The real check is to
create a session and send one message.

### Host resource limits, learned the hard way

This machine has 16 GB and 8 cores, and the run failed three times on
resources before it completed. What worked:

- **Docker VM at 6 CPU / 3.84 GB.** At the original 4 CPU / 1.94 GB,
  `langfuse-web` sat at ~99% CPU *while idle* and had crash-looped 36 times;
  Redis then could not hold BullMQ locks and the worker dropped ingestion jobs
  rather than queueing them.
- **Chrome closed.** It reached 58 processes and 5.86 GB, nearly four times
  Docker's footprint, and the OS killed the runner mid-run when swap hit
  6.33 GB of 7 GB.
- **Batches of 20** via `--ids` rather than one 250-scenario run. The server
  wedged after roughly 40 to 50 scenarios every time, so batching capped the
  loss at minutes instead of the whole tail.

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

### Review gate, satisfied

The four stale walkthroughs (`support-001`, `031`, `047`, `070`) were discarded
and **30 scenarios were reviewed across two fresh, non-overlapping samples of
15**, against the handout's requirement of 15. Each sample spans both scenario
groups, all three roles and every intent; together they cover all six
documented data-quality cases. Rulings are in `scenarios/support_review.jsonl`:
42 records, 23 `accept` / 19 `revise`.

Every ruling was checked against `data/cartwheel.db` rather than read off the
scenario prose. All 19 revisions are applied, and the applied set was verified
to match the rulings exactly in both directions: no record changed without a
ruling, no ruling left unapplied.

### Defects found and fixed during the review

1. **Ungrounded followups, 11 records.** Two stock followup strings had been
   copied onto hosts whose data cannot answer them: *"same address i had
   before"* (neither `users` nor `orders` has an address column) and *"was
   anything else sent with it"* (each order row holds exactly one
   `product_id`). After the first two turned up in sampling, a sweep of all 22
   reused followup strings found every remaining instance. Replacements are
   grounded in each host's own record, and no two share a string, so no new
   stock cluster was created. Distinct followups rose from 22 to 28.

   The sweep is a text check and costs nothing: only 74 of the 250 scenarios
   have followups at all.

2. **`support-249` spoke in the wrong voice.** Role `support`, but the opening
   read as the shopper (*"my classic tea sampler"*) while the followup said
   *"they're pressing on"*. Its tuple also recorded `platform_rule` while the
   answer key applied the Saltbox Pantry 7-day override. Both corrected.

3. **`support-206` contradicted the pilot.** It asked a yes/no question against
   a state-changing expected outcome, the exact conflict ruled on in
   `pilot-021`, where queuing an unrequested refund was judged *worse*
   behaviour. Rewritten to request the return outright, keeping order 2041's
   day-30 boundary, which is the scarce part of that record.

4. **`support-190` and `support-202`** carried followups that presupposed facts
   their own damaged records contradict.

### Coverage-set intent gap, closed

`cancellation` and `account_change` existed only in the challenge set, leaving
no ordinary baseline: a cancellation failure could not be told apart from a
cancellation failure *under pressure*. Four over-represented `refund` coverage
scenarios were converted (`support-054`, `072`, `091`, `092`). `validate.py`
`--final` locks the 175/75 split, so a coverage addition must be a conversion,
never an append.

`account_change` is a deliberate exception: **ESC-2 escalates account changes
of any kind**, so no ordinary non-escalating variant exists and all six share
one expected outcome. What varies across the groups is pressure, not the
answer. Recorded in `dimension_plan.md` so it does not later read as a
generation fault.

An earlier note in this file claimed `dispute` was also missing from the
coverage set. That was wrong: `dispute` has 8 coverage scenarios.

### Composition, after the Part C revisions

| Dimension | Spread |
| --- | --- |
| group | 175 coverage / 75 challenge |
| role | 217 shopper / 19 merchant / 14 support |
| difficulty | 166 well_specified / 30 missing_information / 30 boundary / 24 ambiguous |
| turns | 176 single / 74 multi-turn |
| subquestion_count | 208 one / 37 two / 5 three |
| intent | refund 77, order_status 73, policy_question 52, product_search 25, dispute 9, cancellation 8, account_change 6 |
| coverage intents | order_status 65, refund 56, policy_question 32, product_search 10, dispute 8, cancellation 2, account_change 2 |
| challenge intents | refund 21, policy_question 20, product_search 15, order_status 8, cancellation 6, account_change 4, dispute 1 |

All eight `user_style` values appear between 26 and 35 times. Every intent now
appears in both sets.

### Monitoring subset

`scenarios/monitoring_scenarios.jsonl` holds 50 records copied **verbatim**
from `support_scenarios.jsonl`, verified byte-identical, because Homework 7
reruns the same requests after the agent changes.

It is selected by **expected outcome** rather than in proportion to the 250,
because it is a regression baseline: all 31 distinct outcomes appear at least
once, so no behaviour can regress unwatched. Weighting favours what is
expensive to get wrong, permission refusals, escalations, the above-threshold
queue, store overrides, state changes, the six damaged records and
as-of-date arithmetic. Ordinary lookups are thinned: `refund` is 12 of 50 here
against 77 of 250.

Composition: 28 challenge / 22 coverage, 42 shopper / 5 merchant / 3 support,
all seven intents, all eight styles, 34 multi-turn, all six data-quality cases.
The challenge tilt is intentional; challenge scenarios are where regressions
surface first.

## Part D, the final run

`scenarios/final-results.jsonl`: **250 records, all `completed`**, 175 coverage
/ 75 challenge, one model (`gpt-5.5`), no duplicate ids.

The run did not complete in one pass. It took four attempts across two days,
and the reasons are worth recording because Homework 7 reruns the monitoring
subset on the same machine.

| Attempt | Result | Cause |
| --- | --- | --- |
| 1 | stopped at 19 | Langfuse dropped ~90% of traces; only 2 of 19 landed |
| 2 | 149 of 250 | OS killed the runner, swap exhausted at 6.33 GB of 7 GB |
| 3 | 0 of 101 | `OPENAI_API_KEY` invalidated; every request 500 |
| 4 | 47, then 20 + 20 + 14 in batches | server wedged twice more; batching finished it |

Attempt 1 was stopped deliberately. Had it run on, it would have spent the full
250 model calls and produced almost nothing for Part E, while
`final-results.jsonl` showed a clean 250/250. **The runner reports `completed`
on the basis of the HTTP reply from port 8010 and never checks that Langfuse
recorded anything**, so trace loss is invisible in the results file. This is the
same failure that cost the pilot 15 of its 50 traces.

The API key problem had a second trap. The key was replaced in `.env`, but a
stale `OPENAI_API_KEY` was exported in the shell, and `python-dotenv` does not
override a variable already present in the environment. The server inherited the
dead key and returned 500 on every scenario. The fix was `unset OPENAI_API_KEY`
before starting uvicorn. A restart alone was not enough: the first "restart" left
the original day-old process alive, which `ps -o lstart` exposed.

### What made the difference

Checking trace delivery *during* the run rather than at the export. After each
batch:

```bash
docker exec observability-clickhouse-1 clickhouse-client \
  --user clickhouse --password clickhouse --database default \
  --query "SELECT countIf(JSONExtractString(metadata['attributes'],'cartwheel.scenario_id') LIKE 'support-%') FROM traces"
```

The count should exceed the scenario count, because 74 of the 250 are
multi-turn and each turn is its own trace. Healthy checkpoints ran 5/3, 7/6,
9/8, 22/20, 46/41, 26 new per 20. The failed run showed 2 per 19.

## Part E, export and smoke report

`traces/support_traces.json`: **324 traces for all 250 scenarios**, which equals
the sum of `turn_count` exactly. The handout's video command returns 250:

```bash
jq '[.traces[].cartwheel_scenario_id] | unique | length' traces/support_traces.json
```

### The export needed filtering

The raw export held **429 traces**. `export_langfuse.py` selects by scenario id
and does not deduplicate, so every failed attempt and rerun came back under the
same ids. Removed, with the counts recorded in a `filtered` block inside the
file:

| Removed | Count | Why |
| --- | --- | --- |
| 401 auth errors | 101 | cost 0.0, latency 0.055s, no output; never reached the model |
| zero-cost failure | 1 | same shape, different cause |
| duplicate reruns | 3 | genuine earlier runs of `support-001`, `002`, `150` |

For the three duplicates the **newest** traces were kept, being the runs made
after the final reseed with a working key. Some of the discarded ones predate a
reseed, so their recorded behaviour no longer matches the database the answer
keys describe. Left in place they would have been open-coded in Homework 4 as
real agent behaviour.

Langfuse still holds everything; only the exported file was filtered.

### Smoke report

`reports/smoke-output.txt` carries all eight queries. Two mechanical notes:
`--multiquery` silently stopped after query 4, so the queries were run
individually, and query 8 has no trailing semicolon and had to be appended
separately.

The report reads **raw** Langfuse data, so its counts still include the pilot
run alongside the 250 final scenarios and do not match the filtered export. A
header in the file says so.

It was regenerated after the dead-trace deletion described below, so the
committed file matches the current store.

| Section | Observed |
| --- | --- |
| roles | shopper 338, merchant 41, support 26 |
| errors | **none** |
| escalations | 100 |
| tokens / cost | 1,638,930 in / 289,693 out, **$17.19** |
| permission denials | **7** |
| tools | `search_help_center` 328, `get_policy` 263, `get_order` 237, `find_order` 180, `escalate_to_human` 100, `search_products` 95, `issue_refund` 22, `cancel_order` 7, `list_my_orders` 3 |

The 7 permission denials confirm the Homework 2 span attribute works, which
Homework 4 depends on. A stray `hw1-line-1` trace from Homework 1 also appears
in the raw data; it is not a final scenario id and is absent from the export.

The cost figure covers **every** attempt, including the runs that were killed
or wedged, so it overstates what the successful 250 alone cost.

### Dead traces deleted from Langfuse

The failed 2026-09-19 authentication run left **104 traces** carrying 207
`level='ERROR'` spans, all inside one 18-minute window, each with cost 0 and no
output because the model was never reached. They were deleted.

The reason is Homework 4, which uses Langfuse as its canonical store and begins
Part B with 15 *uniformly sampled* traces (`homework/module-2/hw4.md:74`).
Sampling over 521 traces would have drawn roughly three dead ones per batch of
15, each consuming a review slot with no conversation to open-code.

Before deleting, two things were verified: the deletion set had **zero overlap**
with the 324 traces in `traces/support_traces.json`, and no other dead traces
existed anywhere in the store. After deleting: **417 traces remain**, 0 carry
error spans, all 67 pilot traces survive, every one of the 324 exported traces
still resolves, and all 250 scenario ids still have traces.

Deletion is permanent and Langfuse has no undo, so the record of those failures
lives here and in the Part D commit message rather than in the trace store.

## Next steps

1. **Video.** Five minutes maximum, recorded by the student. The handout asks
   for a failed pilot scenario with its evidence, a revised final scenario, one
   complete final trace, and the scenario-id count.

   For the revised scenario, `support-249` and `support-206` are the clearest to
   narrate: each has a defect visible on screen and a recorded reason in
   `support_review.jsonl`.

   **For the failed pilot scenario, do not pick `pilot-031` or `pilot-036`.**
   Both are confirmed failures but **have no trace in Langfuse**, so there is
   nothing to show. Fifteen pilot traces were lost to the same ingestion failure
   described above. Use `pilot-033`, `043`, `050`, `019`, `013` or `030`, all of
   which are traced.

2. **Homework 4.** Keep the Langfuse containers. Homework 4 groups traces by
   `cartwheel.session_id`, which `server/app.py:203` sets on the same span as
   the scenario id, so multi-turn conversations reassemble correctly.

## Open questions carried into Homework 4

These were written before Part D ran. The run produced the traces but nothing
here has been judged yet, because comparing behaviour to the expected outcomes
is Homework 4's open coding, not Homework 3's work.

- **Expected outcomes are verified against the database, not against
  behaviour.** Static checks cannot tell whether an expected outcome is
  *reasonable*, only whether it matches the record. The pilot showed this
  matters: `pilot-021` was ruled not-a-failure only after seeing what the agent
  actually did. Expect some Part D results to raise the same question.
- **The two failure patterns from the pilot are unaddressed by design.** The
  agent used the wall-clock date instead of the 2026-07-01 as-of date, and
  explained policy correctly without acting. Many final expected reasons now
  state both requirements explicitly, so the traces will show whether that
  phrasing changed the agent's behaviour or merely documented the expectation.
- **The smoke report counts 100 escalations and 7 permission denials** across
  the raw data. Neither number has been checked against the scenarios that
  expected those outcomes; that join is Homework 4 work.

## Corrections to the pilot files, applied 2026-09-18

This section covers the **pilot** files only, `pilot_scenarios.jsonl` and
`pilot_review.jsonl`. The Part C revisions to `support_scenarios.jsonl` were
made the same day and are recorded above, under "Defects found and fixed during
the review".

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
