"""DB-free report renderer.

All public functions accept already-loaded plain Python data — either ``dict``
rows (the shape produced by the router) or ORM objects (attribute access).
Accessors below tolerate both so the renderer can be exercised in unit tests with
nothing more than plain dicts and never imports SQLAlchemy or opens a session.

WeasyPrint is imported lazily inside :func:`render_pdf` only; importing this
module never triggers the native cairo/pango dependency.
"""
from __future__ import annotations

import csv
import io
import json
import os
from datetime import datetime, timezone
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from lighthouse_shared import ENTITY_META, PALETTE, RELATIONSHIP_LABELS

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")

# Confidentiality / ethics line stamped on every report cover.
CONFIDENTIALITY_NOTICE = (
    "CONFIDENTIAL — For authorized recipients only. This report was generated from "
    "open-source intelligence for the stated legal basis. All findings are cited to "
    "their source and retrieval date; verify independently before acting."
)
CITATIONS_NOTE = (
    "Every entity and edge in this export references the open-source provenance "
    "(collector, source URL, retrieval timestamp) it was derived from. Claims "
    "without a cited source must not be relied upon."
)

# How many entities to surface in the "top findings" section.
TOP_FINDINGS_LIMIT = 15


# --------------------------------------------------------------------------- #
# tolerant accessors: work on dicts OR ORM objects
# --------------------------------------------------------------------------- #
def _get(obj: Any, key: str, default: Any = None) -> Any:
    """Read ``key`` from a mapping (``obj[key]``) or an object (``getattr``)."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _enum_value(val: Any) -> Any:
    """Normalize an Enum (EntityType/RelationshipType/...) to its ``.value``."""
    return getattr(val, "value", val)


def _str(val: Any) -> str:
    """str() with None -> ''. Datetimes are isoformatted for stable output."""
    if val is None:
        return ""
    if isinstance(val, datetime):
        return val.isoformat()
    return str(val)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _entity_meta(type_value: Any) -> dict[str, Any]:
    """ENTITY_META row for a type value, with a safe fallback."""
    tv = _enum_value(type_value)
    return ENTITY_META.get(tv, {"value": tv, "label": str(tv).title(), "color": PALETTE["accent"]})


def _rel_label(rel_value: Any) -> str:
    rv = _enum_value(rel_value)
    return RELATIONSHIP_LABELS.get(rv, str(rv).replace("_", " "))


def _prov_list(prov_map: dict[str, list[Any]] | None, key: Any) -> list[dict[str, Any]]:
    """Normalize the provenance rows for one entity/edge id into plain dicts."""
    if not prov_map:
        return []
    rows = prov_map.get(str(key)) or prov_map.get(key) or []
    out: list[dict[str, Any]] = []
    for p in rows:
        out.append(
            {
                "id": _str(_get(p, "id")),
                "collector_name": _get(p, "collector_name") or "unknown",
                "source_url": _get(p, "source_url"),
                "retrieved_at": _str(_get(p, "retrieved_at")),
                "license_note": _get(p, "license_note"),
            }
        )
    return out


def _entity_view(e: Any) -> dict[str, Any]:
    """A normalized, template-friendly dict view of one entity."""
    type_value = _enum_value(_get(e, "type"))
    meta = _entity_meta(type_value)
    return {
        "id": _str(_get(e, "id")),
        "type": type_value,
        "type_label": meta.get("label", str(type_value).title()),
        "type_color": meta.get("color", PALETTE["accent"]),
        "value": _get(e, "value") or "",
        "label": _get(e, "label") or _get(e, "value") or "",
        "confidence": int(_get(e, "confidence", 0) or 0),
        "source_count": int(_get(e, "source_count", 0) or 0),
        "tags": list(_get(e, "tags", []) or []),
        "first_seen": _get(e, "first_seen"),
        "last_seen": _get(e, "last_seen"),
        "conflicting": bool(_get(e, "conflicting", False)),
        "pinned": bool(_get(e, "pinned", False)),
        "attributes": dict(_get(e, "attributes", {}) or {}),
    }


def _edge_view(ed: Any, labels_by_id: dict[str, str]) -> dict[str, Any]:
    """A normalized dict view of one edge, resolving endpoint labels when possible."""
    src = _str(_get(ed, "source_entity_id"))
    tgt = _str(_get(ed, "target_entity_id"))
    rel = _enum_value(_get(ed, "relationship"))
    return {
        "id": _str(_get(ed, "id")),
        "source_entity_id": src,
        "target_entity_id": tgt,
        "source_label": labels_by_id.get(src, src),
        "target_label": labels_by_id.get(tgt, tgt),
        "relationship": rel,
        "relationship_label": _rel_label(rel),
        "confidence": int(_get(ed, "confidence", 0) or 0),
        "attributes": dict(_get(ed, "attributes", {}) or {}),
    }


# --------------------------------------------------------------------------- #
# timeline extraction
# --------------------------------------------------------------------------- #
_DATE_ATTR_KEYS = (
    "breach_date",
    "added_date",
    "not_before",
    "not_after",
    "valid_from",
    "valid_to",
    "registered_date",
    "creation_date",
    "expiry_date",
    "date",
)


def _coerce_dt_str(val: Any) -> str | None:
    """Best-effort -> an ISO-ish date string for timeline sorting/display."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.isoformat()
    s = str(val).strip()
    return s or None


