"use client";

import type { StylesheetStyle } from "cytoscape";

import { ConfidenceMeter } from "@/components/entity/ConfidenceMeter";
import { entityColor, entityIcon, entityIsMono, entityLabel } from "@/lib/theme";
import type { EntityType } from "@/lib/types";

/** Shape of a node's `data` payload we put into Cytoscape. */
export interface NodeData {
  id: string;
  label: string;
  value: string;
  etype: EntityType;
  color: string;
  confidence: number;
  sources: number;
  conflicting: boolean;
  pinned: boolean;
}

/**
 * Returns the Cytoscape stylesheet for the graph. Node visuals are driven entirely by
 * `data(...)` so the style is computed once and reacts to data changes (size by source_count,
 * border in the type hue, accent ring on selection, dashed warning border when conflicting).
 */
export function graphStylesheet(): StylesheetStyle[] {
  return [
    {
      selector: "node",
      style: {
        "background-color": "data(color)",
        "background-opacity": 0.92,
        label: "data(label)",
        color: "#E6EDF3",
        "font-size": 9,
        "font-family": "var(--font-inter), system-ui, sans-serif",
        "text-valign": "bottom",
        "text-halign": "center",
        "text-margin-y": 4,
        "text-wrap": "wrap",
        "text-max-width": "92px",
        "text-outline-color": "#0B0F14",
        "text-outline-width": 2,
        // Subtle size scaling by source_count (mapped from 1..12 -> 22..46px).
        width: "mapData(sources, 1, 12, 22, 46)" as unknown as number,
        height: "mapData(sources, 1, 12, 22, 46)" as unknown as number,
        "min-zoomed-font-size": 6,
        shape: "ellipse",
        "border-width": 2,
        "border-color": "data(color)",
        "border-opacity": 0.85,
        "transition-property": "border-width, border-color, background-opacity, width, height",
        "transition-duration": 120 as unknown as number,
      },
    },
    // Non-mono types read better as rounded rectangles (person, org, location, social, breach).
    {
      selector: "node[shape = 'round-rectangle']",
      style: { shape: "round-rectangle" },
    },
    {
      selector: "node[?pinned]",
      style: {
        "border-style": "double",
        "border-width": 4,
      },
    },
    {
      selector: "node[?conflicting]",
      style: {
        "border-color": "#F59E0B",
        "border-style": "dashed",
        "border-width": 2.5,
        "border-opacity": 1,
      },
    },
    {
      selector: "node:selected",
      style: {
        "border-color": "#3B82F6",
        "border-width": 4,
        "border-opacity": 1,
        "overlay-color": "#3B82F6",
        "overlay-opacity": 0.18,
        "overlay-padding": 6,
        "z-index": 10,
      },
    },
    {
      selector: "node.faded",
      style: { opacity: 0.12, "text-opacity": 0.05, events: "no" },
    },
    {
      selector: "node.entering",
      style: { "background-opacity": 0, "border-opacity": 0, opacity: 0 },
    },
    {
      selector: "edge",
      style: {
        width: 1.5,
        "line-color": "rgba(139,152,169,0.45)",
        "curve-style": "bezier",
        "target-arrow-shape": "triangle",
        "target-arrow-color": "rgba(139,152,169,0.55)",
        "arrow-scale": 0.8,
        label: "data(label)",
        "font-size": 7,
        color: "#8B98A9",
        "text-rotation": "autorotate" as unknown as number,
        "text-background-color": "#0B0F14",
        "text-background-opacity": 0.7,
        "text-background-padding": "1px" as unknown as string,
        "min-zoomed-font-size": 8,
      },
    },
    {
      selector: "edge.faded",
      style: { opacity: 0.05, "text-opacity": 0, events: "no" },
    },
  ];
}

/** Decide the node shape from the entity type (mono = identifier-ish = ellipse). */
export function nodeShape(type: EntityType): "ellipse" | "round-rectangle" {
  return entityIsMono(type) ? "ellipse" : "round-rectangle";
}

/** React content for the hover tooltip / quick-facts card. */
export function EntityHoverCard({
  type,
  value,
  label,
  confidence,
  sources,
  conflicting,
}: {
  type: EntityType;
  value: string;
  label: string;
  confidence: number;
  sources: number;
  conflicting: boolean;
}) {
  const Icon = entityIcon(type);
  const color = entityColor(type);
  const mono = entityIsMono(type);
  return (
    <div className="w-56 space-y-2 rounded-lg border border-border bg-raised p-3 shadow-glow">
      <div className="flex items-center gap-2">
        <span className="flex h-4 w-4 shrink-0 items-center justify-center" style={{ color }}>
          <Icon size={14} strokeWidth={2} />
        </span>
        <span className="text-xs font-medium text-muted">{entityLabel(type)}</span>
        {conflicting && (
          <span className="ml-auto rounded bg-warning/15 px-1.5 py-0.5 text-[10px] font-medium text-warning">
            conflicting
          </span>
        )}
      </div>
      <div className={mono ? "mono break-all text-[13px] text-text" : "break-words text-sm text-text"}>
        {label || value}
      </div>
      <ConfidenceMeter value={confidence} size="sm" />
      <div className="text-[11px] text-muted">
        {sources} source{sources === 1 ? "" : "s"}
      </div>
    </div>
  );
}
