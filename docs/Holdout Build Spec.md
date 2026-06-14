
> **Package identity note:** The project ships as the `holdout` package (`pip install holdout`,
> `from holdout import ...`, CLI command `holdout`). "MAGI" is the internal codename and the
> source of the report aesthetic and persona names (Melchior, Balthasar, Caspar). Prose
> references to "MAGI" in this document mean the concept and design; the installable package,
> CLI, and import paths are all `holdout`.

**MAGI**
**BUILD SPECIFICATION**
*What to implement, and nothing else.*

# 1. What We Are Building
MAGI takes a question that has no verifiable answer at the time it is asked, puts it to several independently-prompted reasoners, and produces a durable record of their competing positions — with the losing reasoning retained in full rather than merged away. On disagreement it returns a structured crux instead of a forced answer. The output is an artifact, not a decision.

## 1.1 In Scope
- Putting one question to N independently-prompted agents (N odd; default 3).
- Collecting a written rationale and a YES/NO position from each, committed before any agent sees another's output.
- Counting positions against a reversibility threshold and producing either a result or a crux.
- Writing the full deliberation to a durable, queryable store and rendering it as a self-contained report file.
- Running at decision time, in the workflow path — emitting the record at the moment of deliberation, before the decision is resolved.
## 1.2 Explicitly Out of Scope
- No synthesis or merge step. The system must never collapse the positions into one answer.
- No accuracy claim and no benchmark target. Correctness of the underlying decision is not the system's concern.
- No automatic decision-making. On a split the system returns an input to a human, never a verdict to obey.
- No learning, scoring, or calibration of agents over time. The store records; it does not analyze.
- No fixed review schedules or automated reminders.
- Not a retrospective tool. MAGI does not reconstruct or audit a decision after it has already been resolved elsewhere; if the decision is already made, there is no longer any unresolved dissent to preserve. (This concerns capture, not retrieval: records captured at their own commit time may, of course, be retrieved later as precedent — that is the compounding mechanism, not retrospection.)
## 1.3 When MAGI Runs: At Decision Time, Not After
MAGI must be invoked at the moment a decision is being made, as part of the workflow that makes it — not as a post-hoc audit. This is a build constraint, not a preference, and it follows directly from what the system preserves.
The value of the record is the unresolved disagreement: the competing positions and the losing reasoning, captured while they still exist. Once a decision is resolved — once a human or a downstream system has picked an outcome and moved on — the dissent has already been flattened into that outcome, and there is nothing left for MAGI to preserve. A forensic record of a settled decision (what was chosen, by whom, under which policy) is a different and lesser artifact; capturing it is explicitly out of scope. MAGI's record exists only because it is taken before resolution.
Implementation consequence: the deliberation must run synchronously in the decision path and emit its record as a precondition to, or concurrent with, the decision — never afterward from logs. An integration that calls MAGI to explain a decision already taken has misused it.
# 2. The Boundary (a Build Constraint, Not a Philosophy)
MAGI applies only to questions without a verifiable answer at decision time. This is a hard constraint on the implementation, not a stylistic preference, because the system behaves correctly on one class of question and incorrectly on the other.

