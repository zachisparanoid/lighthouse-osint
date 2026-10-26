"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import {
  AlertTriangle,
  ExternalLink,
  GitBranch,
  KeyRound,
  Pin,
  PinOff,
  Play,
  Plus,
  Trash2,
  X,
} from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { AutoExpandDialog } from "@/components/collection/AutoExpandDialog";
import { ConfidenceMeter } from "@/components/entity/ConfidenceMeter";
import { EntityBadge } from "@/components/entity/EntityBadge";
import { Badge, Separator, Spinner } from "@/components/ui/primitives";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/input";
import { api, ApiError } from "@/lib/api";
import { useAuth, useUi } from "@/lib/store";
import { entityIsMono, entityLabel } from "@/lib/theme";
import type { EntityDetail, ModuleInfo, Note, Provenance } from "@/lib/types";
import { cn, formatDate, relativeTime } from "@/lib/utils";

export function EntityDrawer({ caseId }: { caseId: string }) {
  const selectedEntityId = useUi((s) => s.selectedEntityId);
  const setSelectedEntityId = useUi((s) => s.setSelectedEntityId);
  const reduce = useReducedMotion();

  // Close on Escape.
  useEffect(() => {
    if (!selectedEntityId) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setSelectedEntityId(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [selectedEntityId, setSelectedEntityId]);

  return (
    <AnimatePresence>
      {selectedEntityId && (
        <motion.aside
          key={selectedEntityId}
          initial={reduce ? false : { x: "100%" }}
          animate={{ x: 0 }}
          exit={reduce ? { opacity: 0 } : { x: "100%" }}
          transition={{ duration: 0.2, ease: "easeOut" }}
          className="fixed right-0 top-0 z-40 flex h-full w-[400px] max-w-[calc(100vw-1rem)] flex-col border-l border-border bg-surface shadow-drawer"
          aria-label="Entity details"
        >
          <DrawerBody caseId={caseId} id={selectedEntityId} onClose={() => setSelectedEntityId(null)} />
        </motion.aside>
      )}
    </AnimatePresence>
  );
}

function DrawerBody({
  caseId,
  id,
  onClose,
}: {
  caseId: string;
  id: string;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const [expandOpen, setExpandOpen] = useState(false);

  const { data: entity, isLoading, isError, error } = useQuery({
    queryKey: ["entity", caseId, id],
    queryFn: () => api.entities.get(caseId, id),
  });

  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: ["entity", caseId, id] });
    void qc.invalidateQueries({ queryKey: ["graph", caseId] });
    void qc.invalidateQueries({ queryKey: ["entities", caseId] });
  };

  const pinMutation = useMutation({
    mutationFn: (pinned: boolean) => api.entities.update(caseId, id, { pinned }),
    onSuccess: (_d, pinned) => {
      toast.success(pinned ? "Pinned" : "Unpinned");
      invalidate();
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "Failed"),
  });

  const deleteMutation = useMutation({
    mutationFn: () => api.entities.remove(caseId, id),
    onSuccess: () => {
      toast.success("Entity deleted");
      invalidate();
      onClose();
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "Failed to delete"),
  });

  return (
    <>
      {/* Header */}
      <div className="flex items-start justify-between gap-2 border-b border-border p-4">
        <div className="min-w-0 flex-1">
          {entity ? (
            <>
              <div className="flex items-center gap-2">
                <EntityBadge
                  type={entity.type}
                  value={entity.value}
                  label={entity.label}
                  className="text-base font-semibold"
                />
              </div>
              <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                <Badge variant="outline">{entityLabel(entity.type)}</Badge>
                {entity.conflicting && (
                  <Badge variant="warning" className="gap-1">
                    <AlertTriangle size={11} /> conflicting
                  </Badge>
                )}
                {entity.pinned && (
                  <Badge variant="accent" className="gap-1">
                    <Pin size={10} /> pinned
                  </Badge>
                )}
              </div>
            </>
          ) : (
            <div className="h-6 w-40 skeleton" />
          )}
        </div>
        <button
          onClick={onClose}
          aria-label="Close"
          className="rounded p-1 text-muted transition-colors hover:bg-bg/60 hover:text-text"
        >
          <X size={18} />
        </button>
      </div>

      {/* Scrollable content */}
      <div className="flex-1 overflow-auto">
        {isLoading && (
          <div className="flex justify-center py-12">
            <Spinner className="h-6 w-6 text-muted" />
          </div>
        )}
        {isError && (
          <p className="m-4 rounded-md border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger">
            {error instanceof Error ? error.message : "Failed to load entity"}
          </p>
        )}

        {entity && (
          <div className="divide-y divide-border">
            {/* Confidence + lifecycle */}
            <section className="space-y-3 p-4">
              <div className="space-y-1.5">
                <div className="flex items-center justify-between text-xs text-muted">
                  <span>Confidence</span>
                </div>
                <ConfidenceMeter value={Math.round(entity.confidence)} />
              </div>
              <dl className="grid grid-cols-3 gap-2 text-xs">
                <Meta label="First seen" value={formatDate(entity.first_seen)} />
                <Meta label="Last seen" value={formatDate(entity.last_seen)} />
                <Meta label="Sources" value={String(entity.source_count)} />
              </dl>
            </section>

            <AttributesSection entity={entity} />
            <TagsSection caseId={caseId} entity={entity} onChanged={invalidate} />
            <ActionsSection
              caseId={caseId}
              entity={entity}
              onExpand={() => setExpandOpen(true)}
              onPin={() => pinMutation.mutate(!entity.pinned)}
              onDelete={() => deleteMutation.mutate()}
              pinning={pinMutation.isPending}
              deleting={deleteMutation.isPending}
            />
            <ProvenanceSection provenances={entity.provenances} />
            <NotesSection caseId={caseId} entityId={id} />
          </div>
        )}
      </div>

      {entity && (
        <AutoExpandDialog
          caseId={caseId}
          open={expandOpen}
          onOpenChange={setExpandOpen}
          defaultSeedId={entity.id}
        />
      )}
    </>
  );
}

