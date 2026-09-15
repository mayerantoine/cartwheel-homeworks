# System prompt gap analysis

This review compares the default `SYSTEM_PROMPT_TEMPLATE` in `agent/agent.py` with the requirements in `SPEC.md`. It identifies nine substantive prompt gaps, including two direct contradictions with the specification.

## Direct contradictions

### 1. Above-threshold refunds use the wrong workflow — ESC-1

The spec requires calling `issue_refund`, which creates a `queued_for_approval` refund, followed by an explanation of that result. The prompt instead directs the model to call `escalate_to_human`. This can prevent the required refund record from being created.

- Spec: `SPEC.md:95-97`
- Prompt: `agent/agent.py:74-77`

### 2. Account changes are refused instead of escalated — ESC-2

The spec sends account changes of any kind to a human. The prompt refuses payment-card or credential changes and gives no escalation instruction for other account changes.

- Spec: `SPEC.md:98`
- Prompt: `agent/agent.py:59-62`

## Missing or incomplete requirements

### 3. Tool grounding is phrased as optional — PURPOSE-1 and SCOPE-1

The spec says the agent acts through tools and answers product and policy questions from authoritative sources. The prompt merely says to “prefer” tools over memory, allowing unsupported memory-based answers. Product answers also are not explicitly routed to `search_products`.

- Spec: `SPEC.md:27-30`, `SPEC.md:34-39`
- Prompt: `agent/agent.py:64-66`

### 4. Payment-credential handling is not fully refused — SCOPE-2

The spec refuses any payment-credential handling. “Payment-card or credential changes” only clearly prohibits changes; it does not prohibit requesting, receiving, repeating, or otherwise handling credentials.

- Spec: `SPEC.md:41-45`
- Prompt: `agent/agent.py:59-62`

### 5. Disputes are not explicitly escalated — ESC-3

The spec says disputes always go to a human. The generic “when you are unsure” rule is insufficient because a model might confidently answer a dispute question from the help center without escalating it. Requests unresolved after consulting the help center and order record are also only implicitly covered.

- Spec: `SPEC.md:99-100`
- Prompt: `agent/agent.py:74-77`

### 6. Success claims are only guarded for refunds, and even that guard is incomplete — RESP-2

The spec prohibits claiming that any action succeeded until its tool reports success. The prompt only says not to promise or issue a refund before checking the order. After `get_order`, the model could still claim success without calling `issue_refund`; cancellation and ticket creation are not covered at all.

- Spec: `SPEC.md:108`
- Prompt: `agent/agent.py:71-72`

### 7. Missing or inconsistent information is not addressed — RESP-3

Nothing tells the model to identify missing or contradictory dates, statuses, amounts, or tool results instead of inventing a value. “When you are unsure, escalate” does not require disclosure of what is missing or inconsistent.

- Spec: `SPEC.md:109`
- Prompt: `agent/agent.py:74-77`

### 8. Escalation explanations are incomplete — RESP-4

Refusals must be explained, and the prompt covers that reasonably well. For escalations, however, it only says to tell the user that a human will follow up; it does not require explaining why the case was escalated. The global instruction not to reveal another user’s data does provide partial privacy coverage.

- Spec: `SPEC.md:110`
- Prompt: `agent/agent.py:74-77`, `agent/agent.py:82-84`

### 9. Relevant decisions are not consistently explained — RESP-5

“Plain and warm” broadly covers tone, but the prompt only explicitly requires explanations before tool calls and for refusals. It does not require explaining eligibility decisions, failed actions, queued actions, cancellations, or other consequential outcomes.

- Spec: `SPEC.md:111`
- Prompt: `agent/agent.py:67-69`, `agent/agent.py:79-84`

## Incomplete tool-selection guidance

The tools are registered and described to the model separately, so these omissions are partially compensated outside the prompt. Nevertheless, the prompt contains no explicit workflow for:

- Fetching the full document with `get_policy` after `search_help_center`.
- Using `search_products` for product facts.
- Using `list_my_orders` or `find_order` when an order is unspecified.
- Handling cancellation requests through `cancel_order`.
- Calling `issue_refund` and distinguishing `auto_approved` from `queued_for_approval`.
- Responding correctly to structured tool failures such as `permission_denied`, `not_eligible`, and `paused`.

See the tool inventory in `SPEC.md:63-91` and the current prompt guidance in `agent/agent.py:64-77`.

## Extra prompt rule not required by the spec

The prompt mandates a one-sentence explanation of reasoning before every tool call. The spec requires direct explanations of decisions, but not mandatory pre-tool narration. This extra rule can add latency and repetitive text without closing any of the gaps above.

- Prompt: `agent/agent.py:67-69`

## Intentionally not a prompt gap

`AUTH-1` should not be copied into the prompt as the security boundary. The spec explicitly places authorization in `agent/auth.py` and the tool functions. The prompt’s privacy language is useful defense-in-depth, but tool-layer enforcement is the required control.

- Spec: `SPEC.md:47-61`

## Adjacent documentation error

The mapping comment says `TOOL-1 through TOOL-8`, although the spec defines `TOOL-9` (`escalate_to_human`).

- Comment: `agent/agent.py:38-42`
- Spec: `SPEC.md:77`

## Verification

This was a static, offline comparison. No live-model checks were run.
