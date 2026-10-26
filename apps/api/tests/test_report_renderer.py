"""Renderer unit tests (DB-free, no WeasyPrint).

These exercise the JSON / CSV / HTML paths on small fake dicts. ``render_pdf`` is
deliberately NOT called — WeasyPrint and its native cairo/pango stack are absent
in the local venv. The router/renderer are structured so importing them never
triggers that import.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.reports import renderer


def _fake_case() -> dict:
    return {
        "id": "case-1",
        "name": "Operation Lighthouse",
        "slug": "operation-lighthouse",
        "description": "Mapping infrastructure around example.com.",
        "legal_basis": "Authorized engagement #2026-001; written client consent on file.",
        "status": "active",
    }


def _fake_entities() -> list[dict]:
    return [
        {
            "id": "1",
            "type": "domain",
            "value": "example.com",
            "label": "example.com",
            "confidence": 80,
            "source_count": 2,
            "tags": ["seed"],
            "first_seen": datetime(2026, 1, 2, tzinfo=timezone.utc),
            "last_seen": None,
            "attributes": {"registered_date": "2010-05-01"},
            "conflicting": False,
            "pinned": True,
        },
        {
            "id": "2",
            "type": "ip",
            "value": "93.184.216.34",
            "label": "93.184.216.34",
            "confidence": 65,
            "source_count": 1,
            "tags": [],
            "first_seen": None,
            "last_seen": None,
            "attributes": {},
            "conflicting": True,  # exercises the conflict path
        },
    ]


def _fake_edges() -> list[dict]:
    return [
        {
            "id": "e1",
            "source_entity_id": "1",
            "target_entity_id": "2",
            "relationship": "resolves_to",
            "confidence": 70,
            "attributes": {},
        }
    ]


def _fake_prov_by_entity() -> dict[str, list[dict]]:
    return {
        "1": [
            {
                "id": "p1",
                "collector_name": "dns_records",
                "source_url": "https://dns.example/lookup",
                "retrieved_at": datetime(2026, 1, 2, 10, 0, tzinfo=timezone.utc),
                "license_note": None,
            }
        ],
        "2": [
            {
                "id": "p2",
                "collector_name": "shodan",
                "source_url": "https://api.shodan.io/host/93.184.216.34",
                "retrieved_at": datetime(2026, 1, 2, 11, 0, tzinfo=timezone.utc),
                "license_note": "Shodan ToS",
            }
        ],
    }


def _fake_prov_by_edge() -> dict[str, list[dict]]:
    return {
        "e1": [
            {
                "id": "p3",
                "collector_name": "dns_records",
                "source_url": "https://dns.example/a-record",
                "retrieved_at": datetime(2026, 1, 2, 10, 5, tzinfo=timezone.utc),
                "license_note": None,
            }
        ]
    }


def test_render_csv_contains_entities_and_edges():
    out = renderer.render_csv(_fake_entities(), _fake_edges())
    assert isinstance(out, bytes)
    assert b"example.com" in out
    assert b"93.184.216.34" in out
    # Section markers + an edge relationship are present.
    assert b"# entities" in out
    assert b"# edges" in out
    assert b"resolves_to" in out
    # Header columns are present.
    assert b"source_count" in out


def test_render_json_embeds_provenance_and_meta():
    out = renderer.render_json(
        _fake_case(),
        _fake_entities(),
        _fake_edges(),
        _fake_prov_by_entity(),
        _fake_prov_by_edge(),
    )
    assert isinstance(out, bytes)
    text = out.decode("utf-8")
    assert "example.com" in text
    # _meta + the hard citations requirement.
    assert "_meta" in text
    assert "_citations" in text
    assert "generated_at" in text
    # Every entity carries its provenance source.
    assert "dns_records" in text
    assert "https://api.shodan.io/host/93.184.216.34" in text
    # Edge provenance is embedded too.
    assert "https://dns.example/a-record" in text

    # Valid JSON that round-trips with the expected shape.
    import json

    doc = json.loads(text)
    assert doc["_meta"]["case"]["name"] == "Operation Lighthouse"
    assert len(doc["entities"]) == 2
    assert doc["entities"][0]["provenance"][0]["collector_name"] == "dns_records"


def test_render_html_contains_case_name_and_sections():
    ctx = renderer.build_context(
        case=_fake_case(),
        entities=_fake_entities(),
        edges=_fake_edges(),
        provenance_by_entity=_fake_prov_by_entity(),
        provenance_by_edge=_fake_prov_by_edge(),
        sections=["summary", "inventory", "findings", "graph", "provenance", "timeline"],
        graph_snapshot_png=None,
    )
    html = renderer.render_html(ctx)
    assert isinstance(html, str)
    # Case name appears (cover + footer).
    assert "Operation Lighthouse" in html
    # Legal basis is rendered on the cover (hard requirement).
    assert "Authorized engagement #2026-001" in html
    # Provenance appendix cites a source URL + collector.
    assert "https://dns.example/lookup" in html
    assert "dns_records" in html
    # Conflict entity is called out.
    assert "CONFLICT" in html
    # No graph snapshot -> placeholder note.
    assert "No graph snapshot captured." in html
    # Page-number footer machinery is present in the @page CSS.
    assert "counter(page)" in html


def test_build_context_computes_stats():
    ctx = renderer.build_context(
        case=_fake_case(),
        entities=_fake_entities(),
        edges=_fake_edges(),
        provenance_by_entity=_fake_prov_by_entity(),
        provenance_by_edge=_fake_prov_by_edge(),
        sections=["summary", "timeline"],
        graph_snapshot_png=None,
    )
    stats = ctx["stats"]
    assert stats["entity_total"] == 2
    assert stats["edge_total"] == 1
    assert stats["conflict_total"] == 1
    # Two distinct collectors/source pairs across entities + edge.
    assert stats["source_total"] >= 2
    # Timeline picked up first_seen + a date attribute.
    assert len(ctx["timeline"]) >= 1


def test_render_html_works_with_orm_like_objects():
    """Renderer tolerates attribute-access objects, not just dicts."""

    class Obj:
        def __init__(self, **kw):
            self.__dict__.update(kw)

    case = Obj(
        id="c1",
        name="Object Case",
        slug="object-case",
        description=None,
        legal_basis="basis text",
        status="active",
    )
    ents = [
        Obj(
            id="1",
            type="email",
            value="a@example.com",
            label="a@example.com",
            confidence=90,
            source_count=1,
            tags=[],
            first_seen=None,
            last_seen=None,
            attributes={},
            conflicting=False,
            pinned=False,
        )
    ]
    ctx = renderer.build_context(case, ents, [], {}, {}, ["summary", "inventory", "provenance"], None)
    html = renderer.render_html(ctx)
    assert "Object Case" in html
    assert "a@example.com" in html
    # No provenance on record -> the uncited warning fires.
    assert "UNCITED" in html
