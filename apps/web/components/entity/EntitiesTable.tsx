"use client";

import { useVirtualizer } from "@tanstack/react-virtual";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Check,
  ChevronLeft,
  ChevronRight,
  Copy,
  Database,
  Download,
  Pin,
  PinOff,
  Play,
  Search,
  Tag as TagIcon,
  Trash2,
  X,
} from "lucide-react";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import { ConfidenceMeter } from "@/components/entity/ConfidenceMeter";
import { EntityBadge } from "@/components/entity/EntityBadge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Badge, Label, Skeleton, Spinner } from "@/components/ui/primitives";
import { SimpleTooltip, TooltipProvider } from "@/components/ui/tooltip";
import { ApiError, api } from "@/lib/api";
import { useUi } from "@/lib/store";
import { entityLabel } from "@/lib/theme";
import { ENTITY_TYPES, type Entity, type ModuleInfo, type Page } from "@/lib/types";
import { cn, relativeTime, truncate } from "@/lib/utils";

const LIMIT = 50;
const ROW_HEIGHT = 52;

type SortKey = "confidence" | "recent" | "value";

interface Filters {
  q: string;
  type: string; // "" => all
  tag: string;
  min_confidence: string; // keep as string for input control
  conflicting: boolean;
  sort: SortKey;
}

const DEFAULT_FILTERS: Filters = {
  q: "",
  type: "",
  tag: "",
  min_confidence: "",
  conflicting: false,
  sort: "recent",
};

function useDebounced<T>(value: T, delay = 300): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(t);
  }, [value, delay]);
  return debounced;
}

/** Minimal accessible checkbox (native input, themed). */
function Checkbox({
  checked,
  indeterminate,
  onChange,
  "aria-label": ariaLabel,
}: {
  checked: boolean;
  indeterminate?: boolean;
  onChange: (next: boolean) => void;
  "aria-label"?: string;
}) {
  const ref = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (ref.current) ref.current.indeterminate = Boolean(indeterminate) && !checked;
  }, [indeterminate, checked]);
  return (
    <span className="relative inline-flex h-4 w-4 items-center justify-center">
      <input
        ref={ref}
        type="checkbox"
        checked={checked}
        aria-label={ariaLabel}
        onChange={(e) => onChange(e.target.checked)}
        className={cn(
          "peer h-4 w-4 cursor-pointer appearance-none rounded border border-border bg-bg/60",
          "checked:border-accent checked:bg-accent focus-visible:outline-none focus-visible:shadow-focus",
        )}
      />
      <Check
        size={11}
        className="pointer-events-none absolute text-white opacity-0 peer-checked:opacity-100"
        strokeWidth={3}
      />
    </span>
  );
}

function CopyButton({ value }: { value: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      aria-label="Copy value"
      onClick={(e) => {
        e.stopPropagation();
        navigator.clipboard.writeText(value).then(
          () => {
            setCopied(true);
            setTimeout(() => setCopied(false), 1200);
          },
          () => toast.error("Could not copy to clipboard"),
        );
      }}
      className="invisible shrink-0 rounded p-1 text-muted opacity-0 transition-opacity hover:bg-raised hover:text-text group-hover:visible group-hover:opacity-100"
    >
      {copied ? <Check size={12} className="text-success" /> : <Copy size={12} />}
    </button>
  );
}

