"""CLI: thin typer wrapper over the MAGI library.

Entry point: ``holdout`` (configured in pyproject.toml).

Commands:
  holdout deliberate "question" --tier reversible|hard_to_reverse [--report FILE] [--db PATH]
  holdout record <id>     [--db PATH]
  holdout similar "q"     [--n N] [--db PATH]

Provider configuration via environment variables:
  MAGI_API_KEY   Bearer token (required for real completions)
  MAGI_BASE_URL  API root (default: https://api.openai.com/v1)
  MAGI_MODEL     Model name (default: gpt-4o)
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable
from pathlib import Path

import typer

from holdout.protocol.engine import Panel
from holdout.providers.base import Provider
from holdout.providers.openai_compat import OpenAICompatProvider
from holdout.report.render import render
from holdout.store.sqlite import RecordStore
from holdout.types import Agent, Tier

app = typer.Typer(no_args_is_help=True)

_DEFAULT_DB = Path.home() / ".magi" / "records.db"

_DEFAULT_AGENTS = [
    Agent(name="empirical", mandate="Reason from data, evidence, and measurable outcomes."),
    Agent(
        name="principled",
        mandate="Reason from duty, cost, and the interests of absent stakeholders.",
    ),
    Agent(name="practitioner", mandate="Reason from pattern, precedent, and tacit experience."),
]


def _make_provider() -> Provider:
    return OpenAICompatProvider(
        base_url=os.environ.get("MAGI_BASE_URL", "https://api.openai.com/v1"),
        api_key=os.environ.get("MAGI_API_KEY", ""),
        model=os.environ.get("MAGI_MODEL", "gpt-4o"),
    )


# Tests replace this to inject FakeProvider without touching the network.
_provider_factory: Callable[[], Provider] = _make_provider


@app.command()
def deliberate(
    question: str = typer.Argument(..., help="The question to deliberate."),
    tier: str = typer.Option(..., help="Reversibility: 'reversible' or 'hard_to_reverse'."),
    report: Path | None = typer.Option(None, help="Write the HTML report to this file."),
    db: Path = typer.Option(_DEFAULT_DB, help="Path to the SQLite record store."),
) -> None:
    """Run a deliberation and write the record to the store."""
    try:
        resolved_tier = Tier(tier)
    except ValueError:
        typer.echo(
            f"Error: --tier must be 'reversible' or 'hard_to_reverse', got {tier!r}.",
            err=True,
        )
        raise typer.Exit(code=1) from None

    db.parent.mkdir(parents=True, exist_ok=True)
    provider = _provider_factory()
    panel = Panel(_DEFAULT_AGENTS, provider=provider)
    rec = asyncio.run(panel.deliberate(question, tier=resolved_tier))

    store = RecordStore(db)
    store.write(rec)

    html = render(rec)
    if report is not None:
        report.write_text(html, encoding="utf-8")
        typer.echo(f"Report written to {report}")

    typer.echo(f"id:      {rec.id}")
    typer.echo(f"outcome: {rec.outcome.value}")
    if rec.crux:
        typer.echo(f"crux:    {rec.crux}")
    if rec.concurrence:
        typer.echo("note:    fragile agreement — positions rest on incompatible reasons")


@app.command()
def record(
    record_id: str = typer.Argument(..., metavar="ID", help="Record id to retrieve."),
    db: Path = typer.Option(_DEFAULT_DB, help="Path to the SQLite record store."),
) -> None:
    """Retrieve and display a past deliberation by id."""
    store = RecordStore(db)
    rec = store.get(record_id)
    if rec is None:
        typer.echo(f"No record found for id: {record_id}", err=True)
        raise typer.Exit(code=1)
    typer.echo(f"id:       {rec.id}")
    typer.echo(f"question: {rec.question}")
    typer.echo(f"tier:     {rec.tier.value}")
    typer.echo(f"outcome:  {rec.outcome.value}")
    if rec.crux:
        typer.echo(f"crux:     {rec.crux}")
    if rec.concurrence:
        typer.echo("note:     fragile agreement")
    for pos in rec.positions:
        typer.echo(f"\n[{pos.agent_name}] ({pos.vote.upper()})\n{pos.rationale}")


@app.command()
def similar(
    question: str = typer.Argument(..., help="Find past deliberations similar to this question."),
    n: int = typer.Option(5, help="Maximum number of results to return."),
    db: Path = typer.Option(_DEFAULT_DB, help="Path to the SQLite record store."),
) -> None:
    """Find past deliberations similar to a question."""
    store = RecordStore(db)
    records = store.similar(question, n=n)
    if not records:
        typer.echo("No similar records found.")
        return
    for rec in records:
        typer.echo(f"{rec.id}  {rec.outcome.value:20s}  {rec.question}")
