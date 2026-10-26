"""Phone metadata collector — libphonenumber metadata only (region, carrier, type, tz).

Ethics: this is a PURE, local, offline computation over the bundled libphonenumber
metadata. It performs NO network lookups and never touches private subscriber data —
it only derives what a phone number's structure publicly implies.
"""
from __future__ import annotations

from lighthouse_shared import CollectorCost, EntityType, RelationshipType

from app.collectors.base import CollectionContext, Collector, CollectorResult, EntityRef


def _line_type(parsed) -> str:
    import phonenumbers

    t = phonenumbers.PhoneNumberType
    mapping = {
        t.FIXED_LINE: "FIXED_LINE",
        t.MOBILE: "MOBILE",
        t.FIXED_LINE_OR_MOBILE: "FIXED_LINE_OR_MOBILE",
        t.TOLL_FREE: "TOLL_FREE",
        t.PREMIUM_RATE: "PREMIUM_RATE",
        t.SHARED_COST: "SHARED_COST",
        t.VOIP: "VOIP",
        t.PERSONAL_NUMBER: "PERSONAL_NUMBER",
        t.PAGER: "PAGER",
        t.UAN: "UAN",
        t.VOICEMAIL: "VOICEMAIL",
    }
    return mapping.get(phonenumbers.number_type(parsed), "UNKNOWN")


class PhoneMetaCollector(Collector):
    name = "phone_meta"
    title = "Phone Metadata"
    description = "Derive region, carrier, line type, and timezones from a phone number."
    accepts = {EntityType.PHONE}
    produces = {EntityType.LOCATION, EntityType.ORGANIZATION}
    cost = CollectorCost.FREE
    rate_limit = "120/m"
    cache_ttl = 86400
    base_reliability = 70
    source_note = (
        "libphonenumber metadata: region, carrier, line type, timezones. No lookups of "
        "private subscriber data."
    )

    async def run(self, target: EntityRef, ctx: CollectionContext) -> CollectorResult:
        import phonenumbers
        from phonenumbers import carrier, geocoder
        from phonenumbers import timezone as ph_tz

        result = CollectorResult()
        await ctx.report(20, "Parsing number")

        try:
            parsed = phonenumbers.parse(target.value, None)  # already E.164
        except phonenumbers.NumberParseException:
            result.message = "Unparseable phone number."
            return result

        is_valid = phonenumbers.is_valid_number(parsed)
        region = phonenumbers.region_code_for_number(parsed)
        national = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.NATIONAL)
        ntype = _line_type(parsed)
        geo = geocoder.description_for_number(parsed, "en")
        carrier_name = carrier.name_for_number(parsed, "en")
        tzs = list(ph_tz.time_zones_for_number(parsed))

        await ctx.report(60, "Deriving metadata")

        # Enrich the seed phone node. Library-derived, so license_note instead of source_url.
        result.add_entity(
            EntityType.PHONE,
            target.value,
            attributes={
                "valid": is_valid,
                "region": region,
                "national_format": national,
                "line_type": ntype,
                "timezones": tzs,
            },
            license_note="Derived locally via libphonenumber metadata.",
        )

        if geo:
            loc_value = geo or region
            result.add_entity(
                EntityType.LOCATION,
                loc_value,
                attributes={"country_code": region},
                license_note="libphonenumber",
            )
            result.add_edge(
                (EntityType.PHONE, target.value),
                (EntityType.LOCATION, loc_value),
                RelationshipType.LOCATED_IN,
                source_url=None,
                license_note="libphonenumber",
            )

        if carrier_name:
            result.add_entity(
                EntityType.ORGANIZATION,
                carrier_name,
                attributes={"role": "carrier"},
                license_note="libphonenumber",
            )
            result.add_edge(
                (EntityType.PHONE, target.value),
                (EntityType.ORGANIZATION, carrier_name),
                RelationshipType.REFERENCES,
                source_url=None,
                license_note="libphonenumber",
            )

        await ctx.report(100)
        result.summary = {
            "valid": is_valid,
            "region": region,
            "line_type": ntype,
            "carrier": carrier_name or None,
        }
        return result
