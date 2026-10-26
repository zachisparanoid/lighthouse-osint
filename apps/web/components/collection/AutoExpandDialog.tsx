"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, GitBranch, Search } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { EntityBadge } from "@/components/entity/EntityBadge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/primitives";
import { Spinner } from "@/components/ui/primitives";
import { api, ApiError } from "@/lib/api";
import { useUi } from "@/lib/store";
import { CONSTANTS, type Entity } from "@/lib/types";
import { cn } from "@/lib/utils";

export function AutoExpandDialog({
  caseId,
  open,
  onOpenChange,
  defaultSeedId,
}: {
  caseId: string;
  open: boolean;
  onOpenChange: (o: boolean) => void;
  defaultSeedId?: string | null;
}) {
  const qc = useQueryClient();
  const selectedEntityId = useUi((s) => s.selectedEntityId);

  const [seedId, setSeedId] = useState<string | null>(null);
  const [depth, setDepth] = useState<number>(CONSTANTS.DEFAULT_AUTOEXPAND_DEPTH);
  const [budget, setBudget] = useState<number>(CONSTANTS.DEFAULT_NODE_BUDGET);
  const [disabled, setDisabled] = useState<Set<string>>(new Set());
  const [pending, setPending] = useState(false);

  // Seed defaults: explicit prop > current selection.
  useEffect(() => {
    if (open) setSeedId(defaultSeedId ?? selectedEntityId ?? null);
  }, [open, defaultSeedId, selectedEntityId]);

  const { data: modules } = useQuery({
    queryKey: ["modules", caseId],
    queryFn: () => api.modules.list(caseId),
    enabled: open,
  });

  // Resolve the chosen seed entity for display.
  const { data: seed } = useQuery({
    queryKey: ["entity", caseId, seedId],
    queryFn: () => api.entities.get(caseId, seedId as string),
    enabled: open && !!seedId,
  });

  const toggleDisabled = (name: string) =>
    setDisabled((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });

  const submit = async () => {
    if (!seedId) {
      toast.error("Pick a seed entity first");
      return;
    }
    setPending(true);
    try {
      await api.jobs.autoexpand(caseId, {
        seed_entity_id: seedId,
        depth,
        budget,
        disabled: Array.from(disabled),
      });
      toast.success("Auto-expand started");
      void qc.invalidateQueries({ queryKey: ["jobs", caseId] });
      onOpenChange(false);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Failed to start auto-expand");
    } finally {
      setPending(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Auto-expand</DialogTitle>
          <DialogDescription>
            Breadth-first follow results from a seed, within a depth and node budget. Cancel any
            time from the Jobs panel.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label>Seed entity</Label>
            {seedId && seed ? (
              <div className="flex items-center justify-between gap-2 rounded-md border border-border bg-bg/40 px-3 py-2">
                <EntityBadge type={seed.type} value={seed.value} label={seed.label} />
                <button
                  className="text-xs text-muted hover:text-text"
                  onClick={() => setSeedId(null)}
                >
                  Change
                </button>
              </div>
            ) : (
              <SeedPicker caseId={caseId} onPick={setSeedId} />
            )}
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="ae-depth" className="flex items-center justify-between">
                <span>Depth</span>
                <span className="mono text-text">{depth}</span>
              </Label>
              <input
                id="ae-depth"
                type="range"
                min={1}
                max={5}
                step={1}
                value={depth}
                onChange={(e) => setDepth(Number(e.target.value))}
                className="w-full accent-accent"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="ae-budget">Node budget</Label>
              <Input
                id="ae-budget"
                type="number"
                min={1}
                max={5000}
                value={budget}
                onChange={(e) => setBudget(Math.max(1, Number(e.target.value) || 0))}
              />
            </div>
          </div>

          <div className="space-y-1.5">
            <Label>Collectors to disable for this run</Label>
            <div className="max-h-44 space-y-1 overflow-auto rounded-md border border-border bg-bg/40 p-1.5">
              {!modules && <p className="px-1.5 py-1 text-xs text-muted">Loading…</p>}
              {modules?.map((m) => {
                const off = disabled.has(m.name);
                return (
                  <button
                    key={m.name}
                    onClick={() => toggleDisabled(m.name)}
                    className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm hover:bg-bg/80"
                  >
                    <span
                      className={cn(
                        "flex h-4 w-4 shrink-0 items-center justify-center rounded border",
                        off ? "border-border bg-transparent" : "border-accent bg-accent",
                      )}
                    >
                      {!off && <Check size={11} className="text-white" />}
                    </span>
                    <span className={cn("flex-1 truncate", off ? "text-muted line-through" : "text-text")}>
                      {m.title}
                    </span>
                    {!m.enabled && <span className="text-[10px] text-muted">disabled</span>}
                  </button>
                );
              })}
            </div>
            <p className="text-[11px] text-muted">Checked collectors will run during expansion.</p>
          </div>
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={() => void submit()} disabled={pending || !seedId}>
            {pending ? <Spinner className="h-4 w-4" /> : <GitBranch size={14} />}
            Start expansion
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function SeedPicker({ caseId, onPick }: { caseId: string; onPick: (id: string) => void }) {
  const [q, setQ] = useState("");
  const [debounced, setDebounced] = useState("");
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const t = setTimeout(() => setDebounced(q.trim()), 200);
    return () => clearTimeout(t);
  }, [q]);

  const { data: results, isFetching } = useQuery({
    queryKey: ["entity-search", caseId, debounced],
    queryFn: () => api.entities.search(caseId, debounced),
    enabled: debounced.length >= 1,
  });

  return (
    <div ref={ref} className="space-y-1.5">
      <div className="flex items-center gap-2 rounded-md border border-border bg-bg/60 px-2.5">
        <Search size={14} className="shrink-0 text-muted" />
        <input
          autoFocus
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search entities to use as seed…"
          className="h-9 w-full bg-transparent text-sm text-text placeholder:text-muted/70 focus:outline-none"
        />
      </div>
      {debounced.length >= 1 && (
        <div className="max-h-40 overflow-auto rounded-md border border-border bg-bg/40 p-1">
          {isFetching && <p className="px-2 py-1.5 text-xs text-muted">Searching…</p>}
          {!isFetching && (!results || results.length === 0) && (
            <p className="px-2 py-1.5 text-xs text-muted">No matches</p>
          )}
          {results?.map((e: Entity) => (
            <button
              key={e.id}
              onClick={() => onPick(e.id)}
              className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left hover:bg-bg/80"
            >
              <EntityBadge type={e.type} value={e.value} label={e.label} />
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