def _timeline_events(entity_views: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collect dated events (first_seen + known date-bearing attributes) sorted ascending."""
    events: list[dict[str, Any]] = []
    for ev in entity_views:
        fs = _coerce_dt_str(ev.get("first_seen"))
        if fs:
            events.append(
                {
                    "when": fs,
                    "kind": "first_seen",
                    "entity_label": ev["label"],
                    "entity_type": ev["type"],
                    "type_label": ev["type_label"],
                    "detail": "First observed",
                }
            )
        attrs = ev.get("attributes") or {}
        for key in _DATE_ATTR_KEYS:
            if key in attrs:
                when = _coerce_dt_str(attrs.get(key))
                if when:
                    events.append(
                        {
                            "when": when,
                            "kind": key,
                            "entity_label": ev["label"],
                            "entity_type": ev["type"],
                            "type_label": ev["type_label"],
                            "detail": key.replace("_", " ").title(),
                        }
                    )
    events.sort(key=lambda x: x["when"])
    return events


# --------------------------------------------------------------------------- #
# context assembly
# --------------------------------------------------------------------------- #
def build_context(
    case: Any,
    entities: list[Any],
    edges: list[Any],
    provenance_by_entity: dict[str, list[Any]] | None,
    provenance_by_edge: dict[str, list[Any]] | None,
    sections: list[str],
    graph_snapshot_png: str | None = None,
) -> dict[str, Any]:
    """Assemble the full Jinja render context, including all computed statistics."""
    entity_views = [_entity_view(e) for e in entities]
    labels_by_id = {ev["id"]: ev["label"] for ev in entity_views}
    edge_views = [_edge_view(ed, labels_by_id) for ed in edges]

    # Attach provenance to each entity / edge view.
    for ev in entity_views:
        ev["provenance"] = _prov_list(provenance_by_entity, ev["id"])
    for edv in edge_views:
        edv["provenance"] = _prov_list(provenance_by_edge, edv["id"])

    # ---- counts by type ----
    counts_by_type: dict[str, int] = {}
    for ev in entity_views:
        counts_by_type[ev["type"]] = counts_by_type.get(ev["type"], 0) + 1
    counts_by_type_view = [
        {
            "type": t,
            "label": _entity_meta(t).get("label", t.title()),
            "color": _entity_meta(t).get("color", PALETTE["accent"]),
            "count": c,
        }
        for t, c in sorted(counts_by_type.items(), key=lambda kv: (-kv[1], kv[0]))
    ]

    # ---- distinct sources across everything ----
    source_keys: set[tuple[str, str]] = set()
    total_citations = 0
    for ev in entity_views:
        for p in ev["provenance"]:
            total_citations += 1
            source_keys.add((p["collector_name"], p["source_url"] or ""))
    for edv in edge_views:
        for p in edv["provenance"]:
            total_citations += 1
            source_keys.add((p["collector_name"], p["source_url"] or ""))

    # ---- inventory sorted by type then confidence desc ----
    inventory = sorted(
        entity_views, key=lambda e: (e["type"], -e["confidence"], e["label"].lower())
    )

    # ---- findings: top by confidence + conflicts called out ----
    top_findings = sorted(
        entity_views, key=lambda e: (-e["confidence"], -e["source_count"])
    )[:TOP_FINDINGS_LIMIT]
    conflicts = [e for e in entity_views if e["conflicting"]]

    # ---- timeline ----
    timeline = _timeline_events(entity_views) if "timeline" in sections else []

    stats = {
        "entity_total": len(entity_views),
        "edge_total": len(edge_views),
        "source_total": len(source_keys),
        "citation_total": total_citations,
        "counts_by_type": counts_by_type_view,
        "conflict_total": len(conflicts),
    }

    return {
        "title": _get(case, "title") or _get(case, "name") or "Intelligence Report",
        "generated_at": _now_iso(),
        "sections": list(sections),
        "case": {
            "id": _str(_get(case, "id")),
            "name": _get(case, "name") or "",
            "slug": _get(case, "slug") or "",
            "description": _get(case, "description") or "",
            "legal_basis": _get(case, "legal_basis") or "",
            "status": _enum_value(_get(case, "status")) or "",
        },
        "stats": stats,
        "entities": entity_views,
        "edges": edge_views,
        "inventory": inventory,
        "top_findings": top_findings,
        "conflicts": conflicts,
        "timeline": timeline,
        "graph_snapshot": graph_snapshot_png,
        "palette": PALETTE,
        "confidentiality_notice": CONFIDENTIALITY_NOTICE,
        "citations_note": CITATIONS_NOTE,
    }


# --------------------------------------------------------------------------- #
# HTML / PDF
# --------------------------------------------------------------------------- #
def _jinja_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(TEMPLATES_DIR),
        autoescape=select_autoescape(enabled_extensions=("html", "j2", "html.j2"), default=True),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def render_html(context: dict[str, Any]) -> str:
    """Render the report template to an HTML string."""
    env = _jinja_env()
    template = env.get_template("report.html.j2")
    return template.render(**context)


def render_pdf(html: str) -> bytes:
    """Render HTML -> PDF bytes via WeasyPrint (imported lazily).

    WeasyPrint pulls in native cairo/pango libraries that are not present in the
    local test venv, so the import is deferred to call time. In Docker the
    dependency is installed and this works transparently.
    """
    import weasyprint  # noqa: PLC0415  (lazy by design)

    return weasyprint.HTML(string=html).write_pdf()


# --------------------------------------------------------------------------- #
# JSON / CSV exports
# --------------------------------------------------------------------------- #
def render_json(
    case: Any,
    entities: list[Any],
    edges: list[Any],
    provenance_by_entity: dict[str, list[Any]] | None = None,
    provenance_by_edge: dict[str, list[Any]] | None = None,
) -> bytes:
    """Structured JSON export. Every entity/edge carries its ``provenance`` list."""
    entity_views = [_entity_view(e) for e in entities]
    labels_by_id = {ev["id"]: ev["label"] for ev in entity_views}
    edge_views = [_edge_view(ed, labels_by_id) for ed in edges]

    for ev in entity_views:
        ev["provenance"] = _prov_list(provenance_by_entity, ev["id"])
        # Datetimes -> strings up front so default=str only ever sees leftovers.
        ev["first_seen"] = _str(ev["first_seen"]) or None
        ev["last_seen"] = _str(ev["last_seen"]) or None
    for edv in edge_views:
        edv["provenance"] = _prov_list(provenance_by_edge, edv["id"])

    doc = {
        "_meta": {
            "generated_at": _now_iso(),
            "schema": "lighthouse.report.v1",
            "_citations": CITATIONS_NOTE,
            "case": {
                "id": _str(_get(case, "id")),
                "name": _get(case, "name") or "",
                "slug": _get(case, "slug") or "",
                "legal_basis": _get(case, "legal_basis") or "",
            },
            "counts": {
                "entities": len(entity_views),
                "edges": len(edge_views),
            },
        },
        "entities": entity_views,
        "edges": edge_views,
    }
    return json.dumps(doc, indent=2, default=str).encode("utf-8")


def render_csv(entities: list[Any], edges: list[Any]) -> bytes:
    """CSV with an entities section followed by an edges section."""
    buf = io.StringIO()
    writer = csv.writer(buf)

    entity_views = [_entity_view(e) for e in entities]
    labels_by_id = {ev["id"]: ev["label"] for ev in entity_views}

    writer.writerow(["# entities"])
    writer.writerow(
        ["id", "type", "value", "label", "confidence", "source_count", "tags", "first_seen", "last_seen"]
    )
    for ev in entity_views:
        writer.writerow(
            [
                ev["id"],
                ev["type"],
                ev["value"],
                ev["label"],
                ev["confidence"],
                ev["source_count"],
                ";".join(ev["tags"]),
                _str(ev["first_seen"]),
                _str(ev["last_seen"]),
            ]
        )

    writer.writerow([])
    writer.writerow(["# edges"])
    writer.writerow(["id", "source_entity_id", "target_entity_id", "relationship", "confidence"])
    for ed in edges:
        edv = _edge_view(ed, labels_by_id)
        writer.writerow(
            [
                edv["id"],
                edv["source_entity_id"],
                edv["target_entity_id"],
                edv["relationship"],
                edv["confidence"],
            ]
        )

    return buf.getvalue().encode("utf-8")


# --------------------------------------------------------------------------- #
# orchestrator
# --------------------------------------------------------------------------- #
# format -> file extensions to produce.
_FORMAT_EXTS: dict[str, tuple[str, ...]] = {
    "pdf": ("pdf",),
    "json": ("json",),
    "csv": ("csv",),
    "bundle": ("pdf", "json", "csv"),
}


def write_artifacts(
    report_id: Any,
    fmt: str,
    case: Any,
    entities: list[Any],
    edges: list[Any],
    provenance_by_entity: dict[str, list[Any]] | None,
    provenance_by_edge: dict[str, list[Any]] | None,
    sections: list[str],
    graph_snapshot_png: str | None,
    out_dir: str,
) -> dict[str, str]:
    """Produce the requested artifact(s) and write them to ``out_dir``.

    Returns a ``{ext: path}`` mapping of what was written. For ``"bundle"`` this
    is pdf+json+csv. If WeasyPrint is unavailable the PDF is skipped (an
    ``ImportError`` is raised only when *exactly* a PDF was requested, so the
    router can surface "pdf unavailable" while still emitting json/csv for a
    bundle).
    """
    os.makedirs(out_dir, exist_ok=True)
    exts = _FORMAT_EXTS.get(fmt, ("pdf",))
    written: dict[str, str] = {}

    # JSON / CSV first — they never depend on native libs, so a bundle still
    # produces something useful even if the PDF step fails.
    if "json" in exts:
        path = os.path.join(out_dir, f"{report_id}.json")
        with open(path, "wb") as fh:
            fh.write(render_json(case, entities, edges, provenance_by_entity, provenance_by_edge))
        written["json"] = path

    if "csv" in exts:
        path = os.path.join(out_dir, f"{report_id}.csv")
        with open(path, "wb") as fh:
            fh.write(render_csv(entities, edges))
        written["csv"] = path

    if "pdf" in exts:
        context = build_context(
            case,
            entities,
            edges,
            provenance_by_entity,
            provenance_by_edge,
            sections,
            graph_snapshot_png,
        )
        html = render_html(context)
        # Always keep the rendered HTML alongside — useful for debugging and as a
        # graceful fallback when the PDF engine is missing.
        html_path = os.path.join(out_dir, f"{report_id}.html")
        with open(html_path, "w", encoding="utf-8") as fh:
            fh.write(html)
        written["html"] = html_path
        try:
            pdf_bytes = render_pdf(html)
        except ImportError:
            # WeasyPrint not installed. For a multi-format bundle we degrade
            # gracefully (json/csv already written); for a pdf-only request we
            # re-raise so the caller can mark the report failed.
            if fmt == "pdf":
                raise
        else:
            path = os.path.join(out_dir, f"{report_id}.pdf")
            with open(path, "wb") as fh:
                fh.write(pdf_bytes)
            written["pdf"] = path

    return written
