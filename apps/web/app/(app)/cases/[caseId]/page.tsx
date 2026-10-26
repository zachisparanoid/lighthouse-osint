"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { Spinner } from "@/components/ui/primitives";

export default function CaseIndexPage({ params }: { params: { caseId: string } }) {
  const router = useRouter();

  useEffect(() => {
    router.replace(`/cases/${params.caseId}/graph`);
  }, [router, params.caseId]);

  return (
    <div className="flex h-full items-center justify-center">
      <Spinner className="h-6 w-6 text-muted" />
    </div>
  );
}
