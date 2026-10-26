"use client";

import { useQuery } from "@tanstack/react-query";
import {
  ArrowLeft,
  FileText,
  GitBranch,
  Info,
  ListChecks,
  Network,
  Plus,
  Settings2,
  Table2,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { AddSeedDialog } from "@/components/collection/AddSeedDialog";
import { AutoExpandDialog } from "@/components/collection/AutoExpandDialog";
import { JobQueuePanel } from "@/components/collection/JobQueuePanel";
import { ModuleSettingsDialog } from "@/components/collection/ModuleSettingsDialog";
import { EntityDrawer } from "@/components/entity/EntityDrawer";
import { Badge, Spinner } from "@/components/ui/primitives";
import { Button } from "@/components/ui/button";
import { SimpleTooltip, TooltipProvider } from "@/components/ui/tooltip";
import { api } from "@/lib/api";
import { CASE_STATUS_LABELS } from "@/lib/types";
import { useCaseFeed } from "@/lib/useCaseFeed";
import { cn } from "@/lib/utils";

const TABS = [
  { key: "graph", label: "Graph", icon: Network, shortcut: "g" },
  { key: "entities", label: "Entities", icon: Table2, shortcut: "e" },
  { key: "timeline", label: "Timeline", icon: ListChecks, shortcut: "t" },
  { key: "report", label: "Report", icon: FileText, shortcut: "r" },
] as const;

export default function CaseLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: { caseId: string };
}) {
  const caseId = params.caseId;
  const router = useRouter();
  const pathname = usePathname();

  const [seedOpen, setSeedOpen] = useState(false);
  const [expandOpen, setExpandOpen] = useState(false);
  const [modulesOpen, setModulesOpen] = useState(false);
  const [jobsOpen, setJobsOpen] = useState(false);

  const { connected } = useCaseFeed(caseId);

  const { data: caseData } = useQuery({
    queryKey: ["case", caseId],
    queryFn: () => api.cases.get(caseId),
  });

  const activeTab =
    TABS.find((t) => pathname?.includes(`/${t.key}`))?.key ?? "graph";

  // Keyboard shortcuts (ignored while typing in inputs/textareas/contenteditable).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const el = e.target as HTMLElement | null;
      const tag = el?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || el?.isContentEditable) return;
      const tab = TABS.find((t) => t.shortcut === e.key.toLowerCase());
      if (tab) {
        e.preventDefault();
        router.push(`/cases/${caseId}/${tab.key}`);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [caseId, router]);

  return (
    <TooltipProvider delayDuration={300}>
      <div className="flex h-screen flex-col overflow-hidden">
        {/* Header */}
        <header className="flex shrink-0 items-center gap-3 border-b border-border bg-surface px-4 py-2.5">
          <Link
            href="/dashboard"
            className="flex h-7 w-7 items-center justify-center rounded-md text-muted transition-colors hover:bg-raised hover:text-text"
            aria-label="Back to dashboard"
          >
            <ArrowLeft size={16} />
          </Link>

          <div className="flex min-w-0 items-center gap-2">
            <h1 className="truncate text-sm font-semibold text-text">
              {caseData?.name ?? <span className="inline-block h-4 w-32 skeleton align-middle" />}
            </h1>
            {caseData && (
              <Badge variant={caseData.status === "active" ? "success" : "default"}>
                {CASE_STATUS_LABELS[caseData.status]}
              </Badge>
            )}
            {caseData?.legal_basis && (
              <SimpleTooltip
                label={
                  <span className="block max-w-[220px]">
                    Authorization on file: {caseData.legal_basis}
                  </span>
                }
              >
                <button className="text-muted transition-colors hover:text-text" aria-label="Legal basis">
                  <Info size={14} />
                </button>
              </SimpleTooltip>
            )}
            <SimpleTooltip label={connected ? "Live feed connected" : "Reconnecting…"}>
              <span
                className={cn(
                  "ml-0.5 h-1.5 w-1.5 rounded-full",
                  connected ? "bg-success" : "bg-warning",
                )}
                aria-label={connected ? "connected" : "disconnected"}
              />
            </SimpleTooltip>
          </div>

          {/* Tab nav */}
          <nav className="ml-4 flex items-center gap-1">
            {TABS.map((t) => {
              const Icon = t.icon;
              const active = activeTab === t.key;
              return (
                <Link
                  key={t.key}
                  href={`/cases/${caseId}/${t.key}`}
                  className={cn(
                    "inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
                    active ? "bg-raised text-text" : "text-muted hover:text-text hover:bg-raised/60",
                  )}
                >
                  <Icon size={14} />
                  {t.label}
                </Link>
              );
            })}
          </nav>

          {/* Action bar */}
          <div className="ml-auto flex items-center gap-1.5">
            <Button size="sm" onClick={() => setSeedOpen(true)}>
              <Plus size={14} /> Add seed
            </Button>
            <Button size="sm" variant="secondary" onClick={() => setExpandOpen(true)}>
              <GitBranch size={14} /> Auto-expand
            </Button>
            <SimpleTooltip label="Modules & scheduling">
              <Button size="icon-sm" variant="secondary" onClick={() => setModulesOpen(true)} aria-label="Modules">
                <Settings2 size={15} />
              </Button>
            </SimpleTooltip>
            <SimpleTooltip label="Jobs">
              <Button
                size="icon-sm"
                variant={jobsOpen ? "default" : "secondary"}
                onClick={() => setJobsOpen((v) => !v)}
                aria-label="Toggle jobs panel"
              >
                <ListChecks size={15} />
              </Button>
            </SimpleTooltip>
          </div>
        </header>

        {/* Content */}
        <main className="relative flex-1 overflow-hidden">{children}</main>

        {/* Mounted globally for this workspace */}
        <EntityDrawer caseId={caseId} />
        <JobQueuePanel caseId={caseId} open={jobsOpen} onClose={() => setJobsOpen(false)} />

        {/* Dialogs */}
        <AddSeedDialog caseId={caseId} open={seedOpen} onOpenChange={setSeedOpen} />
        <AutoExpandDialog caseId={caseId} open={expandOpen} onOpenChange={setExpandOpen} />
        <ModuleSettingsDialog caseId={caseId} open={modulesOpen} onOpenChange={setModulesOpen} />
      </div>
    </TooltipProvider>
  );
}
