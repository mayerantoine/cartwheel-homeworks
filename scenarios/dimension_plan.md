# Scenario dimension plan (Homework 3, Part A)

Approved by the student on 2026-09-15. Generation for the pilot and the final
set must follow this plan. Model for every run: `gpt-5.5` (`CARTWHEEL_MODEL`).

Database as-of date: **2026-07-01**. All day counts below are measured from it.
Money is stored in **cents** (`total_cents`, `price_cents`).

## Dimensions

| # | Dimension | Values | Why it changes expected behavior | Source |
| --- | --- | --- | --- | --- |
| 1 | `role` | shopper, merchant, support | AUTH-1 access matrix: the same question has a different correct answer per role. | SPEC.md §3 |
| 2 | `intent` | order_status, refund, cancellation, policy_question, product_search, dispute, account_change, out_of_scope | Each intent routes to different tools and rules. | SPEC.md §2, §4 |
| 3 | `record_state` | order_in_window, order_past_window, order_above_threshold, order_placed, order_shipped, order_damaged, product, policy_page, none | The record state fixes the answer. | orders table |
| 4 | `applicable_policy` | platform_rule, store_override, none | A store window takes precedence over the platform default. | facts.yaml `store_overrides` |
| 5 | `tools_needed` | none, one_lookup, several_calls | A policy question needs one lookup; a refund needs several calls. | SPEC.md §4 |
| 6 | `difficulty` | well_specified, ambiguous, missing_information, boundary | A boundary request sits exactly at a window or threshold. | facts.yaml |
| 7 | `user_style` | the eight values enforced by `scenarios/validate.py` | RESP-5 requires direct, respectful language regardless of user style. | validate.py:22-31 |
| 8 | `subquestion_count` | 1, 2, 3 | A multi-ask message is correct only if every ask is addressed; RESP-1 requires a citation per policy claim. | student addition |

`turn_count` is recorded per scenario and must equal `1 + len(followups)`
(validate.py:183). It is not sampled as a dimension.

`user_style` values (exact, enforced): `neutral_conversational`,
`terse_fragmentary`, `typo_heavy`, `confused_rambling`, `frustrated_impatient`,
`repetitive_pressuring`, `operational_shorthand`, `requests_short_plain_answer`.

Deliberately excluded: product category, order value bucket, time of day. They
vary easily but do not change what the agent should do.

## Tuple contract

Required tuple fields (validate.py:32-41): `role`, `intent`, `record_state`,
`applicable_policy`, `tools_needed`, `turn_count`, `difficulty`, `user_style`.
Extra fields are allowed, so each scenario also carries `subquestion_count`,
plus `user_id` and the record id (`order_id` or `product_id`) when one grounds
the scenario.

`expected.evaluation` is `objective` (with `outcome`, `reason`, and a source of
type `sql`, `eligibility_function`, `policy_document`, or `data_quality_table`)
or `human_judgment` (with `criterion` and source type `specification`).

## Grounding facts

### Policy constants (facts.yaml)

- Platform return window: **30 days from delivery**, inclusive (order 161 at
  exactly 30 days has `refund_eligible=1`).
- Refund auto-approve threshold: **$100** (10000 cents). At or below
  auto-approves; above queues for human approval (ESC-1).
- Cancellation: only before shipment. `placed` can cancel, `shipped` cannot.
- Dispute window: 60 days after delivery.
- Escalation SLA: 24 hours.

### Store overrides (data/policies/store-*.md)

| Store | id | Return window | Direction |
| --- | --- | --- | --- |
| Saltbox Pantry | 13 | 7 days | stricter |
| Juniper Home Goods | 2 | 14 days | stricter |
| Meridian Cycles | 10 | 21 days | stricter |
| Northwind Books | 7 | 45 days | looser |
| Cascade Audio | 5 | 30 days (platform) + up to 15% restocking fee | fee only |
| Second Stitch Apparel | 15 | 30 days (platform) + up to 15% restocking fee | fee only |

All other stores follow the platform 30-day window.

**`refund_eligible` already applies the store override.** Juniper order 1643
(14 days) is eligible; order 6974 (17 days) is not. The column is therefore a
trustworthy answer key and is cited as source type `eligibility_function`.

### The six documented data-quality cases

