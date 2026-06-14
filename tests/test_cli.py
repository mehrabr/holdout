"""Tests for cli.py — thin typer wrapper over the MAGI library.

All tests inject FakeProvider by monkeypatching ``magi.cli._provider_factory``.
No network, no API key, fully deterministic.

The FakeProvider rules match the mandates defined in cli._DEFAULT_AGENTS:
  empirical:    "Reason from data, evidence, and measurable outcomes."
  principled:   "Reason from duty, cost, and the interests of absent stakeholders."
  practitioner: "Reason from pattern, precedent, and tacit experience."

The "[Mandate:" rule catches crux/concurrence calls (those prompts include
"[Mandate:" from _format_rationales); commit prompts do not contain that token.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

import magi.cli as cli_module
from magi.cli import app
from magi.providers.fake import FakeProvider

runner = CliRunner()

_Q = "Should we adopt this technology?"

# 3-0 YES → unanimous → concurrence call → CONVERGENT → MAJORITY
_RULES_UNANIMOUS_YES = [
    ("[Mandate:", "Reasons reinforce each other.\nASSESSMENT: CONVERGENT"),
    ("data, evidence", "Data supports adoption.\nVOTE: YES"),
    ("duty, cost", "Duty supports adoption.\nVOTE: YES"),
    ("pattern, precedent", "Pattern supports adoption.\nVOTE: YES"),
]

# 2-1 with HARD_TO_REVERSE → SPLIT → crux call
_RULES_SPLIT = [
    ("[Mandate:", "Would the migration risk outweigh the performance gain?"),
    ("data, evidence", "Data supports.\nVOTE: YES"),
    ("duty, cost", "Duty supports.\nVOTE: YES"),
    ("pattern, precedent", "Prior cases advise caution.\nVOTE: NO"),
]

# 3-0 YES → unanimous → concurrence call → FRAGILE → FRAGILE_AGREEMENT
_RULES_FRAGILE = [
    ("[Mandate:", "Reasons contradict each other.\nASSESSMENT: FRAGILE"),
    ("data, evidence", "Data supports.\nVOTE: YES"),
    ("duty, cost", "Duty supports.\nVOTE: YES"),
    ("pattern, precedent", "Pattern supports.\nVOTE: YES"),
]


def _factory_unanimous() -> FakeProvider:
    return FakeProvider(rules=_RULES_UNANIMOUS_YES)


def _factory_split() -> FakeProvider:
    return FakeProvider(rules=_RULES_SPLIT)


def _factory_fragile() -> FakeProvider:
    return FakeProvider(rules=_RULES_FRAGILE)


def _invoke_deliberate(
    tmp_db: str,
    monkeypatch: pytest.MonkeyPatch,
    *extra_args: str,
    factory: object = None,
) -> object:
    if factory is None:
        factory = _factory_unanimous
    monkeypatch.setattr(cli_module, "_provider_factory", factory)
    return runner.invoke(
        app, ["deliberate", "--db", tmp_db, _Q, "--tier", "reversible", *extra_args]
    )


def _run_deliberation_and_get_id(tmp_db: str, monkeypatch: pytest.MonkeyPatch) -> str:
    """Run a successful deliberation and return the record id from stdout."""
    result = _invoke_deliberate(tmp_db, monkeypatch)
    assert result.exit_code == 0, result.output
    match = re.search(r"id:\s+(\S+)", result.output)
    assert match, f"no id in output: {result.output!r}"
    return match.group(1)


# ─────────────────────────────────────────────────────────────────────────────
# deliberate command — basic wiring
# ─────────────────────────────────────────────────────────────────────────────


def test_deliberate_exits_zero(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    result = _invoke_deliberate(str(tmp_path / "db"), monkeypatch)
    assert result.exit_code == 0, result.output


def test_deliberate_prints_id_line(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    result = _invoke_deliberate(str(tmp_path / "db"), monkeypatch)
    assert "id:" in result.output


def test_deliberate_prints_outcome_line(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    result = _invoke_deliberate(str(tmp_path / "db"), monkeypatch)
    assert "outcome:" in result.output


def test_deliberate_prints_majority_outcome(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = _invoke_deliberate(str(tmp_path / "db"), monkeypatch)
    assert "majority" in result.output


# ─────────────────────────────────────────────────────────────────────────────
# deliberate command — report file
# ─────────────────────────────────────────────────────────────────────────────


def test_deliberate_writes_report_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = str(tmp_path / "db")
    report = tmp_path / "report.html"
    result = _invoke_deliberate(db, monkeypatch, "--report", str(report))
    assert result.exit_code == 0, result.output
    assert report.exists()


def test_deliberate_report_contains_html(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = str(tmp_path / "db")
    report = tmp_path / "report.html"
    _invoke_deliberate(db, monkeypatch, "--report", str(report))
    assert "<html" in report.read_text().lower()


def test_deliberate_report_mentions_question(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = str(tmp_path / "db")
    report = tmp_path / "report.html"
    _invoke_deliberate(db, monkeypatch, "--report", str(report))
    assert _Q in report.read_text()


def test_deliberate_no_report_flag_writes_no_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = str(tmp_path / "db")
    _invoke_deliberate(db, monkeypatch)
    html_files = list(tmp_path.glob("*.html"))
    assert not html_files


# ─────────────────────────────────────────────────────────────────────────────
# deliberate command — split and fragile paths
# ─────────────────────────────────────────────────────────────────────────────


def test_deliberate_split_prints_crux(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli_module, "_provider_factory", _factory_split)
    result = runner.invoke(
        app,
        ["deliberate", "--db", str(tmp_path / "db"), _Q, "--tier", "hard_to_reverse"],
    )
    assert result.exit_code == 0, result.output
    assert "crux:" in result.output


def test_deliberate_fragile_prints_note(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli_module, "_provider_factory", _factory_fragile)
    result = runner.invoke(
        app,
        ["deliberate", "--db", str(tmp_path / "db"), _Q, "--tier", "reversible"],
    )
    assert result.exit_code == 0, result.output
    assert "fragile" in result.output.lower()


# ─────────────────────────────────────────────────────────────────────────────
# deliberate command — tier validation
# ─────────────────────────────────────────────────────────────────────────────


def test_deliberate_bad_tier_exits_nonzero(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli_module, "_provider_factory", _factory_unanimous)
    result = runner.invoke(
        app, ["deliberate", "--db", str(tmp_path / "db"), _Q, "--tier", "banana"]
    )
    assert result.exit_code != 0


def test_deliberate_bad_tier_error_message(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli_module, "_provider_factory", _factory_unanimous)
    result = runner.invoke(
        app, ["deliberate", "--db", str(tmp_path / "db"), _Q, "--tier", "banana"]
    )
    combined = result.output + (result.stderr if hasattr(result, "stderr") else "")
    assert "reversible" in combined or "hard_to_reverse" in combined


def test_deliberate_missing_tier_exits_nonzero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli_module, "_provider_factory", _factory_unanimous)
    result = runner.invoke(app, ["deliberate", "--db", str(tmp_path / "db"), _Q])
    assert result.exit_code != 0


def test_deliberate_both_tier_values_accepted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both valid tier values produce exit code 0."""
    for tier_str in ("reversible", "hard_to_reverse"):
        monkeypatch.setattr(cli_module, "_provider_factory", _factory_unanimous)
        result = runner.invoke(
            app,
            ["deliberate", "--db", str(tmp_path / f"db_{tier_str}"), _Q, "--tier", tier_str],
        )
        assert result.exit_code == 0, f"tier={tier_str!r} failed: {result.output}"


