"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import cytoscape, { type Core, type EventObject, type NodeSingular } from "cytoscape";
// cytoscape-fcose ships no types; the runtime export is a Cytoscape extension registrant.
// @ts-expect-error — untyped CJS module
import fcose from "cytoscape-fcose";
import { useReducedMotion } from "framer-motion";
import { useEffect, useMemo, useRef, useState, type MutableRefObject } from "react";
import { createRoot, type Root } from "react-dom/client";
import { toast } from "sonner";

import { Spinner } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { useUi } from "@/lib/store";
import { entityColor } from "@/lib/theme";
import { RELATIONSHIP_TYPE_LABELS, type Entity, type GraphResponse } from "@/lib/types";

import { EntityHoverCard, graphStylesheet, nodeShape, type NodeData } from "./EntityNode";
import { GraphNodeMenu, type NodeMenuState } from "./GraphNodeMenu";

let fcoseRegistered = false;
function ensureExtensions() {
  if (!fcoseRegistered) {
    cytoscape.use(fcose);
    fcoseRegistered = true;
  }
}

function toNodeData(e: Entity | GraphResponse["entities"][number]): NodeData {
  return {
    id: e.id,
    label: e.label || e.value,
    value: e.value,
    etype: e.type,
    color: entityColor(e.type),
    confidence: Math.round(e.confidence),
    sources: Math.max(1, e.source_count),
    conflicting: e.conflicting,
    pinned: (e as Entity).pinned ?? false,
  };
}

