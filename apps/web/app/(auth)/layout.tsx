import { Radar } from "lucide-react";

import { Card } from "@/components/ui/primitives";

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center px-4 py-12">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex flex-col items-center gap-3 text-center">
          <div className="flex h-12 w-12 items-center justify-center rounded-lg border border-accent/40 bg-accent/10 text-accent shadow-glow">
            <Radar size={24} />
          </div>
          <div className="space-y-1">
            <h1 className="text-xl font-semibold text-text">Lighthouse</h1>
            <p className="text-sm text-muted">OSINT investigation console</p>
          </div>
        </div>
        <Card className="p-6">{children}</Card>
      </div>
    </div>
  );
}
