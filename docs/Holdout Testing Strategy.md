> **Package identity note:** The project ships as the `holdout` package (`pip install holdout`,
> `from holdout import ...`, CLI command `holdout`). "MAGI" is the internal codename and the
> source of the report aesthetic and persona names (Melchior, Balthasar, Caspar). Prose
> references to "MAGI" in this document mean the concept and design; the installable package,
> CLI, and import paths are all `holdout`.

**MAGI**

**TESTING STRATEGY**

*How we know the build is correct without a benchmark.*

**1. The Testing Premise**

MAGI makes no accuracy claim, so there is no benchmark to pass and no ground-truth dataset to score against. The build is correct when its acceptance criteria hold by inspection. The job of the test suite is to turn each criterion into an automated, deterministic check --- so that \'by inspection\' becomes \'by a green test run,\' repeatable on every change.

This has a sharp consequence for what we test and how. We never test whether a crux is wise or a rationale is persuasive --- those are prompt-quality questions no unit test can answer. We test that the structure holds: that blind commitment is real, that no synthesis ever occurs, that dissent is preserved verbatim, that the store round-trips faithfully. The two most important invariants are tested structurally, not by example.

+--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
| **The distinction that shapes everything**                                                                                                                                                                                                                                                                                                                                     |
|                                                                                                                                                                                                                                                                                                                                                                                |
| Most tests verify behavior on chosen inputs. Two of our invariants --- no synthesis, and blind commitment --- cannot be adequately tested that way, because a clever input passing is not evidence the property holds universally. These are tested as structural guarantees: properties of the types and call graph that no input could violate. Sections 4 and 5 cover this. |
+--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+

**2. The Pyramid, Sized for This Project**

The suite is deliberately bottom-heavy. Because the provider is an injectable seam (Section 3), almost everything can be a fast offline unit test. Live tests against a real endpoint are rare, opt-in, and verify plumbing only.

  -------------------------------------------------------------------------------------------------------------------------------------------------------------
  **Layer**     **What it covers**                                                                             **Count**         **Speed**      **Network**
  ------------- ---------------------------------------------------------------------------------------------- ----------------- -------------- ---------------
  Unit          Types, tabulation, crux/concurrence wiring, store ops, report render. The bulk of the suite.   Many              Milliseconds   None

  Invariant     The two load-bearing guarantees, tested structurally (no-synthesis, blind commitment).         Few but central   Milliseconds   None

  Integration   Full engine end-to-end against the FakeProvider; CLI over the library.                         Some              Fast           None

  Live          One real provider adapter: auth, request shape, response parsing, error propagation.           Minimal           Seconds        Real (opt-in)
  -------------------------------------------------------------------------------------------------------------------------------------------------------------

Live tests are marked and excluded by default; they run only with an explicit opt-in and a configured key. The entire rest of the suite runs with no key, no network, and full determinism --- which is what lets an agent iterate quickly and safely.

**3. The Seam That Makes It Testable**

