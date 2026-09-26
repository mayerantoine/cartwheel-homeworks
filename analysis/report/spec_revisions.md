# Specification revisions from error analysis

Homework 4 asks that a desired behaviour not yet required by `SPEC.md` be
recorded as a specification gap and the requirement revised *before* any
failure label is assigned, because an evaluator built against an unwritten
requirement measures the reviewer's drifting opinion rather than a commitment.

## Revision 1: RESP-1, policy citation by audience

**Status:** applied to `SPEC.md`.

### Motivating annotation

| | |
| --- | --- |
| Annotation id | `amuiicrsrjiqz` |
| Trace | `36dff227db559665888edb42e1dac6f9` |
| Scenario | `support-005` (shopper, dispute, well_specified) |
| Selected span | `agent handles them (cw-disputes). Y` |
| Note | "dont display policy nane" |
| Recorded | 2026-09-26T14:51:40Z |

### Supporting evidence

27 annotations across 24 reviewed traces record the same objection. **Every
one is on a shopper trace**, which is what motivated an audience-based split
rather than removing the citation requirement outright.

Across the whole gpt-6-luna run, **163 of 279 shopper traces** print a raw
policy identifier in an assistant reply, so this is the dominant surface
behaviour rather than an occasional slip.

### The conflict

The agent was doing what it was told. The original requirement read:

> **RESP-1.** Cite the policy identifier for every claim derived from a policy
> document.

and `agent/agent.py:70` instructs the model to "Cite the policy id (for example
cw-returns) for every policy claim." So the observed behaviour satisfied the
specification, and the disagreement was with the specification, not the agent.

### The decision

A policy identifier is an internal retrieval key. A shopper cannot look up
`cw-disputes`, so printing it adds noise without adding checkability. Merchants
and support staff do work with the policy catalogue and use the identifier to
find the source document. Grounding must still be checkable for every reply,
which the trace preserves regardless of what the user sees.

RESP-1 was therefore split by audience into RESP-1a (shopper: plain language
and human-readable titles, no raw identifier), RESP-1b (merchant and support:
cite the identifier), and RESP-1c (record the identifier in the trace for every
reply).

### Consequences

- The 27 annotations become labelable against RESP-1a rather than being
  withdrawn, because the requirement now says what they assumed.
- This is a **specification failure, not a generalization failure**. The fix is
  a prompt edit at `agent/agent.py:70`, which currently mandates the behaviour
  under revision. Per the error-analysis skill (phase 6), specification
  failures are fixed before an evaluator is built, and the fix should show up
  as a prevalence drop between prompt versions.
- The mode's evaluator is a **code check**, not an LLM judge: "does a
  shopper-facing assistant message match `\b(cw-[a-z-]+|store-[a-z0-9-]+)\b`"
  is deterministic and needs no interpretation.
- Any judgment on this mode applies only to traces produced *after* the prompt
  edit. Labeling the current traces measures the old specification.