export function GraphCanvas({
  caseId,
  cyRef,
  onCyReady,
}: {
  caseId: string;
  cyRef?: MutableRefObject<Core | null>;
  onCyReady?: (cy: Core) => void;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const localCy = useRef<Core | null>(null);
  const reduce = useReducedMotion();
  const qc = useQueryClient();

  const { graphFilters, focusEntityId, setFocusEntityId, setSelectedEntityId } = useUi();

  // Track previously seen node ids so we can spring-in only the newly added ones.
  const seenIds = useRef<Set<string>>(new Set());
  const didInitialLayout = useRef(false);
  const hiddenIds = useRef<Set<string>>(new Set());

  // Hover tooltip overlay (React-managed; positioned from rendered node coords).
  const tipRef = useRef<HTMLDivElement>(null);
  const tipRootRef = useRef<Root | null>(null);

  // Right-click context menu state.
  const [menu, setMenu] = useState<NodeMenuState | null>(null);

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["graph", caseId],
    queryFn: () => api.entities.graph(caseId, { limit: 1500 }),
  });

  // Stable lookup of the current entity objects for menu / hover content.
  const entityById = useMemo(() => {
    const m = new Map<string, Entity>();
    for (const e of data?.entities ?? []) m.set(e.id, e as Entity);
    return m;
  }, [data]);

  // ---- Initialize Cytoscape once. ----
  useEffect(() => {
    if (!containerRef.current || localCy.current) return;
    ensureExtensions();

    const cy = cytoscape({
      container: containerRef.current,
      style: graphStylesheet(),
      elements: [],
      minZoom: 0.15,
      maxZoom: 3,
      wheelSensitivity: 0.2,
      boxSelectionEnabled: false,
      autoungrabify: false,
    });
    localCy.current = cy;
    if (cyRef) cyRef.current = cy;
    onCyReady?.(cy);

    // Capture a PNG after each layout so the report builder can embed a graph snapshot.
    cy.on("layoutstop", () => {
      try {
        useUi.getState().setGraphSnapshot(
          cy.png({ output: "base64", bg: "#0B0F14", full: false, scale: 1.2, maxWidth: 1600, maxHeight: 1000 }),
        );
      } catch {
        /* snapshot is best-effort */
      }
    });

    // Selection: clicking a node selects it globally; tapping the background clears.
    cy.on("tap", "node", (evt: EventObject) => {
      const id = (evt.target as NodeSingular).id();
      setSelectedEntityId(id);
    });
    cy.on("tap", (evt: EventObject) => {
      if (evt.target === cy) setSelectedEntityId(null);
    });

    // Right-click -> context menu anchored at the rendered position.
    cy.on("cxttap", "node", (evt: EventObject) => {
      const node = evt.target as NodeSingular;
      const rp = node.renderedPosition();
      const rect = containerRef.current?.getBoundingClientRect();
      setMenu({
        id: node.id(),
        x: (rect?.left ?? 0) + rp.x,
        y: (rect?.top ?? 0) + rp.y,
      });
    });
    cy.on("tap pan zoom", () => setMenu(null));

    // Hover quick-facts tooltip.
    const showTip = (node: NodeSingular) => {
      const tip = tipRef.current;
      if (!tip) return;
      const d = node.data() as NodeData;
      const rp = node.renderedPosition();
      tip.style.left = `${rp.x}px`;
      tip.style.top = `${rp.y - node.renderedHeight() / 2 - 8}px`;
      tip.style.display = "block";
      if (!tipRootRef.current) tipRootRef.current = createRoot(tip);
      tipRootRef.current.render(
        <EntityHoverCard
          type={d.etype}
          value={d.value}
          label={d.label}
          confidence={d.confidence}
          sources={d.sources}
          conflicting={d.conflicting}
        />,
      );
    };
    const hideTip = () => {
      if (tipRef.current) tipRef.current.style.display = "none";
    };
    cy.on("mouseover", "node", (evt: EventObject) => showTip(evt.target as NodeSingular));
    cy.on("mouseout", "node", hideTip);
    cy.on("pan zoom drag", hideTip);

    return () => {
      hideTip();
      tipRootRef.current?.unmount();
      tipRootRef.current = null;
      cy.destroy();
      localCy.current = null;
      if (cyRef) cyRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ---- Sync graph data into Cytoscape (diff add/remove). ----
  useEffect(() => {
    const cy = localCy.current;
    if (!cy || !data) return;

    const layout = data.layout ?? {};
    const nextIds = new Set(data.entities.map((e) => e.id));

    cy.batch(() => {
      // Remove vanished elements.
      cy.nodes().forEach((n) => {
        if (!nextIds.has(n.id())) n.remove();
      });

      // Upsert nodes.
      const freshlyAdded: string[] = [];
      for (const e of data.entities) {
        const existing = cy.getElementById(e.id);
        const nodeData = toNodeData(e);
        if (existing.nonempty()) {
          existing.data(nodeData);
          existing.data("shape", nodeShape(e.type));
        } else {
          const pos = layout[e.id];
          const node = cy.add({
            group: "nodes",
            data: { ...nodeData, shape: nodeShape(e.type) },
            ...(pos ? { position: { x: pos.x, y: pos.y } } : {}),
          });
          if (didInitialLayout.current && !seenIds.current.has(e.id)) {
            node.addClass("entering");
            freshlyAdded.push(e.id);
          }
        }
        seenIds.current.add(e.id);
      }

      // Upsert edges (only those whose endpoints exist).
      const edgeIds = new Set(data.edges.map((ed) => ed.id));
      cy.edges().forEach((ed) => {
        if (!edgeIds.has(ed.id())) ed.remove();
      });
      for (const ed of data.edges) {
        if (!nextIds.has(ed.source_entity_id) || !nextIds.has(ed.target_entity_id)) continue;
        if (cy.getElementById(ed.id).nonempty()) continue;
        cy.add({
          group: "edges",
          data: {
            id: ed.id,
            source: ed.source_entity_id,
            target: ed.target_entity_id,
            label: relLabel(ed.relationship),
          },
        });
      }

      // Spring-in newly added nodes (unless reduced motion).
      if (!reduce && freshlyAdded.length) {
        for (const id of freshlyAdded) {
          const node = cy.getElementById(id);
          node.removeClass("entering");
          node.animate(
            { style: { "background-opacity": 0.92, "border-opacity": 0.85, opacity: 1 } },
            { duration: 280 },
          );
        }
      } else if (freshlyAdded.length) {
        // Reduced motion: just reveal immediately.
        for (const id of freshlyAdded) cy.getElementById(id).removeClass("entering");
      }
    });

    // Run the layout once on first load (or whenever there were no saved positions).
    const hasSavedPositions = Object.keys(layout).length > 0;
    if (!didInitialLayout.current) {
      didInitialLayout.current = true;
      if (hasSavedPositions) {
        // Layout already applied via preset positions above; just fit.
        cy.fit(undefined, 60);
      } else {
        runFcose(cy, !reduce);
      }
    } else if (data.entities.some((e) => !layout[e.id] && isNewlyPlaced(cy, e.id))) {
      // New nodes without saved positions: lay them out gently without disturbing the rest.
      runFcose(cy, !reduce, true);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, reduce]);

  // ---- React to graph filters (type set + min confidence). ----
  useEffect(() => {
    const cy = localCy.current;
    if (!cy) return;
    const { types, minConfidence } = graphFilters;
    const typeSet = new Set(types);
    cy.batch(() => {
      cy.nodes().forEach((n) => {
        const d = n.data() as NodeData;
        const typeOk = typeSet.size === 0 || typeSet.has(d.etype);
        const confOk = d.confidence >= minConfidence;
        const hidden = hiddenIds.current.has(n.id());
        if (typeOk && confOk && !hidden) n.removeClass("faded");
        else n.addClass("faded");
      });
      // Fade edges touching any faded/hidden node.
      cy.edges().forEach((ed) => {
        const s = ed.source().hasClass("faded");
        const t = ed.target().hasClass("faded");
        if (s || t) ed.addClass("faded");
        else ed.removeClass("faded");
      });
    });
  }, [graphFilters, data]);

  // ---- React to focusEntityId: select + center + zoom, then clear. ----
  useEffect(() => {
    const cy = localCy.current;
    if (!cy || !focusEntityId) return;
    const node = cy.getElementById(focusEntityId);
    if (node.nonempty()) {
      setSelectedEntityId(focusEntityId);
      cy.animate(
        { center: { eles: node }, zoom: Math.max(1, cy.zoom()) },
        { duration: reduce ? 0 : 360 },
      );
    }
    setFocusEntityId(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusEntityId]);

  // ---- Reflect global selection back into the graph (e.g. opened from the table). ----
  const selectedEntityId = useUi((s) => s.selectedEntityId);
  useEffect(() => {
    const cy = localCy.current;
    if (!cy) return;
    cy.batch(() => {
      cy.nodes(":selected").unselect();
      if (selectedEntityId) {
        const n = cy.getElementById(selectedEntityId);
        if (n.nonempty()) n.select();
      }
    });
  }, [selectedEntityId, data]);

  const hideNode = (id: string) => {
    hiddenIds.current.add(id);
    const cy = localCy.current;
    cy?.getElementById(id).addClass("faded");
    if (selectedEntityId === id) setSelectedEntityId(null);
  };

  return (
    <div className="relative h-full w-full">
      <div ref={containerRef} className="h-full w-full" />

      {/* Hover quick-facts overlay; positioned imperatively, centered on its anchor. */}
      <div
        ref={tipRef}
        className="pointer-events-none absolute z-30 -translate-x-1/2 -translate-y-full"
        style={{ display: "none" }}
      />

      {(isLoading || (!data && !isError)) && (
        <div className="absolute inset-0 flex items-center justify-center bg-bg/40">
          <Spinner className="h-6 w-6 text-muted" />
        </div>
      )}
      {isError && (
        <div className="absolute inset-0 flex items-center justify-center">
          <p className="rounded-md border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger">
            {error instanceof Error ? error.message : "Failed to load graph"}
          </p>
        </div>
      )}
      {data && data.entities.length === 0 && !isLoading && (
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
          <div className="pointer-events-auto max-w-xs text-center">
            <p className="text-sm font-medium text-text">No entities yet</p>
            <p className="mt-1 text-sm text-muted">
              Add a seed entity to begin building the graph.
            </p>
          </div>
        </div>
      )}

      {menu && (
        <GraphNodeMenu
          caseId={caseId}
          state={menu}
          entity={entityById.get(menu.id) ?? null}
          onClose={() => setMenu(null)}
          onHide={hideNode}
          onChanged={() => {
            void qc.invalidateQueries({ queryKey: ["graph", caseId] });
            void qc.invalidateQueries({ queryKey: ["jobs", caseId] });
          }}
        />
      )}

      <span className="sr-only" aria-live="polite">
        {data ? `${data.entities.length} entities` : ""}
      </span>
    </div>
  );
}

// Helpers ---------------------------------------------------------------------

function relLabel(rel: string): string {
  return RELATIONSHIP_TYPE_LABELS[rel as keyof typeof RELATIONSHIP_TYPE_LABELS] ?? rel;
}

function isNewlyPlaced(cy: Core, id: string): boolean {
  const n = cy.getElementById(id);
  if (n.empty()) return false;
  const p = n.position();
  // Cytoscape places position-less nodes at (0,0) initially.
  return p.x === 0 && p.y === 0;
}

export function runFcose(cy: Core, animate: boolean, incremental = false) {
  cy.layout({
    name: "fcose",
    animate,
    animationDuration: 600,
    fit: !incremental,
    padding: 60,
    nodeSeparation: 90,
    idealEdgeLength: 110,
    nodeRepulsion: 9000,
    randomize: !incremental,
    quality: "default",
  } as cytoscape.LayoutOptions).run();
}