Everything rests on one design choice: the \`Provider\` is a one-method protocol, and the engine depends on the interface, never a concrete provider. The default test double, \`FakeProvider\`, returns scripted responses by matching substrings of the prompt and records every prompt it received.

> \# Stage any outcome deterministically by scripting per-mandate responses.\
> fake = FakeProvider(rules=\[\
> (\'empirical\', \'\... POSITION: NO (cost exceeds benefit)\'),\
> (\'principled\', \'\... POSITION: YES (duty to users)\'),\
> (\'practitioner\',\'\... POSITION: NO (team lacks the experience)\'),\
> \])\
> record = await Panel(agents, provider=fake).deliberate(q, tier=\'hard_to_reverse\')\
> \# -\> a 1-2 split, fully deterministic, no network, sub-millisecond

Because the fake records prompts, it is also the instrument for the blind-commitment test (Section 5). Two roles, one double: it stages outcomes and it surveils the call graph.

**4. Invariant I --- No Synthesis (Structural)**

The central architectural commitment is that the system never merges the positions into one answer. Testing this by example is insufficient: showing that ten chosen deliberations produced no merged answer does not prove an eleventh could not. So the property is enforced structurally and tested at that level.

**How it is enforced**

- The \`Record\` type has no field capable of holding a synthesized or final answer. There is nowhere to put one. Adding synthesis would require adding a field, which is a visible, reviewable type change.

- The engine\'s terminal step constructs a \`Record\` from the collected \`Position\` objects plus an \`Outcome\`, a possible crux, and a possible concurrence flag --- and nothing else. No code path produces free text that aggregates the rationales into a verdict.

**How it is tested**

1.  Field-absence test: assert the \`Record\` model exposes no field whose name or type could carry a merged answer (no \`synthesis\`, \`answer\`, \`final\`, \`summary\`, \`consensus\` field). This is a guard against a future change silently reintroducing synthesis.

2.  Output-faithfulness test: for representative deliberations across all outcomes, assert every agent rationale appears in the report verbatim and the report contains no text not traceable to a Position, the crux, or fixed template chrome.

3.  Minority-preservation test: assert \`record.minority\` returns the full losing Position objects, byte-for-byte equal to what the agents produced --- never a shortened or paraphrased form.

+--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
| **Why structural beats example here**                                                                                                                                                                                                                                                                        |
|                                                                                                                                                                                                                                                                                                              |
| An example test answers \'did synthesis happen this time?\' A structural test answers \'can synthesis happen at all?\' The second is the property we actually need, and it is the one that protects the invariant against future edits made by someone --- or some agent --- who did not read this document. |
+--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+

**5. Invariant II --- Blind Commitment (Structural + Surveillance)**

Each agent must commit its position without sight of any peer\'s output. This is the difference between independent positions and a convergence cascade. It is protected two ways: a function boundary that makes leakage impossible by construction, and a surveillance test that catches leakage if the boundary is ever weakened.

**How it is enforced**

- The commitment function takes the question and exactly one agent --- never the panel and never a collection of peer outputs. Its signature gives it no access to other agents\' rationales, so it cannot include them in a prompt.

- The engine fans out the N commitment calls concurrently and awaits them together. Because they are launched before any result is available, no call can depend on another\'s output even by accident of ordering.

**How it is tested**

4.  Surveillance test (the key one): run a full deliberation through a FakeProvider whose scripted rationales contain distinctive sentinel strings (e.g. each agent\'s rationale embeds a unique token). After the run, inspect every recorded prompt and assert that no agent\'s prompt contains any other agent\'s sentinel. If a peer rationale ever leaks into a prompt, this fails loudly.

5.  Concurrency test: assert the N commitment calls are dispatched before any completes --- for instance with a provider double that records dispatch order and blocks until all N have been entered. This proves the fan-out is genuinely parallel, not sequential with hidden coupling.

6.  Signature test: a static check (mypy plus a small assertion) that the commitment entrypoint accepts a single agent and the question, and has no parameter through which peer output could be passed.

> \# Surveillance test, in essence:\
> fake = FakeProvider(rules=\[\
> (\'empirical\', \'rationale_E \<\<TOKEN_E\>\>\'),\
> (\'principled\', \'rationale_P \<\<TOKEN_P\>\>\'),\
> (\'practitioner\',\'rationale_X \<\<TOKEN_X\>\>\'),\
> \])\
> await Panel(agents, provider=fake).deliberate(q, tier=\'reversible\')\
> \
> for prompt in fake.prompts_containing(\'empirical\'):\
> assert \'\<\<TOKEN_P\>\>\' not in prompt \# no principled leak\
> assert \'\<\<TOKEN_X\>\>\' not in prompt \# no practitioner leak\
> \# \... repeated for every agent vs every peer

**6. Per-Module Test Plan**

Each module\'s tests are self-contained and map to a build step, so a task is always \'make this module\'s tests green.\'

**types.py --- the contract**

- Construction rejects: empty mandate, whitespace name, panel size \< 3, even panel size.

- Cross-field invariants reject: SPLIT without crux, crux on non-SPLIT, FRAGILE_AGREEMENT without concurrence, concurrence on non-fragile.

- Derived accessors: tally counts, prevailing side, minority is the losing positions verbatim, split preserves all positions.

- (These already pass against the reference contract; they become the regression net.)

**protocol/commit.py --- blind commitment**

- Surveillance, concurrency, and signature tests from Section 5.

- A well-formed provider response parses into a Position with the agent\'s mandate stored verbatim.

- A malformed or empty provider response raises rather than producing an invalid Position.

**protocol/tabulate.py --- counting and thresholds**

- Reversible tier: simple majority returns MAJORITY with the correct prevailing side.

- Hard-to-reverse, unanimity required: anything short of unanimous returns SPLIT.

- Hard-to-reverse, majority permitted: majority returns MAJORITY but flags dissent for prominent surfacing.

- Boundary: with odd N, every vote distribution resolves to exactly one of the outcomes (no undefined state).

**protocol/crux.py and concurrence.py --- wiring only**

- On a split, the crux pass is invoked and a non-empty crux is attached to the Record (the prompt\'s quality is out of scope for tests).

- On unanimous-but-incompatible rationales, concurrence detection sets the flag and the outcome becomes FRAGILE_AGREEMENT.

- On unanimous-and-convergent rationales, the flag is not set and the outcome is MAJORITY.

- Note: crux and concurrence are themselves LLM calls. Tests assert the code path and the structural result, never the semantic quality. Quality lives in the prompt-tuning loop (Section 7).

**store/sqlite.py --- the record store**

- Write then get-by-id returns a byte-faithful Record, including every rationale and mandate verbatim.

- Recency retrieval returns records in correct order.

- Similarity retrieval returns a kindred prior record for a related question (against a small seeded fixture; similarity quality is best-effort, presence and ordering are the assertion).

- Idempotency: writing the same record id twice does not corrupt the store; behavior (reject or replace) is defined and tested.

- The stored agent mandate is present and verbatim --- the auditability guarantee.

**report/render.py --- the artifact**

- Every rationale appears verbatim; minority shown at equal weight and labelled as on-record, never as error or rejected.

- No synthesized text (ties to Invariant I faithfulness test).

- Split renders the crux and escalation language; fragile agreement renders the concurrence note; majority renders neither.

- The record identifier appears for citation.

**cli.py --- thin wrapper**

- \`holdout \"q\" \--tier \...\` runs a deliberation and writes a report file.

- Omitting or mis-spelling the tier is rejected with a clear message (the caller must assert the tier).

- \`holdout record \<id\>\` and \`holdout similar \"q\"\` retrieve from the store.

- CLI tests run against the FakeProvider via dependency injection --- no network.

**providers/openai_compat.py --- the only live surface**

- Offline, with respx mocking httpx: correct request shape, auth header present, response parsed into text, HTTP and timeout errors propagate as raises.

- Concurrent safety: multiple in-flight completions do not interleave state.

- Live (opt-in, marked): a single smoke test that a real endpoint returns a parseable completion. Excluded from the default run.

**7. What the Suite Deliberately Does Not Test**

Three prompts carry semantic weight: the per-agent commitment prompt, the crux-extraction prompt, and the concurrence-detection prompt. Their wording determines output quality, and quality is not unit-testable --- only plumbing is. Conflating the two would produce brittle tests that break on harmless rewording and still fail to measure what matters.

- Prompts live as versioned text files under \`prompts/\`, separate from logic, so they can be tuned without touching tested code paths.

- Tests assert the prompt is loaded, populated with the right fields, and that its response is parsed correctly --- never that the response is good.

- Prompt quality is evaluated by a separate, human-in-the-loop iteration against held example deliberations, tracked outside the unit suite. This is the one place \'inspection\' stays human, and the strategy says so plainly rather than pretending a test covers it.

**8. Acceptance Criteria → Tests**

Each build-spec acceptance criterion maps to a specific test, so \'accepted\' means \'these tests are green.\'

  -----------------------------------------------------------------------------------------------------------------------------------------------------
  **Acceptance criterion**                                                         **Verifying test**
  -------------------------------------------------------------------------------- --------------------------------------------------------------------
  No agent\'s rationale could be influenced by another\'s (blind commitment)       Surveillance + concurrency + signature tests (5)

  Every rationale, including losing ones, retained verbatim in record and report   types minority test; report faithfulness test (4,6)

  No output merges positions into one answer                                       Field-absence + output-faithfulness tests (4)

  Split yields a consequence-anchored crux and no forced verdict                   tabulate split tests; crux wiring test; report escalation test (6)

  Agreement on incompatible reasons flagged as fragile                             concurrence tests; report concurrence-note test (6)

  Stored mandates make deliberations auditable from the record alone               store verbatim-mandate test (6)

  Records retrievable by id, recency, and similarity                               store retrieval tests (6)
  -----------------------------------------------------------------------------------------------------------------------------------------------------

**9. Continuous Integration**

- Default CI run: ruff (lint + format check), mypy \--strict on src, and pytest excluding the live marker. Fully offline; fast enough to run on every push.

- Coverage is reported but not fetishized: the invariant and faithfulness tests matter more than a line-coverage number. Target meaningful coverage of the protocol and store; do not chase coverage of trivial code.

- Live tests run on a separate, manual or scheduled job with a configured key, never gating ordinary changes.

- A pre-merge gate fails if the no-synthesis field-absence test or the blind-commitment surveillance test is removed or skipped --- the two invariants cannot be silently disabled.

**TESTING STRATEGY --- TEST PLAN**

*Correct by inspection becomes correct by a green run. The two invariants are tested as structure, not example.*