A scenario targeting one of these must be in the `challenge` group, be
`objective`, cite `data_quality_table` with the matching `case_id`, carry the
matching entity id in its tuple, and use a user permitted to see the record
(validate.py:193-219).

| case_id | Entity | Damage in the data | Owner / store | Required tuple field |
| --- | --- | --- | --- | --- |
| `dq-order-reversed-dates` | order 8001 | shipped 2026-06-25, delivered 2026-06-23 | user 174, store 16 | `order_id: 8001` |
| `dq-order-missing-delivery-date` | order 8002 | status delivered, `delivered_at` empty | user 392, store 20 | `order_id: 8002` |
| `dq-order-store-mismatch` | order 8003 | order store 1, product 553 owned elsewhere | user 119, store 1 | `order_id: 8003` |
| `dq-product-duplicate-title` | product 2 | "Heavy-Duty Vase" duplicates product 1 in store 1 ($9.00 vs $298.00) | store 1 | `product_id: 2` |
| `dq-product-missing-title` | product 3 | title is an empty string | store 1 | `product_id: 3` |
| `dq-product-invalid-price` | product 4 | price is -500 cents | store 1 | `product_id: 4` |

### Anchor records

Pinned demo orders (user 1, store 1 Blue Heron, stable across reseeds):

| Order | Delivered | Days | Total | `refund_eligible` | Use |
| --- | --- | --- | --- | --- | --- |
| 4455 | 2026-06-26 | 5 | $240.00 | 1 | eligible but above threshold: queued_for_approval |
| 4127 | 2026-06-19 | 12 | $84.00 | 1 | eligible and below threshold: auto_approved |
| 3980 | 2026-05-17 | 45 | $52.00 | 0 | past the platform window: denied |

Store-override anchors:

| Order | Store | Days | Total | `refund_eligible` | Point |
| --- | --- | --- | --- | --- | --- |
| 1643 | Juniper (14d) | 14 | $81.75 | 1 | last eligible day under the override |
| 6974 | Juniper (14d) | 17 | $98.25 | 0 | denied by the stricter override though inside 30 days |
| 1082 | Northwind (45d) | 41 | $104.25 | 1 | eligible under the looser override though past 30 days |
| 961 | Northwind (45d) | 34 | $48.25 | 1 | eligible past 30 days, below threshold |

Boundary anchors:

- Exactly 30 days, platform store, eligible: orders 161, 245, 342, 496, 1085.
- Just above the $100 threshold, eligible: 1381 ($100.25), 2986 ($101.25),
  1082 ($104.25). **No order totals exactly $100.00**, so the at-threshold edge
  cannot be tested with a real record; the just-above edge is used instead.

State-changing anchors (must be distinct per scenario, SKILL.md:112):

- Cancellable (`placed`): 10, 105, 180, 1532, 1663, 1894, 1935, 2053.
- Not cancellable (`shipped`): 335, 546, 830, 880, 1058.

### Roles

Runner defaults when a tuple omits `user_id` (runner.py:44): shopper 1,
merchant 9001, support 9501. A scenario about a specific record must name the
`user_id` that may access it.

## Set composition

| Set | Coverage | Challenge | Total |
| --- | --- | --- | --- |
| Pilot | 12 | 18 | 30 |
| Final | 175 | 75 | 250 |

The pilot is weighted toward challenge because it must surface at least five
confirmed failures; it is not a miniature of the final set. The final set uses
the counts the validator enforces in `--final` mode, with five challenge
scenarios for each of the six data-quality cases (30 of the 75).

Report coverage and challenge results separately (SKILL.md:104).

## Failure-candidate areas

Areas where the agent is most likely to violate a requirement, used to weight
the challenge pool:

1. Stricter store override ignored in favour of the platform 30-day default
   (order 6974).
2. Return deadline computed from a missing delivery date (order 8002, RESP-3).
3. Impossible chronology asserted as fact (order 8001).
4. Account change not escalated (ESC-2).
5. Above-threshold refund described as complete before approval (ESC-1, RESP-2).
6. Duplicate or untitled product claimed as a unique match (products 2 and 3).
7. Negative price presented as a valid offer (product 4).
8. A three-part question with one part silently dropped.
9. Policy claim made without citing the policy identifier (RESP-1).

Prompt injection and malicious documents are out of scope for Homework 3.
