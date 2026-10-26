"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { getAccessToken } from "./api";
import { connectCaseFeed } from "./ws";
import type { WsEvent } from "./types";

export interface AutoExpandProgress {
  jobId: string;
  progress: number;
  nodes: number;
  jobs: number;
}

/**
 * Subscribes to a case's live WebSocket feed and keeps TanStack Query caches fresh.
 *
 * - graph_delta / succeeded job_completed -> invalidate graph/entities/jobs (+ toast on new entities)
 * - job_progress / autoexpand_progress    -> invalidate jobs, throttled to ~1s, and expose latest progress
 * - failed / skipped job_completed        -> toast
 */
export function useCaseFeed(caseId: string) {
  const qc = useQueryClient();
  const [connected, setConnected] = useState(false);
  const [autoExpand, setAutoExpand] = useState<AutoExpandProgress | null>(null);
  // Throttle high-frequency jobs invalidations to at most one per second.
  const lastJobsInvalidate = useRef(0);

  useEffect(() => {
    if (!caseId) return;

    const throttledInvalidateJobs = () => {
      const now = Date.now();
      if (now - lastJobsInvalidate.current < 1000) return;
      lastJobsInvalidate.current = now;
      void qc.invalidateQueries({ queryKey: ["jobs", caseId] });
    };

    const onEvent = (e: WsEvent) => {
      switch (e.type) {
        case "graph_delta": {
          void qc.invalidateQueries({ queryKey: ["graph", caseId] });
          void qc.invalidateQueries({ queryKey: ["entities", caseId] });
          void qc.invalidateQueries({ queryKey: ["jobs", caseId] });
          if (e.new_entities.length) {
            toast.success(`${e.collector}: +${e.new_entities.length} entities`);
          }
          break;
        }
        case "job_completed": {
          void qc.invalidateQueries({ queryKey: ["jobs", caseId] });
          if (e.status === "succeeded") {
            void qc.invalidateQueries({ queryKey: ["graph", caseId] });
            void qc.invalidateQueries({ queryKey: ["entities", caseId] });
          } else if (e.status === "failed") {
            toast.error(`${e.collector} failed${e.error ? `: ${e.error}` : ""}`);
          } else if (e.status === "skipped") {
            toast(`${e.collector} skipped`, { description: e.error ?? undefined });
          }
          break;
        }
        case "job_progress": {
          throttledInvalidateJobs();
          break;
        }
        case "autoexpand_progress": {
          setAutoExpand({ jobId: e.job_id, progress: e.progress, nodes: e.nodes, jobs: e.jobs });
          throttledInvalidateJobs();
          break;
        }
        // "connected" is a no-op; onOpen already flips `connected`.
      }
    };

    const dispose = connectCaseFeed(caseId, getAccessToken() || "", {
      onEvent,
      onOpen: () => setConnected(true),
      onClose: () => setConnected(false),
    });

    return () => {
      dispose();
      setConnected(false);
    };
  }, [caseId, qc]);

  return { connected, autoExpand };
}
