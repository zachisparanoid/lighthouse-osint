"use client";

import { useQuery } from "@tanstack/react-query";
import { Activity, FolderSearch, GitGraph, Plus, Share2 } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import type { LucideIcon } from "lucide-react";

import { CaseCreateDialog } from "@/components/case/CaseCreateDialog";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Badge, Card, Skeleton } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import type { CaseSummary } from "@/lib/types";
import { relativeTime } from "@/lib/utils";

function CountChip({ icon: Icon, value, title }: { icon: LucideIcon; value: number; title: string }) {
  return (
    <span className="inline-flex items-center gap-1 text-xs text-muted" title={title}>
      <Icon size={13} />
      <span className="tabular-nums">{value.toLocaleString()}</span>
    </span>
  );
}

function CaseCard({ c }: { c: CaseSummary }) {
  return (
    <Link
      href={`/cases/${c.id}/graph`}
      className="group flex flex-col rounded-lg border border-border bg-surface p-4 shadow-card transition-colors hover:border-accent/40 hover:bg-raised/30"
    >
      <div className="flex items-start justify-between gap-2">
        <h3 className="truncate text-sm font-semibold text-text">{c.name}</h3>
        <Badge variant={c.status === "active" ? "success" : "default"} className="shrink-0 capitalize">
          {c.status}
        </Badge>
      </div>

      <p className="mt-1.5 line-clamp-2 min-h-[40px] text-sm text-muted">
        {c.description?.trim() || "No description."}
      </p>

      <div className="mt-3 flex items-center gap-3 border-t border-border pt-3">
        <CountChip icon={Share2} value={c.entity_count} title="Entities" />
        <CountChip icon={GitGraph} value={c.edge_count} title="Edges" />
        <CountChip icon={Activity} value={c.running_jobs} title="Running jobs" />
        <span className="ml-auto flex items-center gap-2">
          {c.role && <span className="text-xs capitalize text-muted">{c.role}</span>}
          <span className="text-xs text-muted">{relativeTime(c.updated_at)}</span>
        </span>
      </div>
    </Link>
  );
}

export default function CasesPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [createOpen, setCreateOpen] = useState(false);

  const { data: cases, isLoading } = useQuery({ queryKey: ["cases"], queryFn: api.cases.list });

  // Auto-open the create dialog when arriving via ?new=1, then strip the param.
  useEffect(() => {
    if (searchParams.get("new") === "1") {
      setCreateOpen(true);
      router.replace("/cases");
    }
  }, [searchParams, router]);

  return (
    <div className="mx-auto max-w-6xl px-6 py-8">
      <div className="mb-6 flex items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold text-text">Cases</h1>
          <p className="mt-0.5 text-sm text-muted">All investigations you can access.</p>
        </div>
        <Button onClick={() => setCreateOpen(true)}>
          <Plus size={16} />
          New case
        </Button>
      </div>

      {isLoading ? (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-[136px] w-full rounded-lg" />
          ))}
        </div>
      ) : !cases || cases.length === 0 ? (
        <Card>
          <EmptyState
            icon={FolderSearch}
            title="No cases yet"
            description="Create your first investigation to start mapping entities and relationships."
            action={
              <Button onClick={() => setCreateOpen(true)}>
                <Plus size={16} />
                Create your first case
              </Button>
            }
          />
        </Card>
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {cases.map((c) => (
            <CaseCard key={c.id} c={c} />
          ))}
        </div>
      )}

      <CaseCreateDialog open={createOpen} onOpenChange={setCreateOpen} />
    </div>
  );
}
