"use client";

import { useQueryClient } from "@tanstack/react-query";
import { GitBranch, EyeOff, Pin, PinOff, Play, Tag, Trash2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { AutoExpandDialog } from "@/components/collection/AutoExpandDialog";
import { RunModuleDialog } from "@/components/collection/RunModuleDialog";
import { api, ApiError } from "@/lib/api";
import type { Entity } from "@/lib/types";

export interface NodeMenuState {
  id: string;
  x: number;
  y: number;
}

const itemCls =
  "flex w-full cursor-pointer select-none items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-sm text-text outline-none transition-colors hover:bg-bg/80 disabled:opacity-50";

/**
 * A small absolutely-positioned context menu for a graph node. Rendered at viewport
 * coordinates (fixed). Opens RunModule / AutoExpand dialogs and performs entity mutations.
 */
export function GraphNodeMenu({
  caseId,
  state,
  entity,
  onClose,
  onHide,
  onChanged,
}: {
  caseId: string;
  state: NodeMenuState;
  entity: Entity | null;
  onClose: () => void;
  onHide: (id: string) => void;
  onChanged: () => void;
}) {
  const qc = useQueryClient();
  const ref = useRef<HTMLDivElement>(null);
  const [runOpen, setRunOpen] = useState(false);
  const [expandOpen, setExpandOpen] = useState(false);
  const [tagging, setTagging] = useState(false);
  const [tagValue, setTagValue] = useState("");
  const [busy, setBusy] = useState(false);

  // Close on outside click / Escape.
  useEffect(() => {
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("mousedown", onDown);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("mousedown", onDown);
      window.removeEventListener("keydown", onKey);
    };
  }, [onClose]);

  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ["graph", caseId] });
    void qc.invalidateQueries({ queryKey: ["entity", caseId, state.id] });
    onChanged();
  };

  const togglePin = async () => {
    if (!entity) return;
    setBusy(true);
    try {
      await api.entities.update(caseId, entity.id, { pinned: !entity.pinned });
      toast.success(entity.pinned ? "Unpinned" : "Pinned");
      refresh();
      onClose();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Failed to update");
    } finally {
      setBusy(false);
    }
  };

  const addTag = async () => {
    if (!entity) return;
    const t = tagValue.trim();
    if (!t) return;
    setBusy(true);
    try {
      const tags = Array.from(new Set([...entity.tags, t]));
      await api.entities.update(caseId, entity.id, { tags });
      toast.success(`Tagged “${t}”`);
      setTagValue("");
      setTagging(false);
      refresh();
      onClose();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Failed to tag");
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    setBusy(true);
    try {
      await api.entities.remove(caseId, state.id);
      toast.success("Entity deleted");
      refresh();
      onClose();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Failed to delete");
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <div
        ref={ref}
        className="fixed z-50 min-w-[200px] animate-fade-in rounded-lg border border-border bg-raised p-1 shadow-glow"
        style={{ left: state.x, top: state.y }}
        role="menu"
      >
        {tagging ? (
          <div className="p-1.5">
            <input
              autoFocus
              value={tagValue}
              onChange={(e) => setTagValue(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") void addTag();
              }}
              placeholder="Tag name…"
              className="h-8 w-full rounded-md border border-border bg-bg/60 px-2.5 text-sm text-text placeholder:text-muted/70 focus-visible:shadow-focus focus-visible:outline-none"
            />
            <div className="mt-1.5 flex justify-end gap-1.5">
              <button className={itemCls + " w-auto px-2 py-1"} onClick={() => setTagging(false)}>
                Cancel
              </button>
              <button
                className="rounded-md bg-accent px-2.5 py-1 text-xs font-medium text-white hover:bg-accent/90 disabled:opacity-50"
                onClick={() => void addTag()}
                disabled={busy || !tagValue.trim()}
              >
                Add
              </button>
            </div>
          </div>
        ) : (
          <>
            <button
              role="menuitem"
              className={itemCls}
              onClick={() => {
                setRunOpen(true);
              }}
            >
              <Play size={14} className="text-muted" /> Run module…
            </button>
            <button
              role="menuitem"
              className={itemCls}
              onClick={() => void togglePin()}
              disabled={!entity || busy}
            >
              {entity?.pinned ? (
                <>
                  <PinOff size={14} className="text-muted" /> Unpin
                </>
              ) : (
                <>
                  <Pin size={14} className="text-muted" /> Pin
                </>
              )}
            </button>
            <button
              role="menuitem"
              className={itemCls}
              onClick={() => setExpandOpen(true)}
              disabled={!entity}
            >
              <GitBranch size={14} className="text-muted" /> Auto-expand from here
            </button>
            <button role="menuitem" className={itemCls} onClick={() => setTagging(true)} disabled={!entity}>
              <Tag size={14} className="text-muted" /> Tag…
            </button>
            <button
              role="menuitem"
              className={itemCls}
              onClick={() => {
                onHide(state.id);
                onClose();
              }}
            >
              <EyeOff size={14} className="text-muted" /> Hide
            </button>
            <div className="-mx-1 my-1 h-px bg-border" />
            <button
              role="menuitem"
              className={itemCls + " text-danger hover:bg-danger/10"}
              onClick={() => void remove()}
              disabled={busy}
            >
              <Trash2 size={14} /> Delete
            </button>
          </>
        )}
      </div>

      {entity && (
        <RunModuleDialog
          caseId={caseId}
          entity={entity}
          open={runOpen}
          onOpenChange={(o) => {
            setRunOpen(o);
            if (!o) onClose();
          }}
        />
      )}
      {entity && (
        <AutoExpandDialog
          caseId={caseId}
          open={expandOpen}
          onOpenChange={(o) => {
            setExpandOpen(o);
            if (!o) onClose();
          }}
          defaultSeedId={entity.id}
        />
      )}
    </>
  );
}
