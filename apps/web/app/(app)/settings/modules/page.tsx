"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Boxes, Gauge, KeyRound, ShieldCheck } from "lucide-react";
import Link from "next/link";

import { EntityDot } from "@/components/entity/EntityBadge";
import { EmptyState } from "@/components/ui/empty-state";
import {
  Badge,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Skeleton,
} from "@/components/ui/primitives";
import { ApiError, api } from "@/lib/api";
import { entityLabel } from "@/lib/theme";
import {
  KEY_SERVICE_LABELS,
  type EntityType,
  type KeyService,
  type ModuleInfo,
} from "@/lib/types";

function TypeChips({ types }: { types: string[] }) {
  if (!types || types.length === 0) return <span className="text-xs text-muted">—</span>;
  return (
    <div className="flex flex-wrap gap-1.5">
      {types.map((t) => (
        <span
          key={t}
          className="inline-flex items-center gap-1.5 rounded border border-border bg-bg/40 px-1.5 py-0.5 text-[11px] text-muted"
        >
          <EntityDot type={t as EntityType} size={7} />
          {entityLabel(t)}
        </span>
      ))}
    </div>
  );
}

function ModuleCard({ module: m }: { module: ModuleInfo }) {
  return (
    <Card>
      <CardHeader>
        <div className="min-w-0">
          <CardTitle className="truncate">{m.title}</CardTitle>
          <p className="mt-1 text-xs text-muted">{m.description}</p>
        </div>
        <Badge variant={m.cost === "keyed" ? "warning" : "success"} className="shrink-0 capitalize">
          {m.cost}
        </Badge>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        {m.requires_key && (
          <div className="flex flex-wrap items-center gap-2 rounded-md border border-warning/30 bg-warning/5 px-3 py-2 text-xs">
            <KeyRound size={13} className="shrink-0 text-warning" />
            <span className="text-text">
              Requires a {KEY_SERVICE_LABELS[m.requires_key as KeyService] ?? m.requires_key} key
            </span>
            <Link
              href="/settings/keys"
              className="ml-auto inline-flex items-center gap-1 font-medium text-accent hover:underline"
            >
              Settings → Keys <ArrowRight size={12} />
            </Link>
          </div>
        )}

        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1">
            <p className="text-xs font-medium text-muted">Accepts</p>
            <TypeChips types={m.accepts} />
          </div>
          <div className="space-y-1">
            <p className="text-xs font-medium text-muted">Produces</p>
            <TypeChips types={m.produces} />
          </div>
        </div>

        <div className="flex items-center gap-2 text-xs text-muted">
          <Gauge size={13} className="shrink-0" />
          Rate limit: <span className="mono text-text">{m.rate_limit}</span>
        </div>

        <div className="flex items-start gap-2 rounded-md border border-border bg-bg/40 p-2.5 text-xs text-muted">
          <ShieldCheck size={13} className="mt-0.5 shrink-0 text-success" />
          <span>{m.source_note}</span>
        </div>
      </CardContent>
    </Card>
  );
}

export default function ModulesPage() {
  const { data: modules, isLoading, isError, error } = useQuery<ModuleInfo[]>({
    queryKey: ["modules-global"],
    queryFn: () => api.modules.global(),
  });

  const free = (modules ?? []).filter((m) => m.cost === "free");
  const keyed = (modules ?? []).filter((m) => m.cost === "keyed");

  return (
    <div className="mx-auto max-w-5xl space-y-6 p-6">
      <div className="space-y-1">
        <h1 className="text-lg font-semibold text-text">Module catalog</h1>
        <p className="max-w-3xl text-sm text-muted">
          The collectors Lighthouse can run and the public data sources they draw on. Per-case
          enable/disable and auto-expand depth/budget are configured inside each case workspace
          (the Modules dialog). This page documents the supported modules and their data sources.
        </p>
      </div>

      {isLoading ? (
        <div className="grid gap-4 md:grid-cols-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-52 w-full" />
          ))}
        </div>
      ) : isError ? (
        <EmptyState
          icon={Boxes}
          title="Couldn’t load modules"
          description={error instanceof ApiError ? error.message : "Please try again."}
        />
      ) : !modules || modules.length === 0 ? (
        <EmptyState icon={Boxes} title="No modules registered" description="The collector registry is empty." />
      ) : (
        <div className="space-y-8">
          {free.length > 0 && (
            <section className="space-y-3">
              <div className="flex items-center gap-2">
                <h2 className="text-sm font-semibold text-text">Free sources</h2>
                <Badge variant="success">{free.length}</Badge>
              </div>
              <div className="grid gap-4 md:grid-cols-2">
                {free.map((m) => (
                  <ModuleCard key={m.name} module={m} />
                ))}
              </div>
            </section>
          )}

          {keyed.length > 0 && (
            <section className="space-y-3">
              <div className="flex items-center gap-2">
                <h2 className="text-sm font-semibold text-text">Keyed sources (BYOK)</h2>
                <Badge variant="warning">{keyed.length}</Badge>
              </div>
              <div className="grid gap-4 md:grid-cols-2">
                {keyed.map((m) => (
                  <ModuleCard key={m.name} module={m} />
                ))}
              </div>
            </section>
          )}
        </div>
      )}
    </div>
  );
}
