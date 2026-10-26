"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  Check,
  Download,
  FileText,
  Info,
  Loader2,
} from "lucide-react";
import { useParams } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Badge,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Label,
  Separator,
  Skeleton,
  Spinner,
} from "@/components/ui/primitives";
import { ApiError, api } from "@/lib/api";
import { useUi } from "@/lib/store";
import type { Entity, Page, Report } from "@/lib/types";
import { cn, relativeTime } from "@/lib/utils";

type SectionId = "summary" | "inventory" | "findings" | "graph" | "provenance" | "timeline";

const SECTIONS: { id: SectionId; label: string; hint: string }[] = [
  { id: "summary", label: "Summary", hint: "Case overview and scope" },
  { id: "inventory", label: "Entity inventory", hint: "Full list of discovered entities" },
  { id: "findings", label: "Key findings", hint: "Conflicts, high-confidence pivots" },
  { id: "graph", label: "Graph snapshot", hint: "Relationship map image" },
  { id: "provenance", label: "Provenance appendix", hint: "Every source URL + retrieval date" },
  { id: "timeline", label: "Timeline", hint: "Chronological dated facts" },
];

type FormatId = "pdf" | "json" | "csv" | "bundle";

const FORMATS: { id: FormatId; label: string }[] = [
  { id: "pdf", label: "PDF" },
  { id: "json", label: "JSON" },
  { id: "csv", label: "CSV" },
  { id: "bundle", label: "Bundle (all)" },
];

function statusVariant(status: string): "success" | "warning" | "danger" | "default" {
  if (status === "ready") return "success";
  if (status === "failed") return "danger";
  if (status === "pending") return "warning";
  return "default";
}

