"use client";

import { ReportBuilder } from "@/components/report/ReportBuilder";

export default function ReportPage() {
  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="border-b border-border px-4 py-3">
        <h1 className="text-sm font-semibold text-text">Report builder</h1>
        <p className="text-xs text-muted">
          Compose a cited, court-ready export of this investigation.
        </p>
      </div>
      <div className="min-h-0 flex-1 overflow-auto">
        <ReportBuilder />
      </div>
    </div>
  );
}
