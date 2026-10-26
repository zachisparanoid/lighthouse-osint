"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { KeyRound, Play } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { EntityBadge } from "@/components/entity/EntityBadge";
import { Badge } from "@/components/ui/primitives";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { EmptyState } from "@/components/ui/empty-state";
import { Spinner } from "@/components/ui/primitives";
import { api, ApiError } from "@/lib/api";
import type { Entity, ModuleInfo } from "@/lib/types";

/**
 * Lists collectors compatible with `entity` (their `accepts` includes the entity type) and
 * enabled. Keyed collectors missing a key are shown disabled with an "Add key" hint.
 */
export function RunModuleDialog({
  caseId,
  entity,
  open,
  onOpenChange,
}: {
  caseId: string;
  entity: Entity;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const qc = useQueryClient();
  const [runningName, setRunningName] = useState<string | null>(null);

  const { data: modules, isLoading } = useQuery({
    queryKey: ["modules", caseId],
    queryFn: () => api.modules.list(caseId),
    enabled: open,
  });

  const compatible = (modules ?? []).filter(
    (m) => m.enabled && m.accepts.includes(entity.type),
  );

  const run = async (m: ModuleInfo) => {
    setRunningName(m.name);
    try {
      await api.jobs.run(caseId, m.name, entity.id);
      toast.success(`Queued ${m.title}`);
      void qc.invalidateQueries({ queryKey: ["jobs", caseId] });
      onOpenChange(false);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Failed to run collector");
    } finally {
      setRunningName(null);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Run a collector</DialogTitle>
          <DialogDescription className="flex items-center gap-1.5">
            <span>Against</span>
            <EntityBadge type={entity.type} value={entity.value} label={entity.label} />
          </DialogDescription>
        </DialogHeader>

        {isLoading ? (
          <div className="flex justify-center py-8">
            <Spinner className="h-5 w-5 text-muted" />
          </div>
        ) : compatible.length === 0 ? (
          <EmptyState
            icon={Play}
            title="No compatible collectors"
            description="No enabled collector accepts this entity type. Enable one in Modules settings."
            className="py-10"
          />
        ) : (
          <div className="max-h-[60vh] space-y-1.5 overflow-auto">
            {compatible.map((m) => {
              const missingKey = !!m.requires_key && !m.key_present;
              return (
                <div
                  key={m.name}
                  className="flex items-start gap-3 rounded-md border border-border bg-bg/40 p-3"
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium text-text">{m.title}</span>
                      <Badge variant={m.cost === "keyed" ? "warning" : "default"}>{m.cost}</Badge>
                    </div>
                    <p className="mt-0.5 line-clamp-2 text-xs text-muted">{m.description}</p>
                    {missingKey && (
                      <p className="mt-1 flex items-center gap-1 text-[11px] text-warning">
                        <KeyRound size={11} /> Add key in Settings → Keys
                      </p>
                    )}
                  </div>
                  <Button
                    size="sm"
                    variant={missingKey ? "secondary" : "default"}
                    disabled={missingKey || runningName === m.name}
                    onClick={() => void run(m)}
                    className="shrink-0"
                  >
                    {runningName === m.name ? <Spinner className="h-3.5 w-3.5" /> : <Play size={13} />}
                    Run
                  </Button>
                </div>
              );
            })}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