Implementation consequence: the entrypoint should make the caller assert the question is of the second type, and the documentation must steer answerable questions elsewhere. Routing a question-with-an-answer through MAGI produces confident, unfounded agreement — the one failure mode the design exists to avoid.
# 3. Architecture
The smallest structure that delivers the requirement. Three components: the panel, the protocol, the store.
## 3.1 The Panel
N agents (N odd; default 3), each given a fixed reasoning mandate — a constraint on what kind of evidence it may invoke, not a personality. A representative default set of three:
- Empirical: reasons from data, precedent, and measurable outcomes.
- Principled: reasons from duty, cost, and the interests of stakeholders not present.
- Practitioner: reasons from pattern, prior cases, and tacit experience.
N and the specific mandates are caller-configurable. Nothing in the system depends on exactly three agents or on these particular mandates; this is held loosely by design.
## 3.2 The Protocol
- Blind commitment. Each agent receives only the question and its own mandate, and returns a written rationale plus a YES/NO position before any agent's output is shown to any other. This step is load-bearing and non-negotiable: it is the difference between independent positions and a convergence cascade. Implementations must not leak peer rationales into an agent's context prior to its commitment.
- Tabulation. Count positions against the threshold for the decision's reversibility tier (Section 4).
- Crux extraction (on a split). A separate neutral pass — not any of the N agents — reads all rationales and returns the single falsifiable question whose resolution would most likely change the outcome. The crux must be consequence-anchored: it names the specific adverse outcome the minority is reasoning about, not merely the locus of disagreement. The crux, not the bare fact of disagreement, is the deliverable of a split.
- Concurrence check (on agreement). When agents reach the same position for incompatible reasons, flag the result as fragile agreement. Agreement on contradictory rationales is materially different from agreement on convergent ones and must be recorded as such, not silently counted as consensus.
- Record. Write the question, every rationale, every position, the outcome or crux, and any concurrence flag to the store, and render the report file.
## 3.3 No Synthesis Step
There must be no agent or post-process that merges the positions into a single answer, and no recommendation beyond the prevailing position or the crux. This is the central architectural commitment. A synthesis step would dissolve the dissent the system exists to preserve and would collapse MAGI into the synthesis tools it is meant to differ from. Its absence is the design, not an omission.
## 3.4 The Store
A durable local store — SQLite in the reference implementation — holding one structured record per deliberation. The store records and retrieves; it does not analyze, score, or learn.
### Record schema (reference)
deliberation
  id            TEXT PRIMARY KEY     # stable identifier for retrieval/citation
  created_at    TEXT                 # ISO 8601 timestamp
  question      TEXT                 # the question as asked
  tier          TEXT                 # 'reversible' | 'hard_to_reverse'
  outcome       TEXT                 # 'majority' | 'split' | 'fragile_agreement'
  crux          TEXT                 # consequence-anchored crux; null unless split
  concurrence   INTEGER              # 1 if agreement rests on incompatible reasons

position  (one row per agent)
  deliberation_id  TEXT              # FK -> deliberation.id
  agent_mandate    TEXT              # the exact mandate text used (for auditability)
  rationale        TEXT              # the agent's full written rationale, verbatim
  vote             TEXT              # 'yes' | 'no'
The agent_mandate is stored verbatim so the conditions of the deliberation are auditable from the record alone — a stacked panel is then visible in the artifact rather than hidden.
### Retrieval and Compounding Precedent
Records must be retrievable by identifier and by recency. They must also be retrievable by similarity to a new question, so that a past dissent surfaces when a kindred decision recurs. This is not a convenience feature; it is the mechanism by which the record compounds into something valuable. A single preserved dissent is useful at one postmortem. An accumulating, searchable body of past dissents — where every new deliberation can find the prior cases that resemble it — becomes organizational memory that is expensive to reconstruct and therefore hard to replace. The store grows more useful with every deliberation written to it, and similarity retrieval is what converts a pile of records into precedent. It requires no scoring or ranking of agents to deliver this.
# 4. Decision Handling
Two tiers, distinguished only by reversibility. No further classification and no fixed review intervals.

Implementation notes. The caller supplies the tier; the system does not infer it and does not prevent mis-tiering. The boundary between tiers is intentionally coarse. Both are acceptable: the tier affects only the acting threshold and the split behavior, never whether the dissenting rationale is preserved — which happens in every case regardless of tier.
# 5. The Report Artifact
The rendered report is the primary deliverable: a self-contained file that makes a contested decision's reasoning permanently accessible and attachable to a pull request, decision log, or postmortem.
## 5.1 Required Contents
- The question, verbatim.
- Every position in full — the agent mandate and the complete rationale — shown at equal visual weight.
- The vote tally and the outcome (majority result, split, or fragile agreement).
- On a split: the consequence-anchored crux.
- On fragile agreement: the concurrence flag and a note that the shared position rests on incompatible reasons.
- The record identifier, for retrieval and citation.
## 5.2 Required Properties
- The minority position is labelled as a position on record, never as an error or a rejected answer. An outvoted qualified position has not been disproven.
- The report is faithful to the record: it adds no synthesis, recommendation, or editorializing beyond what the protocol produced.
- Visual styling is not specified here and is not load-bearing. A plain or minimally-formatted report delivers the entire requirement; richer styling is optional.
# 6. Interfaces
## 6.1 Library
A minimal programmatic surface. Representative shape:
from holdout import Panel, Agent

