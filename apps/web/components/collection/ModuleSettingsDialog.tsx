"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { KeyRound, RefreshCw } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { EntityBadge } from "@/components/entity/EntityBadge";
import { Badge } from "@/components/ui/primitives";
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
import { Label, Separator, Spinner } from "@/components/ui/primitives";
import { Switch } from "@/components/ui/switch";
import { api, ApiError } from "@/lib/api";
import type { Entity, ModuleSettings, RescanConfig } from "@/lib/types";

export function ModuleSettingsDialog({
  caseId,
  open,
  onOpenChange,
}: {
  caseId: string;
  open: boolean;
  onOpenChange: (o: boolean) => void;
}) {
  const qc = useQueryClient();
  const [saving, setSaving] = useState(false);

  const { data: modules } = useQuery({
    queryKey: ["modules", caseId],
    queryFn: () => api.modules.list(caseId),
    enabled: open,
  });
  const { data: settings } = useQuery({
    queryKey: ["module-settings", caseId],
    queryFn: () => api.modules.settings(caseId),
    enabled: open,
  });
  const { data: rescan } = useQuery({
    queryKey: ["rescan", caseId],
    queryFn: () => api.cases.getRescan(caseId),
    enabled: open,
  });

  // Local editable copies.
  const [disabled, setDisabled] = useState<Set<string>>(new Set());
  const [depth, setDepth] = useState(2);
  const [budget, setBudget] = useState(250);
  const [rescanCfg, setRescanCfg] = useState<RescanConfig | null>(null);

  useEffect(() => {
    if (settings) {
      setDisabled(new Set(settings.disabled));
      setDepth(settings.autoexpand_depth);
      setBudget(settings.autoexpand_budget);
    }
  }, [settings]);
  useEffect(() => {
    if (rescan) setRescanCfg(rescan);
  }, [rescan]);

  const toggleModule = (name: string, enabled: boolean) =>
    setDisabled((prev) => {
      const next = new Set(prev);
      if (enabled) next.delete(name);
      else next.add(name);
      return next;
    });

  const save = async () => {
    setSaving(true);
    try {
      const body: ModuleSettings = {
        disabled: Array.from(disabled),
        autoexpand_depth: depth,
        autoexpand_budget: budget,
      };
      await api.modules.setSettings(caseId, body);
      if (rescanCfg) await api.cases.setRescan(caseId, rescanCfg);
      toast.success("Settings saved");
      void qc.invalidateQueries({ queryKey: ["modules", caseId] });
      void qc.invalidateQueries({ queryKey: ["module-settings", caseId] });
      void qc.invalidateQueries({ queryKey: ["rescan", caseId] });
      onOpenChange(false);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Failed to save settings");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Modules &amp; scheduling</DialogTitle>
          <DialogDescription>
            Enable or disable collectors for this case and configure automatic re-scans.
          </DialogDescription>
        </DialogHeader>

        <div className="max-h-[65vh] space-y-5 overflow-auto pr-1">
          {/* Collectors */}
          <section className="space-y-1.5">
            <Label>Collectors</Label>
            <div className="space-y-1 rounded-md border border-border bg-bg/40 p-1.5">
              {!modules && <p className="px-1.5 py-1 text-xs text-muted">Loading…</p>}
              {modules?.map((m) => {
                const enabled = !disabled.has(m.name);
                const missingKey = !!m.requires_key && !m.key_present;
                return (
                  <div
                    key={m.name}
                    className="flex items-center gap-3 rounded-md px-2 py-1.5 hover:bg-bg/60"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="truncate text-sm text-text">{m.title}</span>
                        <Badge variant={m.cost === "keyed" ? "warning" : "default"}>{m.cost}</Badge>
                        {missingKey && (
                          <span className="flex items-center gap-1 text-[11px] text-warning">
                            <KeyRound size={11} /> no key
                          </span>
                        )}
                      </div>
                      <p className="truncate text-xs text-muted">{m.source_note}</p>
                    </div>
                    <Switch
                      checked={enabled}
                      onCheckedChange={(v) => toggleModule(m.name, v)}
                      aria-label={`Toggle ${m.title}`}
                    />
                  </div>
                );
              })}
            </div>
          </section>

          {/* Auto-expand defaults */}
          <section className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="ms-depth">Default auto-expand depth</Label>
              <Input
                id="ms-depth"
                type="number"
                min={1}
                max={5}
                value={depth}
                onChange={(e) =>
                  setDepth(Math.min(5, Math.max(1, Number(e.target.value) || 1)))
                }
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="ms-budget">Default node budget</Label>
              <Input
                id="ms-budget"
                type="number"
                min={1}
                max={5000}
                value={budget}
                onChange={(e) => setBudget(Math.max(1, Number(e.target.value) || 1))}
              />
            </div>
          </section>

          <Separator />

          {/* Re-scan schedule */}
          <section className="space-y-3">
            <div className="flex items-center justify-between">
              <Label className="flex items-center gap-1.5 text-sm text-text">
                <RefreshCw size={13} /> Scheduled re-scan
              </Label>
              <Switch
                checked={!!rescanCfg?.enabled}
                onCheckedChange={(v) =>
                  setRescanCfg((c) => ({
                    enabled: v,
                    interval_hours: c?.interval_hours ?? 24,
                    seed_entity_id: c?.seed_entity_id ?? null,
                    depth: c?.depth ?? depth,
                    budget: c?.budget ?? budget,
                  }))
                }
              />
            </div>

            {rescanCfg?.enabled && (
              <div className="space-y-3 rounded-md border border-border bg-bg/40 p-3">
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1.5">
                    <Label htmlFor="rs-interval">Interval (hours)</Label>
                    <Input
                      id="rs-interval"
                      type="number"
                      min={1}
                      value={rescanCfg.interval_hours}
                      onChange={(e) =>
                        setRescanCfg((c) =>
                          c ? { ...c, interval_hours: Math.max(1, Number(e.target.value) || 1) } : c,
                        )
                      }
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="rs-depth">Depth</Label>
                    <Input
                      id="rs-depth"
                      type="number"
                      min={1}
                      max={5}
                      value={rescanCfg.depth}
                      onChange={(e) =>
                        setRescanCfg((c) =>
                          c
                            ? { ...c, depth: Math.min(5, Math.max(1, Number(e.target.value) || 1)) }
                            : c,
                        )
                      }
                    />
                  </div>
                </div>
                <div className="space-y-1.5">
                  <Label>Re-scan seed</Label>
                  <RescanSeedPicker
                    caseId={caseId}
                    seedId={rescanCfg.seed_entity_id}
                    onPick={(id) => setRescanCfg((c) => (c ? { ...c, seed_entity_id: id } : c))}
                  />
                </div>
              </div>
            )}
          </section>
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={() => void save()} disabled={saving}>
            {saving && <Spinner className="h-4 w-4" />}
            Save settings
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function RescanSeedPicker({
  caseId,
  seedId,
  onPick,
}: {
  caseId: string;
  seedId: string | null;
  onPick: (id: string | null) => void;
}) {
  const [q, setQ] = useState("");
  const [debounced, setDebounced] = useState("");
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const t = setTimeout(() => setDebounced(q.trim()), 200);
    return () => clearTimeout(t);
  }, [q]);

  const { data: seed } = useQuery({
    queryKey: ["entity", caseId, seedId],
    queryFn: () => api.entities.get(caseId, seedId as string),
    enabled: !!seedId,
  });
  const { data: results } = useQuery({
    queryKey: ["entity-search", caseId, debounced],
    queryFn: () => api.entities.search(caseId, debounced),
    enabled: debounced.length >= 1,
  });

  if (seedId && seed) {
    return (
      <div className="flex items-center justify-between gap-2 rounded-md border border-border bg-bg/60 px-3 py-2">
        <EntityBadge type={seed.type} value={seed.value} label={seed.label} />
        <button className="text-xs text-muted hover:text-text" onClick={() => onPick(null)}>
          Change
        </button>
      </div>
    );
  }

  return (
    <div ref={ref} className="space-y-1.5">
      <Input
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder="Search a seed entity…"
      />
      {debounced.length >= 1 && (
        <div className="max-h-36 overflow-auto rounded-md border border-border bg-bg/60 p-1">
          {(!results || results.length === 0) && (
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
