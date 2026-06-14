"""Report rendering: produces a faithful, self-contained HTML artifact from a Record.

The only public symbol is `render`. It interpolates Record fields into the Jinja2
template and adds no synthesis, recommendation, or editorial text. Every string in
the output is traceable to a Position, the crux, or fixed template chrome.
"""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from holdout.types import Outcome, Record, Vote

_TEMPLATE_DIR = Path(__file__).parent

_ENV = Environment(
    loader=FileSystemLoader(str(_TEMPLATE_DIR)),
    autoescape=True,
)


def render(record: Record) -> str:
    """Return a self-contained HTML string faithfully representing *record*.

    Every position is shown at equal visual weight. On a MAJORITY outcome the
    outvoted positions are labelled 'position on record' — never 'error' or
    'rejected'. On a SPLIT the crux and escalation language are shown. On
    FRAGILE_AGREEMENT a concurrence note is shown.
    """
    tally = record.tally

    if record.outcome is Outcome.MAJORITY:
        minority_set: frozenset[object] = frozenset(record.minority)
    else:
        minority_set = frozenset()

    positions_with_labels = [(p, p in minority_set) for p in record.positions]

    template = _ENV.get_template("template.html.j2")
    return template.render(
        record=record,
        yes_count=tally[Vote.YES],
        no_count=tally[Vote.NO],
        positions_with_labels=positions_with_labels,
    )
