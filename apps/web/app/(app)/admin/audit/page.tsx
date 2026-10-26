"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import {
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Download,
  ScrollText,
  ShieldOff,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import {
  Badge,
  Card,
  CardContent,
  Label,
  Skeleton,
} from "@/components/ui/primitives";
import { ApiError, api } from "@/lib/api";
import type { AuditEntry, Page } from "@/lib/types";
import { cn, formatDate, truncate } from "@/lib/utils";

const LIMIT = 50;

interface AuditFilters {
  action: string;
  q: string;
  case_id: string;
  actor_id: string;
}

const DEFAULT_FILTERS: AuditFilters = { action: "", q: "", case_id: "", actor_id: "" };

function useDebounced<T>(value: T, delay = 350): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(t);
  }, [value, delay]);
  return debounced;
}

function AuditRow({ entry }: { entry: AuditEntry }) {
  const [open, setOpen] = useState(false);
  const hasMeta = entry.meta && Object.keys(entry.meta).length > 0;
  return (
    <>
      <tr
        className={cn("border-b border-border align-top transition-colors hover:bg-raised/30", hasMeta && "cursor-pointer")}
        onClick={() => hasMeta && setOpen((o) => !o)}
      >
        <td className="px-3 py-2">
          {hasMeta ? (
            open ? (
              <ChevronDown size={14} className="text-muted" />
            ) : (
              <ChevronRight size={14} className="text-muted" />
            )
          ) : null}
        </td>
        <td className="whitespace-nowrap px-3 py-2 text-xs text-muted">{formatDate(entry.created_at)}</td>
        <td className="px-3 py-2">
          <Badge variant="outline">{entry.action}</Badge>
        </td>
        <td className="mono px-3 py-2 text-xs text-muted" title={entry.actor_id ?? undefined}>
          {entry.actor_id ? truncate(entry.actor_id, 14) : "—"}
        </td>
        <td className="px-3 py-2 text-xs text-text">
          {entry.target_type ? (
            <span>
              {entry.target_type}
              {entry.target_id && (
                <span className="mono ml-1 text-muted" title={entry.target_id}>
                  {truncate(entry.target_id, 12)}
                </span>
              )}
            </span>
          ) : (
            "—"
          )}
        </td>
        <td className="mono px-3 py-2 text-xs text-muted" title={entry.case_id ?? undefined}>
          {entry.case_id ? truncate(entry.case_id, 12) : "—"}
        </td>
        <td className="mono px-3 py-2 text-xs text-muted">{entry.ip ?? "—"}</td>
      </tr>
      {open && hasMeta && (
        <tr className="border-b border-border bg-bg/40">
          <td colSpan={7} className="px-3 py-2">
            <pre className="mono max-h-72 overflow-auto rounded-md border border-border bg-bg p-3 text-xs text-muted">
              {JSON.stringify(entry.meta, null, 2)}
            </pre>
          </td>
        </tr>
      )}
    </>
  );
}