export function ReportBuilder() {
  const params = useParams<{ caseId: string }>();
  const caseId = params.caseId;
  const qc = useQueryClient();

  const [title, setTitle] = useState("Investigation report");
  const [sections, setSections] = useState<Record<SectionId, boolean>>({
    summary: true,
    inventory: true,
    findings: true,
    graph: false,
    provenance: true,
    timeline: true,
  });
  const [format, setFormat] = useState<FormatId>("pdf");
  const [minConfidence, setMinConfidence] = useState<string>("0");

  // Quick "head" request to summarize what the report will include.
  const { data: head, isLoading: headLoading } = useQuery<Page<Entity>>({
    queryKey: ["entities", caseId, { limit: 1, report_head: true }],
    queryFn: () => api.entities.list(caseId, { limit: 1 }),
  });

  const { data: reports, isLoading: reportsLoading } = useQuery<Report[]>({
    queryKey: ["reports", caseId],
    queryFn: () => api.reports.list(caseId),
    refetchInterval: (query) => {
      const list = query.state.data as Report[] | undefined;
      // Poll while anything is still generating.
      return list?.some((r) => r.status === "pending") ? 4000 : false;
    },
  });

  const selectedSections = SECTIONS.filter((s) => sections[s.id]).map((s) => s.id);

  const createMutation = useMutation({
    mutationFn: () =>
      api.reports.create(caseId, {
        title: title.trim() || "Investigation report",
        sections: selectedSections,
        format,
        min_confidence: Number(minConfidence) || 0,
        // Live cytoscape canvas is not capturable from here; server captures if available.
        graph_snapshot_png: sections.graph ? useUi.getState().graphSnapshot : null,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["reports", caseId] });
      toast.success("Report queued — it will appear below when ready.");
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "Could not generate report"),
  });

  function toggleSection(id: SectionId) {
    setSections((s) => ({ ...s, [id]: !s[id] }));
  }

  const totalEntities = head?.total ?? 0;

  return (
    <div className="grid gap-5 p-4 lg:grid-cols-[minmax(0,1fr)_320px]">
      {/* Left: builder + history */}
      <div className="space-y-5">
        <Card>
          <CardHeader>
            <CardTitle>Build a report</CardTitle>
          </CardHeader>
          <CardContent className="space-y-5">
            <div className="space-y-1.5">
              <Label htmlFor="report-title">Title</Label>
              <Input
                id="report-title"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="Investigation report"
              />
            </div>

            <div className="space-y-2">
              <Label>Sections</Label>
              <div className="grid gap-2 sm:grid-cols-2">
                {SECTIONS.map((s) => (
                  <label
                    key={s.id}
                    className={cn(
                      "flex cursor-pointer items-start gap-2.5 rounded-md border p-2.5 transition-colors",
                      sections[s.id] ? "border-accent/40 bg-accent/5" : "border-border hover:bg-raised/40",
                    )}
                  >
                    <span
                      className={cn(
                        "mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded border",
                        sections[s.id] ? "border-accent bg-accent text-white" : "border-border",
                      )}
                    >
                      {sections[s.id] && <Check size={11} strokeWidth={3} />}
                    </span>
                    <input
                      type="checkbox"
                      className="sr-only"
                      checked={sections[s.id]}
                      onChange={() => toggleSection(s.id)}
                    />
                    <span className="min-w-0">
                      <span className="block text-sm text-text">
                        {s.id === "graph" ? "Include graph snapshot" : s.label}
                      </span>
                      <span className="block text-xs text-muted">{s.hint}</span>
                    </span>
                  </label>
                ))}
              </div>
              {sections.graph && (
                <p className="text-xs text-muted">
                  Graph snapshot is captured server-side if available.
                </p>
              )}
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label>Format</Label>
                <Select value={format} onValueChange={(v) => setFormat(v as FormatId)}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {FORMATS.map((f) => (
                      <SelectItem key={f.id} value={f.id}>
                        {f.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="report-minconf">Min confidence</Label>
                <Input
                  id="report-minconf"
                  type="number"
                  min={0}
                  max={100}
                  value={minConfidence}
                  onChange={(e) => setMinConfidence(e.target.value)}
                  className="mono"
                />
              </div>
            </div>

            <div className="flex items-start gap-2 rounded-md border border-border bg-bg/40 p-3 text-xs text-muted">
              <Info size={14} className="mt-0.5 shrink-0 text-accent" />
              <span>Every claim in the report cites its source URL + retrieval date.</span>
            </div>

            <Button
              onClick={() => createMutation.mutate()}
              disabled={createMutation.isPending || selectedSections.length === 0}
            >
              {createMutation.isPending ? <Spinner className="h-4 w-4" /> : <FileText size={15} />}
              Generate report
            </Button>
          </CardContent>
        </Card>

        {/* Past reports */}
        <Card>
          <CardHeader>
            <CardTitle>Past reports</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            {reportsLoading ? (
              <div className="space-y-2 p-4">
                {Array.from({ length: 3 }).map((_, i) => (
                  <Skeleton key={i} className="h-14 w-full" />
                ))}
              </div>
            ) : !reports || reports.length === 0 ? (
              <EmptyState
                icon={FileText}
                title="No reports yet"
                description="Generated reports will appear here with download links for each artifact."
              />
            ) : (
              <ul className="divide-y divide-border">
                {reports.map((r) => {
                  const artifacts = Object.entries(r.artifacts ?? {});
                  return (
                    <li key={r.id} className="flex flex-wrap items-center gap-3 p-4">
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <span className="truncate text-sm font-medium text-text">{r.title}</span>
                          <Badge variant={statusVariant(r.status)} className="capitalize">
                            {r.status === "pending" && <Loader2 size={11} className="animate-spin" />}
                            {r.status}
                          </Badge>
                          <Badge variant="outline" className="uppercase">{r.format}</Badge>
                        </div>
                        <p className="mt-0.5 text-xs text-muted">
                          {r.generated_at
                            ? `Generated ${relativeTime(r.generated_at)}`
                            : `Created ${relativeTime(r.created_at)}`}
                        </p>
                        {r.status === "failed" && r.error && (
                          <p className="mt-1 flex items-center gap-1.5 text-xs text-danger">
                            <AlertTriangle size={12} /> {r.error}
                          </p>
                        )}
                      </div>
                      <div className="flex flex-wrap items-center gap-2">
                        {r.status === "ready" && artifacts.length > 0 ? (
                          artifacts.map(([ext]) => (
                            <a
                              key={ext}
                              href={api.reports.downloadUrl(caseId, r.id, ext)}
                              download
                              className="inline-flex h-8 items-center gap-1.5 rounded-md border border-border bg-raised px-3 text-xs font-medium text-text transition-colors hover:bg-raised/70"
                            >
                              <Download size={13} />
                              {ext.toUpperCase()}
                            </a>
                          ))
                        ) : r.status === "pending" ? (
                          <span className="text-xs text-muted">Generating…</span>
                        ) : r.status === "ready" ? (
                          <span className="text-xs text-muted">No artifacts</span>
                        ) : null}
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Right: live preview */}
      <div className="lg:sticky lg:top-4 lg:self-start">
        <Card>
          <CardHeader>
            <CardTitle>Preview</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4 text-sm">
            <div>
              <p className="text-xs text-muted">Title</p>
              <p className="truncate font-medium text-text">{title.trim() || "Investigation report"}</p>
            </div>
            <Separator />
            <div>
              <p className="mb-1 text-xs text-muted">Included sections</p>
              {selectedSections.length === 0 ? (
                <p className="text-xs text-warning">Select at least one section.</p>
              ) : (
                <ul className="space-y-1">
                  {SECTIONS.filter((s) => sections[s.id]).map((s) => (
                    <li key={s.id} className="flex items-center gap-2 text-text">
                      <Check size={13} className="text-success" />
                      {s.label}
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <Separator />
            <div className="grid grid-cols-2 gap-2">
              <div className="rounded-md border border-border bg-bg/40 p-2.5">
                <p className="text-xs text-muted">Entities</p>
                {headLoading ? (
                  <Skeleton className="mt-1 h-5 w-10" />
                ) : (
                  <p className="mono text-lg font-semibold tabular-nums text-text">{totalEntities}</p>
                )}
              </div>
              <div className="rounded-md border border-border bg-bg/40 p-2.5">
                <p className="text-xs text-muted">Format</p>
                <p className="text-lg font-semibold uppercase text-text">{format}</p>
              </div>
            </div>
            <p className="text-xs text-muted">
              Min confidence ≥ <span className="mono text-text">{Number(minConfidence) || 0}</span>.
              Lower-confidence entities are excluded.
            </p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
