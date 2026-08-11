"""A buffer that collects a report instead of drawing it.

The PDF has to contain exactly what the screen shows, and the only way to keep
those two in step is to build both from one code path. Every module that draws a
report offers the same helper twice over: draw it, or - when a capture buffer is
open - append it here and draw nothing.

This lives on its own rather than inside `auto_analyst` because `geo_maps` needs
it too, and `geo_maps` must not import `auto_analyst` - the import direction runs
`app` -> `auto_analyst` -> `geo_maps` -> `geo_assets`. Nothing here imports
Streamlit, so it stays usable from any of them.

The buffer is thread-local because Streamlit serves each session on its own
thread: a module-level list would let one user's export collect another user's
charts.
"""

import threading
from contextlib import contextmanager

_state = threading.local()


def sink():
    """The open buffer, or None when the report is being drawn normally."""
    return getattr(_state, "buffer", None)


def active():
    """True while a report is being collected rather than drawn.

    Callers use this to skip the widgets a report would otherwise create - an
    export must not drop selectboxes onto the page, and it has to read its
    settings from defaults instead.
    """
    return sink() is not None


def add(kind, payload):
    """Record one block. True means it was captured, so draw nothing.

    `kind` is one of "heading", "chart", "kpi", "explain" or "takeaway";
    `report_export` knows how to write each one.
    """
    buffer = sink()
    if buffer is None:
        return False
    buffer.append((kind, payload))
    return True


@contextmanager
def capturing():
    """Collect a report's charts and text instead of rendering them."""
    _state.buffer = []
    try:
        yield _state.buffer
    finally:
        _state.buffer = None
