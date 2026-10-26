"use client";

import { useQuery } from "@tanstack/react-query";
import { format, isValid, parseISO } from "date-fns";
import { ArrowDownWideNarrow, ArrowUpWideNarrow, CalendarClock } from "lucide-react";
import { useParams } from "next/navigation";
import { useMemo, useState } from "react";
import { useReducedMotion } from "framer-motion";
import {
  Area,
  AreaChart,
  ResponsiveContainer,
  Tooltip as RechartsTooltip,
  XAxis,
} from "recharts";

import { EntityBadge } from "@/components/entity/EntityBadge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Card, CardContent, Skeleton } from "@/components/ui/primitives";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ApiError, api } from "@/lib/api";
import { useUi } from "@/lib/store";
import { entityColor } from "@/lib/theme";
import type { Entity, Page } from "@/lib/types";
import { cn, formatDateShort } from "@/lib/utils";

// Attribute keys whose values we treat as dates worth placing on the timeline.
const DATE_KEY_HINTS = [
  "date",
  "not_before",
  "not_after",
  "registered",
  "expires",
  "created_at",
  "breach",
  "updated_at",
  "last_seen",
];

type RangeKey = "all" | "year" | "90d";

interface TimelineEvent {
  id: string;
  date: Date;
  iso: string;
  entity: Entity;
  label: string;
  kind: string;
}

