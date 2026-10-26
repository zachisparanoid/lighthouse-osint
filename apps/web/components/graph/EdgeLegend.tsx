"use client";

import { ChevronDown, ChevronUp, Info } from "lucide-react";
import { useState } from "react";

import { entityLabel } from "@/lib/theme";
import { ENTITY_TYPES, type EntityType } from "@/lib/types";
import { cn } from "@/lib/utils";

import { EntityDot } from "@/components/entity/EntityBadge";

/** A compact, collapsible legend of entity types + a note about edges. */
export function EdgeLegend({ className }: { className?: string }) {
  const [open, setOpen] = useState(false);

  return (
    <div
      className={cn(
        "pointer-events-auto w-52 overflow-hidden rounded-lg border border-border bg-surface/95 shadow-card backdrop-blur",
        className,
      )}
    >
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2 px-3 py-2 text-xs font-medium text-muted transition-colors hover:text-text"
      >
        <Info size={13} />
        <span>Legend</span>
        {open ? (
          <ChevronDown size={14} className="ml-auto" />
        ) : (
          <ChevronUp size={14} className="ml-auto" />
        )}
      </button>

      {open && (
        <div className="border-t border-border px-3 py-2.5">
          <div className="grid grid-cols-2 gap-x-3 gap-y-1.5">
            {ENTITY_TYPES.map((t: EntityType) => (
              <div key={t} className="flex items-center gap-1.5 text-[11px] text-muted">
                <EntityDot type={t} size={8} />
                <span className="truncate">{entityLabel(t)}</span>
              </div>
            ))}
          </div>
          <p className="mt-2.5 border-t border-border pt-2 text-[10px] leading-relaxed text-muted">
            Arrows point from source to target; edge labels name the relationship (e.g. resolves
            to, owns). Node size reflects how many sources corroborate it.
          </p>
        </div>
      )}
    </div>
  );
}
