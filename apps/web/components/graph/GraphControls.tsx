"use client";

import { useQuery } from "@tanstack/react-query";
import {
  Filter,
  Maximize2,
  RotateCw,
  Save,
  Search,
  X,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import type { Core } from "cytoscape";

import { EntityBadge } from "@/components/entity/EntityBadge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { SimpleTooltip } from "@/components/ui/tooltip";
import { api, ApiError } from "@/lib/api";
import { useUi } from "@/lib/store";
import { entityLabel } from "@/lib/theme";
import { ENTITY_TYPES, type Entity, type EntityType } from "@/lib/types";
import { cn } from "@/lib/utils";

import { runFcose } from "./GraphCanvas";

function IconButton({
  label,
  onClick,
  children,
  disabled,
}: {
  label: string;
  onClick: () => void;
  children: React.ReactNode;
  disabled?: boolean;
}) {
  return (
    <SimpleTooltip label={label}>
      <Button
        variant="secondary"
        size="icon-sm"
        onClick={onClick}
        disabled={disabled}
        aria-label={label}
      >
        {children}
      </Button>
    </SimpleTooltip>
  );
}

export function GraphControls({
  caseId,
  cy,
  className,
}: {
  caseId: string;
  cy: Core | null;
  className?: string;
}) {
  const reduced = useRef(false);
  const { graphFilters, setGraphFilters } = useUi();
  const setFocusEntityId = useUi((s) => s.setFocusEntityId);
  const [saving, setSaving] = useState(false);

  const zoomBy = (factor: number) => {
    if (!cy) return;
    cy.zoom({ level: cy.zoom() * factor, renderedPosition: { x: cy.width() / 2, y: cy.height() / 2 } });
  };

  const saveLayout = async () => {
    if (!cy) return;
    setSaving(true);
    try {
      const positions: Record<string, { x: number; y: number }> = {};
      cy.nodes().forEach((n) => {
        const p = n.position();
        positions[n.id()] = { x: Math.round(p.x), y: Math.round(p.y) };
      });
      await api.cases.saveLayout(caseId, positions);
      toast.success("Layout saved");
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Failed to save layout");
    } finally {
      setSaving(false);
    }
  };

  const activeFilterCount =
    graphFilters.types.length + (graphFilters.minConfidence > 0 ? 1 : 0);

  return (
    <div className={cn("flex flex-col gap-2", className)}>
      <div className="flex items-center gap-1.5 rounded-lg border border-border bg-surface/95 p-1.5 shadow-card backdrop-blur">
        <IconButton label="Zoom in" onClick={() => zoomBy(1.25)} disabled={!cy}>
          <ZoomIn size={15} />
        </IconButton>
        <IconButton label="Zoom out" onClick={() => zoomBy(0.8)} disabled={!cy}>
          <ZoomOut size={15} />
        </IconButton>
        <IconButton label="Fit to screen" onClick={() => cy?.fit(undefined, 60)} disabled={!cy}>
          <Maximize2 size={15} />
        </IconButton>
        <IconButton
          label="Re-run layout"
          onClick={() => cy && runFcose(cy, !reduced.current)}
          disabled={!cy}
        >
          <RotateCw size={15} />
        </IconButton>
        <IconButton label="Save layout" onClick={() => void saveLayout()} disabled={!cy || saving}>
          <Save size={15} />
        </IconButton>

        <div className="mx-0.5 h-5 w-px bg-border" />

        {/* Filter popover (built on DropdownMenu). */}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="secondary" size="icon-sm" aria-label="Filters" className="relative">
              <Filter size={15} />
              {activeFilterCount > 0 && (
                <span className="absolute -right-1 -top-1 flex h-4 min-w-[16px] items-center justify-center rounded-full bg-accent px-1 text-[10px] font-medium text-white">
                  {activeFilterCount}
                </span>
              )}
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" className="w-64 p-2">
            <DropdownMenuLabel className="px-1">Entity types</DropdownMenuLabel>
            <div className="flex flex-wrap gap-1 px-1 pb-1">
              {ENTITY_TYPES.map((t: EntityType) => {
                const active = graphFilters.types.includes(t);
                return (
                  <button
                    key={t}
                    onClick={() =>
                      setGraphFilters({
                        types: active
                          ? graphFilters.types.filter((x) => x !== t)
                          : [...graphFilters.types, t],
                      })
                    }
                    className={cn(
                      "rounded-md border px-2 py-0.5 text-[11px] transition-colors",
                      active
                        ? "border-accent/50 bg-accent/15 text-accent"
                        : "border-border text-muted hover:text-text",
                    )}
                  >
                    {entityLabel(t)}
                  </button>
                );
              })}
            </div>
            <DropdownMenuSeparator />
            <DropdownMenuLabel className="flex items-center justify-between px-1">
              <span>Min confidence</span>
              <span className="mono text-text">{graphFilters.minConfidence}</span>
            </DropdownMenuLabel>
            <div className="px-1 pb-1">
              <input
                type="range"
                min={0}
                max={100}
                step={5}
                value={graphFilters.minConfidence}
                onChange={(e) => setGraphFilters({ minConfidence: Number(e.target.value) })}
                className="w-full accent-accent"
              />
            </div>
            {activeFilterCount > 0 && (
              <button
                onClick={() => setGraphFilters({ types: [], minConfidence: 0 })}
                className="mt-1 w-full rounded-md px-2 py-1 text-left text-xs text-muted hover:bg-bg/80 hover:text-text"
              >
                Clear filters
              </button>
            )}
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      <SearchToFocus caseId={caseId} onPick={(id) => setFocusEntityId(id)} />
    </div>
  );
}

function SearchToFocus({
  caseId,
  onPick,
}: {
  caseId: string;
  onPick: (id: string) => void;
}) {
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const [debounced, setDebounced] = useState("");
  const boxRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const t = setTimeout(() => setDebounced(q.trim()), 200);
    return () => clearTimeout(t);
  }, [q]);

  useEffect(() => {
    const onDown = (e: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false);
    };
    window.addEventListener("mousedown", onDown);
    return () => window.removeEventListener("mousedown", onDown);
  }, []);

  const { data: results, isFetching } = useQuery({
    queryKey: ["entity-search", caseId, debounced],
    queryFn: () => api.entities.search(caseId, debounced),
    enabled: debounced.length >= 2,
  });

  return (
    <div ref={boxRef} className="relative w-64">
      <div className="flex items-center gap-2 rounded-lg border border-border bg-surface/95 px-2.5 shadow-card backdrop-blur">
        <Search size={14} className="shrink-0 text-muted" />
        <input
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          placeholder="Search to focus…"
          className="h-8 w-full bg-transparent text-sm text-text placeholder:text-muted/70 focus:outline-none"
        />
        {q && (
          <button
            onClick={() => {
              setQ("");
              setOpen(false);
            }}
            aria-label="Clear"
            className="text-muted hover:text-text"
          >
            <X size={13} />
          </button>
        )}
      </div>

      {open && debounced.length >= 2 && (
        <div className="absolute left-0 right-0 top-full z-40 mt-1 max-h-72 overflow-auto rounded-lg border border-border bg-raised p-1 shadow-glow">
          {isFetching && <p className="px-2.5 py-2 text-xs text-muted">Searching…</p>}
          {!isFetching && (!results || results.length === 0) && (
            <p className="px-2.5 py-2 text-xs text-muted">No matches</p>
          )}
          {results?.map((e: Entity) => (
            <button
              key={e.id}
              onClick={() => {
                onPick(e.id);
                setOpen(false);
              }}
              className="flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-sm hover:bg-bg/80"
            >
              <EntityBadge type={e.type} value={e.value} label={e.label} />
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
