"""Ad-hoc verification that the type contract enforces the spec's invariants.
Not the test suite -- just a fast sanity check that the encoded guarantees fire."""

import asyncio
import sys

sys.path.insert(0, "src")

from holdout.types import Agent, Position, Record, Vote, Tier, Outcome  # noqa: E402
from holdout.providers.fake import FakeProvider  # noqa: E402
from holdout.providers.base import Provider  # noqa: E402

ok = 0
fail = 0

def check(label, cond):
    global ok, fail
    if cond:
        ok += 1
        print(f"  PASS  {label}")
    else:
        fail += 1
        print(f"  FAIL  {label}")

def expect_error(label, fn):
    global ok, fail
    try:
        fn()
        fail += 1
        print(f"  FAIL  {label}  (expected an error, none raised)")
    except Exception:
        ok += 1
        print(f"  PASS  {label}  (correctly rejected)")


def positions(votes):
    """Build positions from a list of votes, with distinct mandates."""
    return tuple(
        Position(
            agent_name=f"a{i}",
            agent_mandate=f"mandate {i}",
            rationale=f"rationale {i}",
            vote=v,
        )
        for i, v in enumerate(votes)
    )


print("\n[1] Agent validation")
expect_error("empty mandate rejected", lambda: Agent(name="x", mandate=""))
expect_error("whitespace name rejected", lambda: Agent(name=" x ", mandate="m"))
check("valid agent constructs", Agent(name="empirical", mandate="reason from data").name == "empirical")

print("\n[2] Panel size invariants")
expect_error("two positions rejected (need >=3)",
             lambda: Record(id="1", created_at="t", question="q", tier=Tier.REVERSIBLE,
                            positions=positions([Vote.YES, Vote.NO]), outcome=Outcome.MAJORITY))
expect_error("four positions rejected (must be odd)",
             lambda: Record(id="1", created_at="t", question="q", tier=Tier.REVERSIBLE,
                            positions=positions([Vote.YES, Vote.YES, Vote.NO, Vote.NO]),
                            outcome=Outcome.MAJORITY))

print("\n[3] No-synthesis invariant (structural)")
check("Record has no synthesized-answer field",
      "synthesis" not in Record.model_fields and "answer" not in Record.model_fields
      and "final" not in Record.model_fields)

print("\n[4] Crux / outcome cross-field invariants")
expect_error("SPLIT without crux rejected",
             lambda: Record(id="1", created_at="t", question="q", tier=Tier.HARD_TO_REVERSE,
                            positions=positions([Vote.YES, Vote.NO, Vote.YES]),
                            outcome=Outcome.SPLIT))
expect_error("crux on non-SPLIT rejected",
             lambda: Record(id="1", created_at="t", question="q", tier=Tier.REVERSIBLE,
                            positions=positions([Vote.YES, Vote.YES, Vote.NO]),
                            outcome=Outcome.MAJORITY, crux="some crux"))
check("SPLIT with crux constructs",
      Record(id="1", created_at="t", question="q", tier=Tier.HARD_TO_REVERSE,
             positions=positions([Vote.YES, Vote.NO, Vote.YES]),
             outcome=Outcome.SPLIT, crux="minority fears X").outcome is Outcome.SPLIT)

print("\n[5] Fragile-agreement / concurrence invariants")
expect_error("FRAGILE_AGREEMENT without concurrence rejected",
             lambda: Record(id="1", created_at="t", question="q", tier=Tier.REVERSIBLE,
                            positions=positions([Vote.YES, Vote.YES, Vote.YES]),
                            outcome=Outcome.FRAGILE_AGREEMENT))
expect_error("concurrence on non-fragile rejected",
             lambda: Record(id="1", created_at="t", question="q", tier=Tier.REVERSIBLE,
                            positions=positions([Vote.YES, Vote.YES, Vote.NO]),
                            outcome=Outcome.MAJORITY, concurrence=True))

print("\n[6] Derived accessors")
maj = Record(id="1", created_at="t", question="q", tier=Tier.REVERSIBLE,
             positions=positions([Vote.YES, Vote.YES, Vote.NO]), outcome=Outcome.MAJORITY)
check("tally counts correctly", maj.tally == {Vote.YES: 2, Vote.NO: 1})
check("prevailing is YES", maj.prevailing is Vote.YES)
check("minority is the single NO position, verbatim",
      len(maj.minority) == 1 and maj.minority[0].vote is Vote.NO
      and maj.minority[0].rationale == "rationale 2")

split = Record(id="2", created_at="t", question="q", tier=Tier.HARD_TO_REVERSE,
               positions=positions([Vote.YES, Vote.NO, Vote.YES]),
               outcome=Outcome.SPLIT, crux="c")
check("split prevailing is None", split.prevailing is None)
check("split minority preserves all positions", len(split.minority) == 3)

print("\n[7] FakeProvider behavior")
async def _fake():
    fp = FakeProvider(rules=[("empirical", "YES because data"), ("principled", "NO because duty")],
                      default="abstain")
    r1 = await fp.complete("you are the empirical agent ...")
    r2 = await fp.complete("you are the principled agent ...")
    r3 = await fp.complete("you are the practitioner agent ...")
    return r1, r2, r3, fp

r1, r2, r3, fp = asyncio.run(_fake())
check("fake matches first rule", r1 == "YES because data")
check("fake matches second rule", r2 == "NO because duty")
check("fake falls back to default", r3 == "abstain")
check("fake records all calls", len(fp.calls) == 3)
check("FakeProvider satisfies Provider protocol", isinstance(fp, Provider))

print(f"\n{'='*50}\n  {ok} passed, {fail} failed\n{'='*50}")
sys.exit(1 if fail else 0)