function csvCell(value: unknown): string {
  const s = value == null ? "" : String(value);
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

function exportCsv(rows: Entity[]) {
  const header = [
    "id",
    "type",
    "value",
    "label",
    "confidence",
    "source_count",
    "tags",
    "conflicting",
    "pinned",
    "first_seen",
    "last_seen",
  ];
  const lines = [header.join(",")];
  for (const e of rows) {
    lines.push(
      [
        e.id,
        e.type,
        e.value,
        e.label,
        e.confidence,
        e.source_count,
        e.tags.join("|"),
        e.conflicting,
        e.pinned,
        e.first_seen ?? "",
        e.last_seen ?? "",
      ]
        .map(csvCell)
        .join(","),
    );
  }
  const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `entities-${new Date().toISOString().slice(0, 10)}.csv`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export function EntitiesTable() {
  const params = useParams<{ caseId: string }>();
  const caseId = params.caseId;
  const qc = useQueryClient();

  const [filters, setFilters] = useState<Filters>(DEFAULT_FILTERS);
  const [qInput, setQInput] = useState("");
  const debouncedQ = useDebounced(qInput, 350);
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [runCollector, setRunCollector] = useState<string>("");

  // Reset paging whenever any filter changes.
  useEffect(() => {
    setOffset(0);
  }, [debouncedQ, filters.type, filters.tag, filters.min_confidence, filters.conflicting, filters.sort]);

  const minConf = filters.min_confidence.trim() === "" ? undefined : Number(filters.min_confidence);

  const queryParams = {
    q: debouncedQ || undefined,
    type: filters.type || undefined,
    tag: filters.tag || undefined,
    min_confidence: Number.isFinite(minConf) ? minConf : undefined,
    conflicting: filters.conflicting || undefined,
    sort: filters.sort,
    limit: LIMIT,
    offset,
  } as const;

  const { data, isLoading, isError, error, isFetching } = useQuery<Page<Entity>>({
    queryKey: ["entities", caseId, queryParams],
    queryFn: () => api.entities.list(caseId, queryParams),
    placeholderData: keepPreviousData,
  });

  // Module catalog for the "Run module" bulk action (collectors that accept).
  const { data: modules } = useQuery<ModuleInfo[]>({
    queryKey: ["modules", caseId],
    queryFn: () => api.modules.list(caseId),
  });

  const items = useMemo(() => data?.items ?? [], [data]);
  const total = data?.total ?? 0;

  // Prune selection to rows that still exist in the current page set is intentional:
  // keep only ids that we can still act on within the loaded data.
  const selectedRows = useMemo(() => items.filter((e) => selected.has(e.id)), [items, selected]);
  const allOnPageSelected = items.length > 0 && items.every((e) => selected.has(e.id));
  const someOnPageSelected = items.some((e) => selected.has(e.id));

  function toggleAll() {
    setSelected((prev) => {
      const next = new Set(prev);
      if (allOnPageSelected) {
        items.forEach((e) => next.delete(e.id));
      } else {
        items.forEach((e) => next.add(e.id));
      }
      return next;
    });
  }

  function toggleOne(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function clearSelection() {
    setSelected(new Set());
  }

  // ---- Virtualizer ----
  const scrollRef = useRef<HTMLDivElement>(null);
  const rowVirtualizer = useVirtualizer({
    count: items.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => ROW_HEIGHT,
    overscan: 12,
  });

  // ---- Mutations ----
  const invalidate = () => qc.invalidateQueries({ queryKey: ["entities", caseId] });

  const bulkMutation = useMutation({
    mutationFn: (body: { entity_ids: string[]; action: string; tag?: string; collector_name?: string }) =>
      api.entities.bulk(caseId, body),
    onSuccess: (res, vars) => {
      invalidate();
      if (vars.action === "run") {
        toast.success(`Queued ${res.jobs_enqueued} job${res.jobs_enqueued === 1 ? "" : "s"}`);
      } else if (vars.action === "delete") {
        toast.success(`Deleted ${res.affected} entit${res.affected === 1 ? "y" : "ies"}`);
        clearSelection();
      } else {
        toast.success(`Updated ${res.affected} entit${res.affected === 1 ? "y" : "ies"}`);
      }
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "Bulk action failed"),
  });

  const ids = () => Array.from(selected);

  function onTag() {
    const tag = window.prompt("Tag to add to selected entities:")?.trim();
    if (!tag) return;
    bulkMutation.mutate({ entity_ids: ids(), action: "tag", tag });
  }
  function onRemoveTag() {
    const tag = window.prompt("Tag to remove from selected entities:")?.trim();
    if (!tag) return;
    bulkMutation.mutate({ entity_ids: ids(), action: "untag", tag });
  }
  function onPin() {
    bulkMutation.mutate({ entity_ids: ids(), action: "pin" });
  }
  function onUnpin() {
    bulkMutation.mutate({ entity_ids: ids(), action: "unpin" });
  }
  function onDelete() {
    if (!window.confirm(`Delete ${selected.size} selected entit${selected.size === 1 ? "y" : "ies"}? This cannot be undone.`))
      return;
    bulkMutation.mutate({ entity_ids: ids(), action: "delete" });
  }
  function onRun() {
    if (!runCollector) {
      toast.error("Choose a collector to run");
      return;
    }
    bulkMutation.mutate({ entity_ids: ids(), action: "run", collector_name: runCollector });
  }

  const totalPages = Math.max(1, Math.ceil(total / LIMIT));
  const currentPage = Math.floor(offset / LIMIT) + 1;
  const rangeStart = total === 0 ? 0 : offset + 1;
  const rangeEnd = Math.min(offset + LIMIT, total);

  return (
    <TooltipProvider delayDuration={300}>
      <div className="flex h-full flex-col">
        {/* Toolbar */}
        <div className="flex flex-wrap items-end gap-3 border-b border-border px-4 py-3">
          <div className="relative min-w-[220px] flex-1">
            <Search size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
            <Input
              value={qInput}
              onChange={(e) => setQInput(e.target.value)}
              placeholder="Search entities…"
              className="pl-9"
              aria-label="Search entities"
            />
            {isFetching && qInput !== debouncedQ && (
              <Spinner className="absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
            )}
          </div>

          <div className="space-y-1">
            <Label>Type</Label>
            <Select
              value={filters.type || "all"}
              onValueChange={(v) => setFilters((f) => ({ ...f, type: v === "all" ? "" : v }))}
            >
              <SelectTrigger className="w-[150px]">
                <SelectValue placeholder="All types" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All types</SelectItem>
                {ENTITY_TYPES.map((t) => (
                  <SelectItem key={t} value={t}>
                    {entityLabel(t)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1">
            <Label>Min conf.</Label>
            <Input
              type="number"
              min={0}
              max={100}
              value={filters.min_confidence}
              onChange={(e) => setFilters((f) => ({ ...f, min_confidence: e.target.value }))}
              placeholder="0"
              className="w-[88px] mono"
              aria-label="Minimum confidence"
            />
          </div>

          <div className="space-y-1">
            <Label>Tag</Label>
            <Input
              value={filters.tag}
              onChange={(e) => setFilters((f) => ({ ...f, tag: e.target.value }))}
              placeholder="tag…"
              className="w-[120px]"
              aria-label="Filter by tag"
            />
          </div>

          <div className="space-y-1">
            <Label>Sort</Label>
            <Select value={filters.sort} onValueChange={(v) => setFilters((f) => ({ ...f, sort: v as SortKey }))}>
              <SelectTrigger className="w-[140px]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="recent">Most recent</SelectItem>
                <SelectItem value="confidence">Confidence</SelectItem>
                <SelectItem value="value">Value (A–Z)</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <label className="flex h-9 cursor-pointer items-center gap-2 rounded-md border border-border bg-bg/40 px-3 text-sm text-muted">
            <Switch
              checked={filters.conflicting}
              onCheckedChange={(v) => setFilters((f) => ({ ...f, conflicting: v }))}
              aria-label="Conflicting only"
            />
            Conflicting only
          </label>
        </div>

        {/* Bulk bar */}
        {selected.size > 0 && (
          <div className="flex flex-wrap items-center gap-2 border-b border-border bg-accent/5 px-4 py-2 text-sm animate-fade-in">
            <span className="font-medium text-text">{selected.size} selected</span>
            <Button size="sm" variant="subtle" onClick={onTag} disabled={bulkMutation.isPending}>
              <TagIcon size={13} /> Tag
            </Button>
            <Button size="sm" variant="subtle" onClick={onRemoveTag} disabled={bulkMutation.isPending}>
              <X size={13} /> Remove tag
            </Button>
            <Button size="sm" variant="subtle" onClick={onPin} disabled={bulkMutation.isPending}>
              <Pin size={13} /> Pin
            </Button>
            <Button size="sm" variant="subtle" onClick={onUnpin} disabled={bulkMutation.isPending}>
              <PinOff size={13} /> Unpin
            </Button>
            <div className="flex items-center gap-1">
              <Select value={runCollector} onValueChange={setRunCollector}>
                <SelectTrigger className="h-8 w-[150px] text-xs">
                  <SelectValue placeholder="Collector…" />
                </SelectTrigger>
                <SelectContent>
                  {(modules ?? []).map((m) => (
                    <SelectItem key={m.name} value={m.name}>
                      {m.title}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Button size="sm" variant="subtle" onClick={onRun} disabled={bulkMutation.isPending || !runCollector}>
                <Play size={13} /> Run
              </Button>
            </div>
            <Button size="sm" variant="subtle" onClick={() => exportCsv(selectedRows)}>
              <Download size={13} /> Export CSV
            </Button>
            <Button size="sm" variant="danger" onClick={onDelete} disabled={bulkMutation.isPending}>
              <Trash2 size={13} /> Delete
            </Button>
            <div className="flex-1" />
            <Button size="sm" variant="ghost" onClick={clearSelection}>
              Clear
            </Button>
          </div>
        )}

        {/* Column header */}
        <div className="flex items-center gap-3 border-b border-border bg-surface/60 px-4 py-2 text-xs font-medium text-muted">
          <span className="flex w-4 shrink-0 items-center">
            <Checkbox
              checked={allOnPageSelected}
              indeterminate={someOnPageSelected}
              onChange={toggleAll}
              aria-label="Select all on page"
            />
          </span>
          <span className="w-[150px] shrink-0">Type</span>
          <span className="min-w-0 flex-1">Value</span>
          <span className="hidden w-[140px] shrink-0 lg:block">Label</span>
          <span className="w-[120px] shrink-0">Confidence</span>
          <span className="hidden w-[60px] shrink-0 text-center md:block">Sources</span>
          <span className="hidden w-[160px] shrink-0 xl:block">Tags</span>
          <span className="w-[88px] shrink-0 text-right">Last seen</span>
        </div>

        {/* Body */}
        <div ref={scrollRef} className="relative min-h-0 flex-1 overflow-auto">
          {isLoading ? (
            <div className="divide-y divide-border">
              {Array.from({ length: 12 }).map((_, i) => (
                <div key={i} className="flex items-center gap-3 px-4 py-3">
                  <Skeleton className="h-4 w-4 rounded" />
                  <Skeleton className="h-4 w-[130px]" />
                  <Skeleton className="h-4 flex-1" />
                  <Skeleton className="h-1.5 w-[110px]" />
                  <Skeleton className="h-4 w-[88px]" />
                </div>
              ))}
            </div>
          ) : isError ? (
            <EmptyState
              icon={Database}
              title="Couldn’t load entities"
              description={error instanceof ApiError ? error.message : "Please try again."}
            />
          ) : items.length === 0 ? (
            <EmptyState
              icon={Database}
              title="No entities yet"
              description="No entities yet — add a seed and run a module."
            />
          ) : (
            <div style={{ height: rowVirtualizer.getTotalSize(), position: "relative", width: "100%" }}>
              {rowVirtualizer.getVirtualItems().map((vItem) => {
                const e = items[vItem.index];
                const isSel = selected.has(e.id);
                return (
                  <div
                    key={e.id}
                    role="row"
                    onClick={() => useUi.getState().setSelectedEntityId(e.id)}
                    className={cn(
                      "group absolute left-0 top-0 flex w-full cursor-pointer items-center gap-3 border-b border-border px-4 text-sm transition-colors hover:bg-raised/40",
                      isSel && "bg-accent/5",
                    )}
                    style={{ height: vItem.size, transform: `translateY(${vItem.start}px)` }}
                  >
                    <span
                      className="flex w-4 shrink-0 items-center"
                      onClick={(ev) => ev.stopPropagation()}
                    >
                      <Checkbox
                        checked={isSel}
                        onChange={() => toggleOne(e.id)}
                        aria-label={`Select ${e.value}`}
                      />
                    </span>
                    <span className="w-[150px] shrink-0 truncate">
                      <EntityBadge type={e.type} value={entityLabel(e.type)} />
                    </span>
                    <span className="flex min-w-0 flex-1 items-center gap-1">
                      <span className="mono truncate text-[13px] text-text" title={e.value}>
                        {truncate(e.value, 64)}
                      </span>
                      <CopyButton value={e.value} />
                      {e.conflicting && (
                        <SimpleTooltip label="Conflicting data across sources">
                          <span className="ml-1">
                            <Badge variant="warning" className="px-1 py-0">!</Badge>
                          </span>
                        </SimpleTooltip>
                      )}
                      {e.pinned && (
                        <Pin size={11} className="ml-1 shrink-0 text-accent" />
                      )}
                    </span>
                    <span className="hidden w-[140px] shrink-0 truncate text-muted lg:block" title={e.label}>
                      {e.label || "—"}
                    </span>
                    <span className="w-[120px] shrink-0">
                      <ConfidenceMeter value={e.confidence} size="sm" />
                    </span>
                    <span className="mono hidden w-[60px] shrink-0 text-center text-muted tabular-nums md:block">
                      {e.source_count}
                    </span>
                    <span className="hidden w-[160px] shrink-0 items-center gap-1 overflow-hidden xl:flex">
                      {e.tags.slice(0, 3).map((t) => (
                        <span
                          key={t}
                          className="truncate rounded border border-border bg-raised px-1.5 py-0.5 text-[10px] text-muted"
                        >
                          {t}
                        </span>
                      ))}
                      {e.tags.length > 3 && (
                        <span className="text-[10px] text-muted">+{e.tags.length - 3}</span>
                      )}
                    </span>
                    <span className="w-[88px] shrink-0 text-right text-xs text-muted">
                      {relativeTime(e.last_seen)}
                    </span>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Pagination */}
        <div className="flex items-center justify-between border-t border-border px-4 py-2 text-xs text-muted">
          <span className="mono tabular-nums">
            {rangeStart}–{rangeEnd} of {total}
          </span>
          <div className="flex items-center gap-2">
            <span className="mono tabular-nums">
              Page {currentPage} / {totalPages}
            </span>
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
    </TooltipProvider>
  );
}