function Meta({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-muted">{label}</dt>
      <dd className="mt-0.5 text-text">{value}</dd>
    </div>
  );
}

// --- Attributes (with _conflicts) --------------------------------------------

function AttributesSection({ entity }: { entity: EntityDetail }) {
  const attrs = entity.attributes ?? {};
  const conflicts = (attrs._conflicts ?? null) as Record<string, unknown> | null;
  const entries = Object.entries(attrs).filter(([k]) => k !== "_conflicts");
  const mono = entityIsMono(entity.type);

  if (entries.length === 0 && !conflicts) {
    return (
      <section className="p-4">
        <SectionTitle>Attributes</SectionTitle>
        <p className="mt-2 text-sm text-muted">No attributes recorded.</p>
      </section>
    );
  }

  return (
    <section className="p-4">
      <SectionTitle>Attributes</SectionTitle>
      <table className="mt-2 w-full">
        <tbody>
          {entries.map(([k, v]) => (
            <tr key={k} className="align-top">
              <td className="w-1/3 py-1 pr-3 text-xs text-muted">{k}</td>
              <td className={cn("py-1 text-sm text-text", mono && "mono break-all text-[13px]")}>
                {renderValue(v)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {conflicts && Object.keys(conflicts).length > 0 && (
        <div className="mt-3 space-y-2 rounded-md border border-warning/40 bg-warning/5 p-3">
          <div className="flex items-center gap-1.5 text-xs font-medium text-warning">
            <AlertTriangle size={12} /> Conflicting values
          </div>
          {Object.entries(conflicts).map(([field, val]) => (
            <div key={field} className="text-xs">
              <span className="text-muted">{field}: </span>
              <ConflictValue value={val} />
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function ConflictValue({ value }: { value: unknown }) {
  // Conflicts may be an array of { value, source } objects, or a plain array of values.
  if (Array.isArray(value)) {
    return (
      <ul className="mt-1 space-y-0.5">
        {value.map((item, i) => {
          if (item && typeof item === "object" && "value" in item) {
            const obj = item as { value: unknown; source?: string };
            return (
              <li key={i} className="flex items-baseline gap-1.5">
                <span className="mono text-text">{String(obj.value)}</span>
                {obj.source && <span className="text-[11px] text-muted">— {obj.source}</span>}
              </li>
            );
          }
          return (
            <li key={i} className="mono text-text">
              {String(item)}
            </li>
          );
        })}
      </ul>
    );
  }
  return <span className="mono text-text">{String(value)}</span>;
}

function renderValue(v: unknown): string {
  if (v == null) return "—";
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

// --- Tags --------------------------------------------------------------------

function TagsSection({
  caseId,
  entity,
  onChanged,
}: {
  caseId: string;
  entity: EntityDetail;
  onChanged: () => void;
}) {
  const [adding, setAdding] = useState("");
  const [busy, setBusy] = useState(false);

  const setTags = async (tags: string[]) => {
    setBusy(true);
    try {
      await api.entities.update(caseId, entity.id, { tags });
      onChanged();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Failed to update tags");
    } finally {
      setBusy(false);
    }
  };

  const add = async () => {
    const t = adding.trim();
    if (!t || entity.tags.includes(t)) {
      setAdding("");
      return;
    }
    await setTags([...entity.tags, t]);
    setAdding("");
  };

  return (
    <section className="p-4">
      <SectionTitle>Tags</SectionTitle>
      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        {entity.tags.map((tag) => (
          <span
            key={tag}
            className="inline-flex items-center gap-1 rounded-md border border-border bg-raised px-2 py-0.5 text-xs text-text"
          >
            {tag}
            <button
              onClick={() => void setTags(entity.tags.filter((x) => x !== tag))}
              disabled={busy}
              aria-label={`Remove tag ${tag}`}
              className="text-muted hover:text-danger"
            >
              <X size={11} />
            </button>
          </span>
        ))}
        <span className="inline-flex items-center gap-1 rounded-md border border-dashed border-border px-1.5">
          <input
            value={adding}
            onChange={(e) => setAdding(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") void add();
            }}
            onBlur={() => void add()}
            placeholder="add tag"
            disabled={busy}
            className="h-6 w-20 bg-transparent text-xs text-text placeholder:text-muted/70 focus:outline-none"
          />
          <Plus size={11} className="text-muted" />
        </span>
      </div>
    </section>
  );
}

// --- Actions (run module / compatible collectors / pivots) -------------------

function ActionsSection({
  caseId,
  entity,
  onExpand,
  onPin,
  onDelete,
  pinning,
  deleting,
}: {
  caseId: string;
  entity: EntityDetail;
  onExpand: () => void;
  onPin: () => void;
  onDelete: () => void;
  pinning: boolean;
  deleting: boolean;
}) {
  const qc = useQueryClient();
  const [runningName, setRunningName] = useState<string | null>(null);

  const { data: modules } = useQuery({
    queryKey: ["modules", caseId],
    queryFn: () => api.modules.list(caseId),
  });

  const compatible = (modules ?? []).filter((m) => m.accepts.includes(entity.type) && m.enabled);

  const run = async (m: ModuleInfo) => {
    if (m.requires_key && !m.key_present) return;
    setRunningName(m.name);
    try {
      await api.jobs.run(caseId, m.name, entity.id);
      toast.success(`Queued ${m.title}`);
      void qc.invalidateQueries({ queryKey: ["jobs", caseId] });
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Failed to run collector");
    } finally {
      setRunningName(null);
    }
  };

  return (
    <section className="space-y-3 p-4">
      <SectionTitle>Actions</SectionTitle>

      <div className="flex flex-wrap gap-2">
        <Button size="sm" variant="secondary" onClick={onExpand}>
          <GitBranch size={13} /> Auto-expand
        </Button>
        <Button size="sm" variant="secondary" onClick={onPin} disabled={pinning}>
          {entity.pinned ? <PinOff size={13} /> : <Pin size={13} />}
          {entity.pinned ? "Unpin" : "Pin"}
        </Button>
        <Button size="sm" variant="ghost" onClick={onDelete} disabled={deleting} className="text-danger hover:bg-danger/10">
          <Trash2 size={13} /> Delete
        </Button>
      </div>

      <div className="space-y-1.5">
        <p className="text-xs font-medium text-muted">Run a collector</p>
        {!modules && <p className="text-xs text-muted">Loading collectors…</p>}
        {modules && compatible.length === 0 && (
          <p className="text-xs text-muted">No enabled collector accepts this entity type.</p>
        )}
        <div className="grid grid-cols-2 gap-1.5">
          {compatible.map((m) => {
            const missingKey = !!m.requires_key && !m.key_present;
            return (
              <button
                key={m.name}
                onClick={() => void run(m)}
                disabled={missingKey || runningName === m.name}
                title={missingKey ? "Add key in Settings → Keys" : m.description}
                className={cn(
                  "flex items-center gap-1.5 rounded-md border border-border bg-bg/40 px-2 py-1.5 text-left text-xs transition-colors",
                  missingKey ? "cursor-not-allowed opacity-60" : "hover:bg-bg/70",
                )}
              >
                {runningName === m.name ? (
                  <Spinner className="h-3 w-3 text-muted" />
                ) : missingKey ? (
                  <KeyRound size={12} className="shrink-0 text-warning" />
                ) : (
                  <Play size={12} className="shrink-0 text-muted" />
                )}
                <span className="truncate text-text">{m.title}</span>
              </button>
            );
          })}
        </div>
      </div>

      <PivotSuggestions caseId={caseId} entity={entity} compatible={compatible} onRun={run} />
    </section>
  );
}

function PivotSuggestions({
  caseId,
  entity,
  compatible,
  onRun,
}: {
  caseId: string;
  entity: EntityDetail;
  compatible: ModuleInfo[];
  onRun: (m: ModuleInfo) => void;
}) {
  // "Not yet run" = no provenance from that collector on this entity.
  const ranCollectors = new Set(entity.provenances.map((p) => p.collector_name));
  const suggestions = compatible.filter(
    (m) => !ranCollectors.has(m.name) && !(m.requires_key && !m.key_present),
  );
  if (suggestions.length === 0) return null;

  return (
    <div className="rounded-md border border-accent/30 bg-accent/5 p-2.5">
      <p className="text-xs font-medium text-accent">Suggested pivots</p>
      <div className="mt-1.5 flex flex-wrap gap-1.5">
        {suggestions.slice(0, 6).map((m) => (
          <button
            key={m.name}
            onClick={() => onRun(m)}
            className="rounded-md border border-accent/40 bg-accent/10 px-2 py-0.5 text-[11px] text-accent hover:bg-accent/20"
          >
            {m.title}
          </button>
        ))}
      </div>
    </div>
  );
}

// --- Provenance --------------------------------------------------------------

function ProvenanceSection({ provenances }: { provenances: Provenance[] }) {
  return (
    <section className="p-4">
      <div className="flex items-center justify-between">
        <SectionTitle>Provenance</SectionTitle>
        <span className="text-[11px] text-muted">{provenances.length} citation{provenances.length === 1 ? "" : "s"}</span>
      </div>
      {provenances.length === 0 ? (
        <p className="mt-2 text-sm text-muted">No provenance recorded.</p>
      ) : (
        <ul className="mt-2 space-y-2">
          {provenances.map((p) => (
            <li key={p.id} className="rounded-md border border-border bg-bg/40 p-2.5">
              <div className="flex items-center justify-between gap-2">
                <Badge variant="default">{p.collector_name}</Badge>
                <span className="text-[11px] text-muted">{relativeTime(p.retrieved_at)}</span>
              </div>
              {p.source_url ? (
                <a
                  href={p.source_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="mt-1.5 flex items-center gap-1 break-all text-xs font-medium text-accent hover:underline"
                >
                  <ExternalLink size={12} className="shrink-0" />
                  {p.source_url}
                </a>
              ) : (
                <p className="mt-1.5 text-xs italic text-muted">No source URL provided</p>
              )}
              {p.license_note && (
                <p className="mt-1 text-[11px] text-muted">{p.license_note}</p>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

// --- Notes -------------------------------------------------------------------

function NotesSection({ caseId, entityId }: { caseId: string; entityId: string }) {
  const qc = useQueryClient();
  const userId = useAuth((s) => s.user?.id);
  const [draft, setDraft] = useState("");

  const { data: notes, isLoading } = useQuery({
    queryKey: ["notes", caseId, entityId],
    queryFn: () => api.cases.notes(caseId, entityId),
  });

  const addMutation = useMutation({
    mutationFn: (body: string) => api.cases.addNote(caseId, { body, entity_id: entityId }),
    onSuccess: () => {
      setDraft("");
      void qc.invalidateQueries({ queryKey: ["notes", caseId, entityId] });
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "Failed to add note"),
  });

  const deleteMutation = useMutation({
    mutationFn: (noteId: string) => api.cases.deleteNote(caseId, noteId),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["notes", caseId, entityId] }),
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "Failed to delete note"),
  });

  return (
    <section className="p-4">
      <SectionTitle>Notes</SectionTitle>

      <div className="mt-2 space-y-2">
        {isLoading && <div className="skeleton h-10 w-full" />}
        {notes?.map((n: Note) => (
          <div key={n.id} className="group rounded-md border border-border bg-bg/40 p-2.5">
            <p className="whitespace-pre-wrap text-sm text-text">{n.body}</p>
            <div className="mt-1 flex items-center justify-between">
              <span className="text-[11px] text-muted">{relativeTime(n.created_at)}</span>
              {userId && n.author_id === userId && (
                <button
                  onClick={() => deleteMutation.mutate(n.id)}
                  className="text-[11px] text-muted opacity-0 transition-opacity hover:text-danger group-hover:opacity-100"
                >
                  Delete
                </button>
              )}
            </div>
          </div>
        ))}
        {notes && notes.length === 0 && !isLoading && (
          <p className="text-xs text-muted">No notes yet.</p>
        )}
      </div>

      <div className="mt-2 space-y-1.5">
        <Textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Add a note…"
          className="min-h-[60px] text-sm"
        />
        <div className="flex justify-end">
          <Button
            size="sm"
            onClick={() => draft.trim() && addMutation.mutate(draft.trim())}
            disabled={!draft.trim() || addMutation.isPending}
          >
            {addMutation.isPending && <Spinner className="h-3.5 w-3.5" />}
            Add note
          </Button>
        </div>
      </div>
    </section>
  );
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return <h3 className="text-xs font-semibold uppercase tracking-wide text-muted">{children}</h3>;
}
