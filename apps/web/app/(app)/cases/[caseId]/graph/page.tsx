"use client";

import { useQuery } from "@tanstack/react-query";
import type { Core } from "cytoscape";
import { MonitorSmartphone } from "lucide-react";
import Link from "next/link";
import { useRef, useState } from "react";

import { EdgeLegend } from "@/components/graph/EdgeLegend";
import { GraphCanvas } from "@/components/graph/GraphCanvas";
import { GraphControls } from "@/components/graph/GraphControls";
import { EntityBadge } from "@/components/entity/EntityBadge";
import { Button } from "@/components/ui/button";
import { ConfidenceMeter } from "@/components/entity/ConfidenceMeter";
import { api } from "@/lib/api";
import { useUi } from "@/lib/store";
import type { Entity } from "@/lib/types";

export default function GraphPage({ params }: { params: { caseId: string } }) {
  const caseId = params.caseId;
  const cyRef = useRef<Core | null>(null);
  const [cy, setCy] = useState<Core | null>(null);

  return (
    <div className="relative h-full w-full">
      {/* Desktop / tablet graph */}
      <div className="hidden h-full w-full md:block">
        <GraphCanvas
          caseId={caseId}
          cyRef={cyRef}
          onCyReady={(instance) => setCy(instance)}
        />
        <div className="pointer-events-none absolute inset-0 p-3">
          <div className="pointer-events-auto absolute left-3 top-3">
            <GraphControls caseId={caseId} cy={cy} />
          </div>
          <div className="pointer-events-auto absolute bottom-3 left-3">
            <EdgeLegend />
          </div>
        </div>
      </div>

      {/* Small-screen fallback */}
      <div className="block h-full overflow-auto md:hidden">
        <CompactEntityList caseId={caseId} />
      </div>
    </div>
  );
}

function CompactEntityList({ caseId }: { caseId: string }) {
  const setSelectedEntityId = useUi((s) => s.setSelectedEntityId);
  const { data, isLoading } = useQuery({
    queryKey: ["graph", caseId],
    queryFn: () => api.entities.graph(caseId, { limit: 1500 }),
  });

  return (
    <div className="p-4">
      <div className="mb-3 flex items-start gap-2 rounded-md border border-border bg-raised p-3">
        <MonitorSmartphone size={16} className="mt-0.5 shrink-0 text-muted" />
        <div className="text-sm">
          <p className="font-medium text-text">Graph is best on larger screens</p>
          <p className="mt-0.5 text-muted">
            Here is a compact entity list. For the full graph, use a wider display or open the{" "}
            <Link href={`/cases/${caseId}/entities`} className="text-accent hover:underline">
              Entities
            </Link>{" "}
            tab.
          </p>
        </div>
      </div>

      {isLoading && <div className="skeleton h-40 w-full" />}
      <ul className="space-y-1.5">
        {data?.entities.map((e: Entity) => (
          <li key={e.id}>
            <button
              onClick={() => setSelectedEntityId(e.id)}
              className="flex w-full items-center gap-2 rounded-md border border-border bg-surface px-3 py-2 text-left hover:bg-raised/60"
            >
              <EntityBadge type={e.type} value={e.value} label={e.label} className="min-w-0 flex-1" />
              <div className="w-16 shrink-0">
                <ConfidenceMeter value={Math.round(e.confidence)} size="sm" showLabel={false} />
              </div>
            </button>
          </li>
        ))}
        {data && data.entities.length === 0 && !isLoading && (
          <li className="py-8 text-center text-sm text-muted">No entities yet.</li>
        )}
      </ul>
    </div>
  );
}
