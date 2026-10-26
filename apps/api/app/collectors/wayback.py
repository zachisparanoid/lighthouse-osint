"""Wayback Machine collector — Internet Archive CDX API.

Public source: https://web.archive.org (Internet Archive Wayback Machine CDX API).
Surfaces historical snapshots of public pages under a domain/host/URL so an analyst can
see archived URLs and when they were first captured. No authentication.
"""
from __future__ import annotations

import json

from lighthouse_shared import CollectorCost, EntityType, RelationshipType

from app.collectors.base import CollectionContext, Collector, CollectorResult, EntityRef

_CDX = "https://web.archive.org/cdx/search/cdx"
_MAX_SNAPSHOTS = 50


class WaybackCollector(Collector):
    name = "wayback"
    title = "Wayback Machine"
    description = "Surface historical snapshots of public pages from the Internet Archive CDX API."
    accepts = {EntityType.DOMAIN, EntityType.SUBDOMAIN, EntityType.URL}
    produces = {EntityType.URL}
    cost = CollectorCost.FREE
    rate_limit = "20/m"
    base_reliability = 70
    source_note = "Internet Archive Wayback Machine (CDX API) — historical snapshots of public pages."

    async def run(self, target: EntityRef, ctx: CollectionContext) -> CollectorResult:
        value = target.value.strip()
        result = CollectorResult()
        await ctx.report(10, "Querying Wayback CDX")

        resp = await ctx.http.get(
            _CDX,
            params={
                "url": f"{value}/*",
                "output": "json",
                "limit": "50",
                "collapse": "urlkey",
                "fl": "original,timestamp,statuscode,mimetype",
            },
        )
        if resp.status_code == 404:
            return CollectorResult(message=f"No Wayback snapshots for {value}.")
        if resp.status_code == 429:
            retry_after = self._retry_after(resp)
            return CollectorResult.failed("rate limited", retry_after=retry_after)
        if resp.status_code != 200:
            resp.raise_for_status()

        try:
            rows = resp.json()
        except (json.JSONDecodeError, ValueError):
            return CollectorResult(message=f"Wayback returned non-JSON for {value}.")

        # rows[0] is the header; data starts at rows[1]. Empty or header-only -> success empty.
        if not isinstance(rows, list) or len(rows) <= 1:
            return CollectorResult(message=f"No Wayback snapshots for {value}.")

        await ctx.report(50, "Parsing snapshots")

        data_rows = rows[1:][:_MAX_SNAPSHOTS]
        for row in data_rows:
            if not row:
                continue
            original = row[0] if len(row) > 0 else None
            timestamp = row[1] if len(row) > 1 else None
            statuscode = row[2] if len(row) > 2 else None
            mimetype = row[3] if len(row) > 3 else None
            if not original:
                continue
            wayback_url = f"https://web.archive.org/web/{timestamp}/{original}"
            result.add_entity(
                EntityType.URL,
                original,
                attributes={
                    "first_snapshot": timestamp,
                    "statuscode": statuscode,
                    "mimetype": mimetype,
                    "wayback_url": wayback_url,
                },
                source_url=wayback_url,
            )
            result.add_edge(
                (target.type, target.value),
                (EntityType.URL, original),
                RelationshipType.REFERENCES,
                attributes={"archived": True},
                source_url=wayback_url,
            )

        snapshot_count = len(rows) - 1
        result.add_entity(
            target.type,
            value,
            attributes={"snapshot_count": snapshot_count},
            source_url=_CDX,
        )

        result.summary = {"snapshot_count": snapshot_count}
        await ctx.report(100)
        return result

    @staticmethod
    def _retry_after(resp) -> int:
        raw = resp.headers.get("Retry-After")
        try:
            return int(raw)
        except (TypeError, ValueError):
            return 60
