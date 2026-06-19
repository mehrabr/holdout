"""Report rendering: produces a faithful, self-contained HTML artifact from a Record.

The only public symbol is `render`. It interpolates Record fields into the Jinja2
template and adds no synthesis, recommendation, or editorial text. Every string in
the output is traceable to a Position, the crux, or fixed template chrome.

When `images` is supplied, each image is embedded in the report so the artifact
shows exactly what was judged. Local file paths are converted to data URIs so the
report remains self-contained; URLs are embedded as-is.
"""

from __future__ import annotations

import base64
import mimetypes
from collections.abc import Sequence
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from holdout.types import Outcome, Record, Vote

_TEMPLATE_DIR = Path(__file__).parent

_ENV = Environment(
    loader=FileSystemLoader(str(_TEMPLATE_DIR)),
    autoescape=True,
)


def _report_image_src(src: str) -> str:
    """Return an <img src> value for the report.

    URL images are used directly. Local files are embedded as data URIs so the
    report is self-contained and viewable without the original file.
    """
    if src.startswith(("http://", "https://")):
        return src
    p = Path(src)
    mime = mimetypes.guess_type(p.name)[0] or "image/png"
    b64 = base64.b64encode(p.read_bytes()).decode()
    return f"data:{mime};base64,{b64}"


def render(record: Record, images: Sequence[str] = ()) -> str:
    """Return a self-contained HTML string faithfully representing *record*.

    Every position is shown at equal visual weight. On a MAJORITY outcome the
    outvoted positions are labelled 'position on record' — never 'error' or
    'rejected'. On a SPLIT the crux and escalation language are shown. On
    FRAGILE_AGREEMENT a concurrence note is shown.

    `images` is an optional list of paths or URLs that were passed as shared
    visual context during the deliberation. Each is embedded in the report header
    so the artifact shows exactly what was judged.
    """
    tally = record.tally

    if record.outcome is Outcome.MAJORITY:
        minority_set: frozenset[object] = frozenset(record.minority)
    else:
        minority_set = frozenset()

    positions_with_labels = [(p, p in minority_set) for p in record.positions]
    image_srcs = [_report_image_src(src) for src in images]

    template = _ENV.get_template("template.html.j2")
    return template.render(
        record=record,
        yes_count=tally[Vote.YES],
        no_count=tally[Vote.NO],
        positions_with_labels=positions_with_labels,
        images=image_srcs,
    )
