# CLAUDE.md

Steering for Claude Code working on **MAGI**. Read this fully before any task. It is
deliberately short. When this file and a vibe disagree, this file wins.

---

## What MAGI is (one paragraph)

MAGI takes a question that has **no verifiable answer** and puts it to N independently
prompted agents, each committing a written rationale and a YES/NO vote **before seeing
any peer**. It preserves every rationale — including the losing one — as a durable
record, and on disagreement returns a **crux** instead of a forced answer. The output is
an artifact, not a decision. MAGI makes **no accuracy claim** and has **no benchmark**.

The full case lives in the design docs. You do not need them to build. You need this
file, the build spec, and the testing strategy.

---

## The two invariants (do not violate, ever)

These are the whole point of the project. Most "improvements" an agent is tempted to make
violate one of them. If a change touches either, stop and re-read this section.

### I. NO SYNTHESIS
The system **never** merges the positions into a single answer. There is no "final
answer," no "consensus summary," no "recommended decision" beyond the prevailing vote or
the crux.
- `Record` has **no field** that could hold a merged answer. Do not add one
  (`synthesis`, `answer`, `final`, `summary`, `consensus`, `verdict_text`, etc.).
- The terminal step builds a `Record` from `Position` objects + an `Outcome` (+ optional
  crux, + optional concurrence flag). It produces **no free text that aggregates the
  rationales**.
- If a task seems to want a "summary of what the panel decided," the answer is the
  `Record` itself, rendered faithfully. Not a synthesized paragraph.

### II. BLIND COMMITMENT
Each agent commits **without sight of any peer's output**.
- The commitment function takes the question and **exactly one agent** — never the panel,
  never a list of peer rationales. Do not add a parameter through which peer output could
  pass.
- The N commitment calls are dispatched **concurrently** and awaited together, so none can
  depend on another's result.
- A peer rationale must never appear in an agent's prompt. This is enforced by the
  function boundary and **tested by surveillance** (sentinel tokens in scripted
  rationales; assert no agent's prompt contains a peer's token). Never weaken that test.

Both invariants are **encoded in the types and call graph**, not just in docs. Keep them
there. A pre-merge gate fails if the no-synthesis field-absence test or the
blind-commitment surveillance test is removed or skipped.

---

## Hard rules

- **No agent framework.** No LangChain, CrewAI, LlamaIndex, AutoGen, or similar. They
  impose the synthesis/coordination patterns MAGI rejects; importing one smuggles the
  convergence bias back through a dependency. Talk to providers over plain async HTTP.
- **Provider is an injected seam.** Everything depends on the one-method `Provider`
  protocol, never a concrete provider. The default test double is `FakeProvider`. The
  whole engine must be testable **offline, deterministically, with no API key**.
- **The contract (`types.py`) is depended on by everything and depends on nothing.** Build
  it first; change it rarely; never loosen its validators to make a test pass.
- **Tests are structural where it matters.** For the two invariants, test the *property*
  (can it happen at all?), not an *example* (did it happen this time?). See the testing
  strategy.
- **Don't test prompt quality in the unit suite.** Whether a crux is *wise* is a prompt
  loop, not a test. Tests assert plumbing: prompt loads, fields populate, response parses.
- **`async` throughout the protocol.** The fan-out is inherently parallel; modeling it
  synchronously models it wrong.
- **Keep the public API tiny.** `Agent`, `Position`, `Record`, `Vote`, `Tier`, `Outcome`,
  and `Panel.deliberate`. Resist surface-area growth.

---

## Repo map

```
src/magi/
  __init__.py          public API (tiny)
  types.py             THE CONTRACT — build first, change rarely
  providers/
    base.py            Provider protocol (one method)
    openai_compat.py   the ONE real adapter (httpx) — the only live surface
    fake.py            deterministic test double; also records prompts
  protocol/
    commit.py          blind commitment: parallel fan-out, one agent per call
    tabulate.py        vote counting; threshold by tier
    crux.py            consequence-anchored crux (LLM call)
    concurrence.py     fragile-agreement detection (LLM call)
    engine.py          orchestrates the steps -> Record
  store/
    schema.sql         the record schema, verbatim from the spec
    sqlite.py          write, get-by-id, recent, similar
  report/
    template.html.j2   faithful, equal-weight render
    render.py
  cli.py               thin typer wrapper over the library
prompts/               versioned prompt text, SEPARATE from logic
tests/                 mirror the modules above
```

Module boundaries mirror the protocol steps on purpose: a task is usually "implement
`<module>.py` so `tests/test_<module>.py` is green." Keep it that way.

---

## Build order (each step ends green before the next)

1. `types.py` + `providers/base.py` + `providers/fake.py` — contract and test harness, no
   behavior. (Reference contract already passes 21 checks; keep them green.)
2. `protocol/commit.py` + `tabulate.py` — run a deliberation against the fake, get a
   majority result. Blind-commitment tests (surveillance + concurrency + signature) land
   here and are non-negotiable.
3. `protocol/crux.py` + `concurrence.py` — split and fragile-agreement paths. Test wiring
   and structural result only, not crux quality.
4. `store/` — schema, write, get-by-id, recent, then similar. Faithful round-trip;
   verbatim mandate (auditability).
5. `report/` — faithful, equal-weight render; minority labelled on-record, never error.
   Ties to the no-synthesis faithfulness test.
6. Two-tier handling + caller-asserted tier at the entrypoint.
7. `cli.py`; then `providers/openai_compat.py` (offline via respx; one opt-in live smoke
   test).

Don't jump ahead. Don't hold more than one module's complexity at once.

---

## Workflow expectations

- **Run the gate before declaring done:** `ruff check`, `ruff format --check`,
  `mypy --strict src`, `pytest` (excludes live by default).
- **`mypy --strict` must stay clean on `src`.** The contract is typed; enforce it.
- **Live tests are opt-in** (`-m live`, needs a key). Never make them gate ordinary work.
- **Small, reviewable commits**, one module/concern each. The invariants must remain
  visible in diffs — a change that touches synthesis or blind commitment should be
  obvious to a reviewer.
- **If a task tempts you to violate an invariant, surface it instead of doing it.** Say
  which invariant and why the task seems to want it. The likely resolution is that the
  task is misread, not that the invariant should bend.

---

## Quick self-check before any change

- Does this add a field or path that could hold a merged answer? → **Stop (Invariant I).**
- Could a peer rationale reach an agent's prompt after this? → **Stop (Invariant II).**
- Am I adding a framework or a heavy dependency? → **Stop (hard rule).**
- Am I testing whether a prompt is *good* rather than *wired*? → **Wrong layer.**
- Did I loosen a `types.py` validator to pass a test? → **Fix the test, not the contract.**

If all five are clear, proceed.