export default function AuditPage() {
  const [filters, setFilters] = useState<AuditFilters>(DEFAULT_FILTERS);
  const debounced = useDebounced(filters);
  const [offset, setOffset] = useState(0);

  useEffect(() => {
    setOffset(0);
  }, [debounced.action, debounced.q, debounced.case_id, debounced.actor_id]);

  const params = useMemo(
    () => ({
      action: debounced.action || undefined,
      q: debounced.q || undefined,
      case_id: debounced.case_id || undefined,
      actor_id: debounced.actor_id || undefined,
      limit: LIMIT,
      offset,
    }),
    [debounced, offset],
  );

  const { data, isLoading, isError, error } = useQuery<Page<AuditEntry>>({
    queryKey: ["audit", params],
    queryFn: () => api.audit.list(params),
    placeholderData: keepPreviousData,
    retry: false,
  });

  const isForbidden = isError && error instanceof ApiError && error.status === 403;

  // Build the export href with the current filters as query params.
  const exportHref = useMemo(() => {
    const qs = new URLSearchParams();
    for (const [k, v] of Object.entries({
      action: debounced.action,
      q: debounced.q,
      case_id: debounced.case_id,
      actor_id: debounced.actor_id,
    })) {
      if (v) qs.set(k, v);
    }
    const s = qs.toString();
    return s ? `${api.audit.exportUrl}?${s}` : api.audit.exportUrl;
  }, [debounced]);

  const items = data?.items ?? [];
  const total = data?.total ?? 0;
  const rangeStart = total === 0 ? 0 : offset + 1;
  const rangeEnd = Math.min(offset + LIMIT, total);

  if (isForbidden) {
    return (
      <div className="mx-auto max-w-5xl p-6">
        <EmptyState
          icon={ShieldOff}
          title="Administrator access required"
          description="You need an admin role to view the audit trail. Contact your workspace administrator if you believe this is a mistake."
        />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-6xl space-y-5 p-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="space-y-1">
          <h1 className="text-lg font-semibold text-text">Audit trail</h1>
          <p className="text-sm text-muted">
            Immutable, append-only record of privileged actions across the platform.
          </p>
        </div>
        <a
          href={exportHref}
          download
          className="inline-flex h-9 items-center gap-2 rounded-md border border-border bg-raised px-4 text-sm font-medium text-text transition-colors hover:bg-raised/70"
        >
          <Download size={15} /> Export CSV
        </a>
      </div>

      {/* Filters */}
      <Card>
        <CardContent className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <div className="space-y-1">
            <Label htmlFor="f-action">Action</Label>
            <Input
              id="f-action"
              value={filters.action}
              onChange={(e) => setFilters((f) => ({ ...f, action: e.target.value }))}
              placeholder="e.g. case.update"
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="f-q">Search</Label>
            <Input
              id="f-q"
              value={filters.q}
              onChange={(e) => setFilters((f) => ({ ...f, q: e.target.value }))}
              placeholder="Free text…"
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="f-case">Case ID</Label>
            <Input
              id="f-case"
              value={filters.case_id}
              onChange={(e) => setFilters((f) => ({ ...f, case_id: e.target.value }))}
              placeholder="case uuid"
              className="mono"
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="f-actor">Actor ID</Label>
            <Input
              id="f-actor"
              value={filters.actor_id}
              onChange={(e) => setFilters((f) => ({ ...f, actor_id: e.target.value }))}
              placeholder="user uuid"
              className="mono"
            />
          </div>
        </CardContent>
      </Card>

      {/* Table */}
      <Card>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="space-y-2 p-4">
              {Array.from({ length: 10 }).map((_, i) => (
                <Skeleton key={i} className="h-9 w-full" />
              ))}
            </div>
          ) : isError ? (
            <EmptyState
              icon={ScrollText}
              title="Couldn’t load audit log"
              description={error instanceof ApiError ? error.message : "Please try again."}
            />
          ) : items.length === 0 ? (
            <EmptyState
              icon={ScrollText}
              title="No audit entries"
              description="No events match the current filters."
            />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left">
                <thead>
                  <tr className="border-b border-border text-xs font-medium text-muted">
                    <th className="w-8 px-3 py-2" />
                    <th className="px-3 py-2">When</th>
                    <th className="px-3 py-2">Action</th>
                    <th className="px-3 py-2">Actor</th>
                    <th className="px-3 py-2">Target</th>
                    <th className="px-3 py-2">Case</th>
                    <th className="px-3 py-2">IP</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((entry) => (
                    <AuditRow key={entry.id} entry={entry} />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Pagination */}
      <div className="flex items-center justify-between text-xs text-muted">
        <span className="mono tabular-nums">
          {rangeStart}–{rangeEnd} of {total}
        </span>
        <div className="flex items-center gap-2">
          <Button
            size="icon-sm"
            variant="secondary"
            disabled={offset === 0}
            onClick={() => setOffset((o) => Math.max(0, o - LIMIT))}
            aria-label="Previous page"
          >
            <ChevronLeft size={15} />
          </Button>
          <Button
            size="icon-sm"
            variant="secondary"
            disabled={rangeEnd >= total}
            onClick={() => setOffset((o) => o + LIMIT)}
            aria-label="Next page"
          >
            <ChevronRight size={15} />
          </Button>
        </div>
      </div>
    </div>
  );
}
