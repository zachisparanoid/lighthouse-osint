"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ChevronDown,
  ListChecks,
  RotateCw,
  X,
} from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/primitives";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { SimpleTooltip } from "@/components/ui/tooltip";
import { api, ApiError } from "@/lib/api";
import { JOB_STATUS_LABELS, type Job, type JobStatus } from "@/lib/types";
import { cn, relativeTime } from "@/lib/utils";

const STATUS_VARIANT: Record<JobStatus, "default" | "accent" | "success" | "danger"> = {
  queued: "accent",
  running: "accent",
  succeeded: "success",
  failed: "danger",
  skipped: "default",
};

/** Normalize a progress value that may be a 0..1 fraction or a 0..100 percentage. */
function pct(progress: number): number {
  const v = progress <= 1 ? progress * 100 : progress;
  return Math.max(2, Math.min(100, Math.round(v)));
}

export function JobQueuePanel({
  caseId,
  open,
  onClose,
}: {
  caseId: string;
  open: boolean;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const [collapsed, setCollapsed] = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: ["jobs", caseId],
    queryFn: () => api.jobs.list(caseId, { limit: 50 }),
    refetchInterval: 4000, // WS is primary; this is a fallback.
    enabled: open,
  });

  const jobs = data?.items ?? [];
  const counts = jobs.reduce<Record<string, number>>((acc, j) => {
    acc[j.status] = (acc[j.status] ?? 0) + 1;
    return acc;
  }, {});
  const active = (counts.running ?? 0) + (counts.queued ?? 0);

  const retry = useMutation({
    mutationFn: (id: string) => api.jobs.retry(caseId, id),
    onSuccess: () => {
      toast.success("Retrying");
      void qc.invalidateQueries({ queryKey: ["jobs", caseId] });
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "Retry failed"),
  });
  const cancel = useMutation({
    mutationFn: (id: string) => api.jobs.cancel(caseId, id),
    onSuccess: () => {
      toast.success("Cancelled");
      void qc.invalidateQueries({ queryKey: ["jobs", caseId] });
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "Cancel failed"),
  });

  if (!open) return null;

  return (
    <div className="fixed bottom-4 right-4 z-40 w-[380px] max-w-[calc(100vw-2rem)] overflow-hidden rounded-lg border border-border bg-surface shadow-glow">
      <div className="flex items-center gap-2 border-b border-border px-3 py-2">
        <ListChecks size={15} className="text-muted" />
        <span className="text-sm font-medium text-text">Jobs</span>
        {active > 0 && (
          <Badge variant="accent" className="ml-1">
            {active} active
          </Badge>
        )}
        <div className="ml-auto flex items-center gap-1">
          <SimpleTooltip label={collapsed ? "Expand" : "Collapse"}>
            <button
              onClick={() => setCollapsed((v) => !v)}
              aria-label={collapsed ? "Expand" : "Collapse"}
              className="rounded p-1 text-muted hover:bg-bg/60 hover:text-text"
            >
              <ChevronDown
                size={16}
                className={cn("transition-transform", collapsed && "rotate-180")}
              />
            </button>
          </SimpleTooltip>
          <SimpleTooltip label="Close">
            <button
              onClick={onClose}
              aria-label="Close jobs panel"
              className="rounded p-1 text-muted hover:bg-bg/60 hover:text-text"
            >
              <X size={15} />
            </button>
          </SimpleTooltip>
        </div>
      </div>

      {!collapsed && (
        <div className="max-h-[60vh] overflow-auto">
          {isLoading && jobs.length === 0 ? (
            <div className="space-y-2 p-3">
              {[0, 1, 2].map((i) => (
                <div key={i} className="skeleton h-12 w-full" />
              ))}
            </div>
          ) : jobs.length === 0 ? (
            <EmptyState
              icon={ListChecks}
              title="No jobs yet"
              description="Run a collector or auto-expand to populate the queue."
              className="py-10"
            />
          ) : (
            <ul className="divide-y divide-border">
              {jobs.map((job) => (
                <JobRow
                  key={job.id}
                  job={job}
                  onRetry={() => retry.mutate(job.id)}
                  onCancel={() => cancel.mutate(job.id)}
                  retrying={retry.isPending && retry.variables === job.id}
                  cancelling={cancel.isPending && cancel.variables === job.id}
                />
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

function JobRow({
  job,
  onRetry,
  onCancel,
  retrying,
  cancelling,
}: {
  job: Job;
  onRetry: () => void;
  onCancel: () => void;
  retrying: boolean;
  cancelling: boolean;
}) {
  const isRunning = job.status === "running";
  const isQueued = job.status === "queued";
  const isAutoExpand = job.collector_name === "auto_expand";
  const time = job.finished_at ?? job.started_at ?? job.created_at;

  return (
    <li className="px-3 py-2.5">
      <div className="flex items-center gap-2">
        <span className="min-w-0 flex-1 truncate text-sm text-text">
          {job.collector_name}
          {job.depth ? <span className="ml-1 text-xs text-muted">· d{job.depth}</span> : null}
        </span>
        <Badge variant={STATUS_VARIANT[job.status]}>{JOB_STATUS_LABELS[job.status]}</Badge>
      </div>

      {isRunning && (
        <div className="mt-1.5 h-1 w-full overflow-hidden rounded-full bg-bg">
          <div
            className="h-full rounded-full bg-accent transition-[width] duration-300"
            style={{ width: `${pct(job.progress)}%` }}
          />
        </div>
      )}

      {job.status === "failed" && job.error && (
        <p className="mt-1 line-clamp-2 text-xs text-danger">{job.error}</p>
      )}

      <div className="mt-1.5 flex items-center justify-between">
        <span className="text-[11px] text-muted">{relativeTime(time)}</span>
        <div className="flex items-center gap-1.5">
          {job.status === "failed" && (
            <Button size="icon-sm" variant="ghost" onClick={onRetry} disabled={retrying} aria-label="Retry">
              <RotateCw size={13} className={cn(retrying && "animate-spin")} />
            </Button>
          )}
          {(isRunning || isQueued) && (
            <Button
              size="sm"
              variant="ghost"
              onClick={onCancel}
              disabled={cancelling}
              className="h-7 px-2 text-xs text-muted hover:text-danger"
            >
              {isAutoExpand ? "Stop" : "Cancel"}
            </Button>
          )}
        </div>
      </div>
    </li>
  );
}
