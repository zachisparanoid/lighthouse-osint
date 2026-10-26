"use client";

import { useQuery } from "@tanstack/react-query";
import { Activity, FolderSearch, GitGraph, Layers, Plus, Share2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import type { LucideIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Badge, Card, Skeleton } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import type { CaseSummary } from "@/lib/types";
import { relativeTime } from "@/lib/utils";

function StatCard({
  label,
  value,
  icon: Icon,
  loading,
}: {
  label: string;
  value: number;
  icon: LucideIcon;
  loading: boolean;
}) {
  return (
    <Card className="p-4">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-muted">{label}</span>
        <Icon size={16} className="text-muted" />
      </div>
      {loading ? (
        <Skeleton className="mt-2 h-8 w-16" />
      ) : (
        <p className="mt-1 text-2xl font-semibold tabular-nums text-text">{value.toLocaleString()}</p>
      )}
    </Card>
  );
}

function CountChip({ icon: Icon, value, title }: { icon: LucideIcon; value: number; title: string }) {
  return (
    <span className="inline-flex items-center gap-1 text-xs text-muted" title={title}>
      <Icon size={13} />
      <span className="tabular-nums">{value.toLocaleString()}</span>
    </span>
  );
}

function CaseRow({ c }: { c: CaseSummary }) {
  return (
    <Link
      href={`/cases/${c.id}/graph`}
      className="flex items-center gap-4 rounded-md border border-border bg-surface p-3 transition-colors hover:border-accent/40 hover:bg-raised/40"
    >
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="truncate text-sm font-medium text-text">{c.name}</span>
          <Badge variant={c.status === "active" ? "success" : "default"} className="capitalize">
            {c.status}
          </Badge>
        </div>
        <div className="mt-1.5 flex items-center gap-3">
          <CountChip icon={Share2} value={c.entity_count} title="Entities" />
          <CountChip icon={GitGraph} value={c.edge_count} title="Edges" />
          {c.role && (
            <span className="text-xs capitalize text-muted">· {c.role}</span>
          )}
        </div>
      </div>
      <span className="shrink-0 text-xs text-muted">{relativeTime(c.updated_at)}</span>
    </Link>
  );
}

export default function DashboardPage() {
  const router = useRouter();
  const { data: cases, isLoading } = useQuery({ queryKey: ["cases"], queryFn: api.cases.list });

  const totalCases = cases?.length ?? 0;
  const activeCases = cases?.filter((c) => c.status === "active").length ?? 0;
  const totalEntities = cases?.reduce((sum, c) => sum + c.entity_count, 0) ?? 0;
  const runningJobs = cases?.reduce((sum, c) => sum + c.running_jobs, 0) ?? 0;

  const recent = [...(cases ?? [])]
    .sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime())
    .slice(0, 6);

  return (
    <div className="mx-auto max-w-6xl px-6 py-8">
      <div className="mb-6 flex items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold text-text">Dashboard</h1>
          <p className="mt-0.5 text-sm text-muted">Your investigation workspace at a glance.</p>
        </div>
        <Button onClick={() => router.push("/cases?new=1")}>
          <Plus size={16} />
          New investigation
        </Button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard label="Total cases" value={totalCases} icon={FolderSearch} loading={isLoading} />
        <StatCard label="Active cases" value={activeCases} icon={Layers} loading={isLoading} />
        <StatCard label="Total entities" value={totalEntities} icon={Share2} loading={isLoading} />
        <StatCard label="Running jobs" value={runningJobs} icon={Activity} loading={isLoading} />
      </div>

      {/* Recent cases */}
      <section className="mt-8">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-text">Recent cases</h2>
          {totalCases > 0 && (
            <Link href="/cases" className="text-xs font-medium text-accent hover:underline">
              View all
            </Link>
          )}
        </div>

        {isLoading ? (
          <div className="space-y-2">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-16 w-full rounded-md" />
            ))}
          </div>
        ) : recent.length === 0 ? (
          <Card>
            <EmptyState
              icon={FolderSearch}
              title="No cases yet"
              description="Create your first investigation to start mapping entities and relationships."
              action={
                <Button onClick={() => router.push("/cases?new=1")}>
                  <Plus size={16} />
                  Create your first case
                </Button>
              }
            />
          </Card>
        ) : (
          <div className="space-y-2">
            {recent.map((c) => (
              <CaseRow key={c.id} c={c} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
