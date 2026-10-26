"use client";

import { EntitiesTable } from "@/components/entity/EntitiesTable";

export default function EntitiesPage() {
  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="border-b border-border px-4 py-3">
        <h1 className="text-sm font-semibold text-text">Entities</h1>
        <p className="text-xs text-muted">
          Every value is cited — open a row to inspect its sources and provenance.
        </p>
      </div>
      <div className="min-h-0 flex-1">
        <EntitiesTable />
      </div>
    </div>
  );
}