panel = Panel([
    Agent('empirical',   'Reason from data and measurable outcomes'),
    Agent('principled',  'Reason from duty, cost, and absent stakeholders'),
    Agent('practitioner','Reason from pattern, precedent, and experience'),
])

record = panel.deliberate(
    'Should we move the auth service to a new language?',
    tier='hard_to_reverse',   # caller asserts reversibility
)

record.outcome      # 'majority' | 'split' | 'fragile_agreement'
record.positions    # full rationale + vote per agent, verbatim
record.minority     # the preserved losing rationale (None if unanimous-convergent)
record.crux         # consequence-anchored crux (None unless split)
record.concurrence  # True if agreement rests on incompatible reasons
record.to_report()  # render the self-contained report file
## 6.2 Command Line
A thin wrapper over the library for use without writing code:
# run a deliberation
holdout "Should we adopt this dependency?" --tier hard_to_reverse

# write the report to a file for attachment
holdout "..." --tier reversible --report decision-dep-adopt.html

# retrieve a past record by id, or by similarity to a new question
holdout record <id>
holdout similar "Should we adopt a different dependency?"
## 6.3 Providers
Any OpenAI-compatible endpoint. Agents may use different models, and parallel-dispatch infrastructure may be used for the fan-out. The only provider-level constraint is the blind-commitment guarantee: an agent's call must not include any peer rationale produced in the same deliberation prior to that agent's own commitment.
# 7. Build Order
- Panel + blind-commitment protocol against one provider; positions collected and tabulated; majority result returned. No store, no report yet.
- Crux extraction (consequence-anchored) and concurrence check added to the protocol.
- The store: schema, write-on-deliberate, retrieval by id and recency, then retrieval by similarity.
- Report rendering: faithful, equal-weight, plain styling first.
- Two-tier handling and the caller-asserted tier at the entrypoint.
- CLI wrapper; multi-provider and per-agent model configuration.
# 8. Acceptance Criteria
The build is correct when all of the following hold by inspection — no benchmark required:
- Given a question and N mandates, no agent's committed rationale could have been influenced by another agent's output (blind commitment holds).
- Every rationale, including every losing one, appears verbatim in the stored record and in the report.
- No output anywhere merges the positions into a single synthesized answer.
- A split yields a consequence-anchored crux and no forced verdict; the report escalates rather than decides.
- Agreement reached on incompatible reasons is flagged as fragile, not counted as plain consensus.
- The stored agent mandates make the conditions of any deliberation auditable from the record alone.
- A past record can be retrieved by identifier, by recency, and by similarity to a new question — and the similarity path returns a kindred prior record, so accumulated records function as searchable precedent.
- The deliberation runs in the decision path and emits its record before or at the moment of resolution; the public API offers no path to construct a record from logs of an already-resolved decision.
# 9. Carried Implementation Risks
Two risks are unresolved and bear directly on the build. They are recorded here so they are designed around, not discovered late. Neither blocks construction; both bound the claims the finished system may make.
## 9.1 Role-Played vs. Authentic Dissent
Agents are given assigned mandates, and assigned-role dissent may carry less cognitive value than genuinely held dissent. Blind commitment is the strongest available mitigation but is not a cure. Build consequence: do not let the system or its documentation claim the dissent is authentic; claim only that competing rationales are preserved. Whether assigned-role dissent has real value is an empirical question to be tested, not asserted.
## 9.2 Dissent vs. Variance
With a single base model under N mandates, observed disagreement may be genuine dissent or merely sampling variance in costume. Build consequence: the value of the record does not depend on resolving this — preserving even correlated rationales beats preserving nothing. Using distinct base models per agent is a supported strengthening but introduces capability-difference confounds; it is an option, not a default, and is not required for the system to meet its acceptance criteria.

**BUILD SPECIFICATION — IMPLEMENTATION REFERENCE**
*The case for the system is a separate document. This one only says what to build.*

