"""Tests for cli.py — thin typer wrapper over the MAGI library.

All tests inject FakeProvider by monkeypatching ``holdout.cli._provider_factory``.
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

import holdout.cli as cli_module
from holdout.cli import app
from holdout.providers.fake import FakeProvider

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
    from holdout.store.sqlite import RecordStore

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


# ─────────────────────────────────────────────────────────────────────────────
# deliberate command — --image flag
# ─────────────────────────────────────────────────────────────────────────────


def test_deliberate_image_flag_passes_to_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When --image is passed, the provider receives multimodal content."""
    received_calls: list[object] = []

    class _RecordingProvider:
        async def complete(self, content: object) -> str:
            received_calls.append(content)
            # Concurrence prompt contains "[Mandate:" from _format_rationales.
            text = (
                content
                if isinstance(content, str)
                else " ".join(
                    p.get("text", "")
                    for p in content  # type: ignore[union-attr]
                    if isinstance(p, dict) and p.get("type") == "text"
                )
            )
            if "[Mandate:" in text:
                return "Reasons reinforce each other.\nASSESSMENT: CONVERGENT"
            return "Looks reasonable.\nVOTE: YES"

    monkeypatch.setattr(cli_module, "_provider_factory", lambda: _RecordingProvider())
    monkeypatch.setenv("HOLDOUT_MODEL", "gpt-4o")

    img = tmp_path / "test.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 8)  # minimal PNG-ish bytes

    result = runner.invoke(
        app,
        [
            "deliberate",
            "--db",
            str(tmp_path / "db"),
            _Q,
            "--tier",
            "reversible",
            "--image",
            str(img),
        ],
    )
    assert result.exit_code == 0, result.output
    # Commit calls are multimodal; crux/concurrence calls are text-only.
    multimodal_calls = [c for c in received_calls if isinstance(c, list)]
    assert multimodal_calls, "expected at least one multimodal provider call"
    # Every multimodal call should include an image_url part.
    for call in multimodal_calls:
        assert isinstance(call, list)
        assert any(isinstance(p, dict) and p.get("type") == "image_url" for p in call), (
            "multimodal call is missing an image_url part"
        )


def test_deliberate_image_url_passes_through(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A URL passed with --image appears verbatim in the provider content."""
    received_calls: list[object] = []

    class _RecordingProvider:
        async def complete(self, content: object) -> str:
            received_calls.append(content)
            text = (
                content
                if isinstance(content, str)
                else " ".join(
                    p.get("text", "")
                    for p in content  # type: ignore[union-attr]
                    if isinstance(p, dict) and p.get("type") == "text"
                )
            )
            if "[Mandate:" in text:
                return "Reasons reinforce each other.\nASSESSMENT: CONVERGENT"
            return "Looks reasonable.\nVOTE: YES"

    monkeypatch.setattr(cli_module, "_provider_factory", lambda: _RecordingProvider())
    monkeypatch.setenv("HOLDOUT_MODEL", "gpt-4o")

    url = "https://example.com/chart.png"
    result = runner.invoke(
        app,
        ["deliberate", "--db", str(tmp_path / "db"), _Q, "--tier", "reversible", "--image", url],
    )
    assert result.exit_code == 0, result.output
    multimodal = [c for c in received_calls if isinstance(c, list)]
    assert multimodal, "expected multimodal calls"
    first = multimodal[0]
    assert isinstance(first, list)
    assert any(
        isinstance(p, dict)
        and p.get("type") == "image_url"
        and isinstance(p.get("image_url"), dict)
        and p["image_url"].get("url") == url  # type: ignore[index]
        for p in first
    ), "image URL not found verbatim in provider call"


def test_deliberate_image_report_contains_visual_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The HTML report includes the Visual Context section when --image is used."""

    class _SimpleProvider:
        async def complete(self, content: object) -> str:
            text = (
                content
                if isinstance(content, str)
                else " ".join(
                    p.get("text", "")
                    for p in content  # type: ignore[union-attr]
                    if isinstance(p, dict) and p.get("type") == "text"
                )
            )
            if "[Mandate:" in text:
                return "Reasons reinforce.\nASSESSMENT: CONVERGENT"
            return "Looks fine.\nVOTE: YES"

    monkeypatch.setattr(cli_module, "_provider_factory", lambda: _SimpleProvider())
    monkeypatch.setenv("HOLDOUT_MODEL", "gpt-4o")

    img = tmp_path / "test.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 8)
    report = tmp_path / "report.html"

    result = runner.invoke(
        app,
        [
            "deliberate",
            "--db",
            str(tmp_path / "db"),
            _Q,
            "--tier",
            "reversible",
            "--image",
            str(img),
            "--report",
            str(report),
        ],
    )
    assert result.exit_code == 0, result.output
    assert report.exists()
    html = report.read_text()
    assert "Visual Context" in html
    assert "<img" in html


def test_deliberate_no_image_report_has_no_visual_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without --image the report has no Visual Context section."""
    db = str(tmp_path / "db")
    report = tmp_path / "report.html"
    _invoke_deliberate(db, monkeypatch, "--report", str(report))
    html = report.read_text()
    assert "Visual Context" not in html


# ─────────────────────────────────────────────────────────────────────────────
# deliberate command — vision guardrail
# ─────────────────────────────────────────────────────────────────────────────


def test_deliberate_non_vision_model_with_image_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Passing --image with a text-only model must fail with a non-zero exit code."""
    monkeypatch.setattr(cli_module, "_provider_factory", _factory_unanimous)
    monkeypatch.setenv("HOLDOUT_MODEL", "gpt-3.5-turbo")

    result = runner.invoke(
        app,
        [
            "deliberate",
            "--db",
            str(tmp_path / "db"),
            _Q,
            "--tier",
            "reversible",
            "--image",
            "https://example.com/img.png",
        ],
    )
    assert result.exit_code != 0


def test_deliberate_non_vision_model_with_image_error_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The error message for a non-vision model must mention the model and vision."""
    monkeypatch.setattr(cli_module, "_provider_factory", _factory_unanimous)
    monkeypatch.setenv("HOLDOUT_MODEL", "gpt-3.5-turbo")

    result = runner.invoke(
        app,
        [
            "deliberate",
            "--db",
            str(tmp_path / "db"),
            _Q,
            "--tier",
            "reversible",
            "--image",
            "https://example.com/img.png",
        ],
    )
    combined = result.output + (result.stderr if hasattr(result, "stderr") else "")
    assert "gpt-3.5-turbo" in combined or "vision" in combined.lower()


def test_deliberate_vision_model_with_image_succeeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A known vision-capable model must not be blocked by the guardrail."""
    monkeypatch.setattr(cli_module, "_provider_factory", _factory_unanimous)
    monkeypatch.setenv("HOLDOUT_MODEL", "gpt-4o")

    result = runner.invoke(
        app,
        [
            "deliberate",
            "--db",
            str(tmp_path / "db"),
            _Q,
            "--tier",
            "reversible",
            "--image",
            "https://example.com/img.png",
        ],
    )
    assert result.exit_code == 0, result.output