/** Pretty label for an attribute-derived event kind. */
function kindFromKey(key: string): string {
  const k = key.toLowerCase();
  if (k.includes("not_before")) return "Valid from";
  if (k.includes("not_after")) return "Valid until";
  if (k.includes("expires")) return "Expires";
  if (k.includes("registered")) return "Registered";
  if (k.includes("breach")) return "Breach date";
  if (k.includes("created")) return "Created";
  if (k.includes("updated")) return "Updated";
  if (k.includes("last_seen")) return "Last seen";
  return key.replace(/[_-]+/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function toDate(value: unknown): Date | null {
  if (typeof value === "number") {
    // Heuristic: seconds vs ms epoch.
    const ms = value < 1e12 ? value * 1000 : value;
    const d = new Date(ms);
    return isValid(d) ? d : null;
  }
  if (typeof value !== "string") return null;
  const s = value.trim();
  if (!s) return null;
  // Guarded parse: parseISO can produce Invalid Date for non-ISO strings.
  let d = parseISO(s);
  if (isValid(d)) return d;
  d = new Date(s);
  return isValid(d) ? d : null;
}

function buildEvents(entities: Entity[]): TimelineEvent[] {
  const events: TimelineEvent[] = [];
  for (const entity of entities) {
    if (entity.first_seen) {
      const d = toDate(entity.first_seen);
      if (d) {
        events.push({
          id: `${entity.id}:first_seen`,
          date: d,
          iso: d.toISOString(),
          entity,
          label: entity.label || entity.value,
          kind: "First seen",
        });
      }
    }
    const attrs = entity.attributes || {};
    for (const [key, raw] of Object.entries(attrs)) {
      const lk = key.toLowerCase();
      if (!DATE_KEY_HINTS.some((h) => lk.includes(h))) continue;
      const d = toDate(raw);
      if (!d) continue;
      events.push({
        id: `${entity.id}:${key}`,
        date: d,
        iso: d.toISOString(),
        entity,
        label: entity.label || entity.value,
        kind: kindFromKey(key),
      });
    }
  }
  return events;
}

function withinRange(date: Date, range: RangeKey): boolean {
  if (range === "all") return true;
  const now = Date.now();
  const ms = date.getTime();
  if (range === "year") return ms >= now - 365 * 24 * 60 * 60 * 1000;
  return ms >= now - 90 * 24 * 60 * 60 * 1000; // 90d
}

export function TimelineView() {
  const params = useParams<{ caseId: string }>();
  const caseId = params.caseId;
  const reduce = useReducedMotion();

  const [newestFirst, setNewestFirst] = useState(true);
  const [range, setRange] = useState<RangeKey>("all");

  const { data, isLoading, isError, error } = useQuery<Page<Entity>>({
    queryKey: ["entities", caseId, { limit: 200, sort: "recent" }],
    queryFn: () => api.entities.list(caseId, { limit: 200, sort: "recent" }),
  });

  const allEvents = useMemo(() => buildEvents(data?.items ?? []), [data]);

  const events = useMemo(() => {
    const filtered = allEvents.filter((e) => withinRange(e.date, range));
    filtered.sort((a, b) => (newestFirst ? b.date.getTime() - a.date.getTime() : a.date.getTime() - b.date.getTime()));
    return filtered;
  }, [allEvents, range, newestFirst]);

  // Group consecutively by day (events already sorted).
  const groups = useMemo(() => {
    const out: { day: string; label: string; events: TimelineEvent[] }[] = [];
    for (const ev of events) {
      const day = format(ev.date, "yyyy-MM-dd");
      const last = out[out.length - 1];
      if (last && last.day === day) last.events.push(ev);
      else out.push({ day, label: formatDateShort(ev.iso), events: [ev] });
    }
    return out;
  }, [events]);

  // Monthly counts for the mini area chart (always chronological).
  const chartData = useMemo(() => {
    const counts = new Map<string, number>();
    for (const ev of events) {
      const m = format(ev.date, "yyyy-MM");
      counts.set(m, (counts.get(m) ?? 0) + 1);
    }
    return Array.from(counts.entries())
      .sort((a, b) => a[0].localeCompare(b[0]))
      .map(([month, count]) => ({ month, label: format(parseISO(`${month}-01`), "MMM yy"), count }));
  }, [events]);

  if (isLoading) {
    return (
      <div className="space-y-3 p-4">
        <Skeleton className="h-28 w-full" />
        {Array.from({ length: 6 }).map((_, i) => (
          <Skeleton key={i} className="h-12 w-full" />
        ))}
      </div>
    );
  }

  if (isError) {
    return (
      <EmptyState
        icon={CalendarClock}
        title="Couldn’t load timeline"
        description={error instanceof ApiError ? error.message : "Please try again."}
      />
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      {/* Controls */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-4 py-3">
        <div>
          <h1 className="text-sm font-semibold text-text">Timeline</h1>
          <p className="text-xs text-muted">
            {events.length} dated event{events.length === 1 ? "" : "s"} derived from entity facts.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Select value={range} onValueChange={(v) => setRange(v as RangeKey)}>
            <SelectTrigger className="w-[150px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All time</SelectItem>
              <SelectItem value="year">Last year</SelectItem>
              <SelectItem value="90d">Last 90 days</SelectItem>
            </SelectContent>
          </Select>
          <Button variant="secondary" size="sm" onClick={() => setNewestFirst((v) => !v)}>
            {newestFirst ? <ArrowDownWideNarrow size={14} /> : <ArrowUpWideNarrow size={14} />}
            {newestFirst ? "Newest first" : "Oldest first"}
          </Button>
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-auto">
        {events.length === 0 ? (
          <EmptyState
            icon={CalendarClock}
            title="No dated events"
            description="No dates found on entities in this range. Run collectors that yield certificates, registrations, or breaches to populate the timeline."
          />
        ) : (
          <div className="p-4">
            {/* Mini chart of event volume */}
            {chartData.length > 1 && (
              <Card className="mb-5">
                <CardContent className="h-28 p-2">
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={chartData} margin={{ top: 6, right: 8, bottom: 0, left: 8 }}>
                      <defs>
                        <linearGradient id="tlFill" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="0%" stopColor="var(--accent)" stopOpacity={0.4} />
                          <stop offset="100%" stopColor="var(--accent)" stopOpacity={0} />
                        </linearGradient>
                      </defs>
                      <XAxis
                        dataKey="label"
                        tick={{ fill: "var(--muted)", fontSize: 10 }}
                        tickLine={false}
                        axisLine={{ stroke: "var(--border)" }}
                        minTickGap={16}
                      />
                      <RechartsTooltip
                        contentStyle={{
                          background: "var(--raised)",
                          border: "1px solid var(--border)",
                          borderRadius: 8,
                          fontSize: 12,
                          color: "var(--text)",
                        }}
                        labelStyle={{ color: "var(--muted)" }}
                        cursor={{ stroke: "var(--border)" }}
                      />
                      <Area
                        type="monotone"
                        dataKey="count"
                        name="Events"
                        stroke="var(--accent)"
                        strokeWidth={2}
                        fill="url(#tlFill)"
                        isAnimationActive={!reduce}
                      />
                    </AreaChart>
                  </ResponsiveContainer>
                </CardContent>
              </Card>
            )}

            {/* Vertical timeline */}
            <ol className="relative ml-2 border-l border-border pl-6">
              {groups.map((group) => (
                <li key={group.day} className="mb-6 last:mb-0">
                  <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">
                    {group.label}
                  </div>
                  <div className="space-y-1.5">
                    {group.events.map((ev) => (
                      <button
                        key={ev.id}
                        type="button"
                        onClick={() => useUi.getState().setSelectedEntityId(ev.entity.id)}
                        className={cn(
                          "group flex w-full items-center gap-3 rounded-md border border-transparent px-2 py-1.5 text-left text-sm transition-colors",
                          "hover:border-border hover:bg-raised/40",
                        )}
                      >
                        <span
                          className="relative -ml-[31px] flex h-3 w-3 shrink-0 items-center justify-center"
                          aria-hidden
                        >
                          <span
                            className="h-2.5 w-2.5 rounded-full ring-2 ring-bg"
                            style={{ background: entityColor(ev.entity.type) }}
                          />
                        </span>
                        <span className="w-[150px] shrink-0 min-w-0">
                          <EntityBadge type={ev.entity.type} value={ev.entity.value} label={ev.entity.label} />
                        </span>
                        <span className="shrink-0 rounded border border-border bg-raised px-1.5 py-0.5 text-[11px] text-muted">
                          {ev.kind}
                        </span>
                        <span className="ml-auto shrink-0 text-xs text-muted">{format(ev.date, "MMM d, yyyy")}</span>
                      </button>
                    ))}
                  </div>
                </li>
              ))}
            </ol>
          </div>
        )}
      </div>
    </div>
  );
}