# ─────────────────────────────────────────────────────────────────────────────
# deliberate command — record written to store
# ─────────────────────────────────────────────────────────────────────────────


def test_deliberate_writes_to_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """After deliberate, the record id printed is retrievable from the store."""
    from magi.store.sqlite import RecordStore

    db_path = tmp_path / "db"
    record_id = _run_deliberation_and_get_id(str(db_path), monkeypatch)

    store = RecordStore(db_path)
    rec = store.get(record_id)
    assert rec is not None
    assert rec.id == record_id
    assert rec.question == _Q


# ─────────────────────────────────────────────────────────────────────────────
# record subcommand
# ─────────────────────────────────────────────────────────────────────────────


def test_record_retrieves_by_id(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = str(tmp_path / "db")
    record_id = _run_deliberation_and_get_id(db, monkeypatch)

    result = runner.invoke(app, ["record", "--db", db, record_id])
    assert result.exit_code == 0, result.output
    assert record_id in result.output


def test_record_output_contains_question(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = str(tmp_path / "db")
    record_id = _run_deliberation_and_get_id(db, monkeypatch)

    result = runner.invoke(app, ["record", "--db", db, record_id])
    assert _Q in result.output


def test_record_output_contains_outcome(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = str(tmp_path / "db")
    record_id = _run_deliberation_and_get_id(db, monkeypatch)

    result = runner.invoke(app, ["record", "--db", db, record_id])
    assert "outcome:" in result.output


def test_record_output_contains_rationales(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = str(tmp_path / "db")
    record_id = _run_deliberation_and_get_id(db, monkeypatch)

    result = runner.invoke(app, ["record", "--db", db, record_id])
    assert "Data supports adoption." in result.output
    assert "Duty supports adoption." in result.output
    assert "Pattern supports adoption." in result.output


def test_record_missing_id_exits_nonzero(tmp_path: Path) -> None:
    db = str(tmp_path / "db")
    result = runner.invoke(app, ["record", "--db", db, "nonexistent-id-000"])
    assert result.exit_code != 0


# ─────────────────────────────────────────────────────────────────────────────
# similar subcommand
# ─────────────────────────────────────────────────────────────────────────────


def test_similar_returns_seeded_record(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = str(tmp_path / "db")
    record_id = _run_deliberation_and_get_id(db, monkeypatch)

    result = runner.invoke(app, ["similar", "--db", db, "adopt this technology"])
    assert result.exit_code == 0
    assert record_id in result.output


def test_similar_empty_store_no_results_message(tmp_path: Path) -> None:
    db = str(tmp_path / "db")
    result = runner.invoke(app, ["similar", "--db", db, "some question"])
    assert result.exit_code == 0
    assert "No similar records found." in result.output


def test_similar_output_contains_outcome_and_question(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = str(tmp_path / "db")
    _run_deliberation_and_get_id(db, monkeypatch)

    result = runner.invoke(app, ["similar", "--db", db, "adopt this technology"])
    assert "majority" in result.output.lower()
    assert _Q in result.output
