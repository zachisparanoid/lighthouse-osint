"""Server-side report generation (PDF via WeasyPrint, JSON, CSV).

The renderer is intentionally DB-free: every function takes already-loaded plain
Python data (dicts or ORM rows), so it is trivial to unit-test without a database
or a Postgres connection. The reports router (``app.api.v1.reports``) is the only
component that touches the DB; it loads rows, converts them to dicts, and hands
them to :mod:`app.reports.renderer`.

WeasyPrint is imported lazily inside :func:`renderer.render_pdf` so that this
package imports cleanly in environments where the native cairo/pango stack is not
installed (e.g. the local test venv).
"""
