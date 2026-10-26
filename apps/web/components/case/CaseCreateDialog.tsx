"use client";

import * as Checkbox from "@radix-ui/react-checkbox";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Check, ShieldAlert } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input, Textarea } from "@/components/ui/input";
import { Label } from "@/components/ui/primitives";
import { ApiError, api } from "@/lib/api";
import { cn } from "@/lib/utils";

const AUP_VERSION = "1.0";
const AUP_TEXT =
  "I confirm this investigation uses only lawful, publicly available information; I will not use Lighthouse for harassment, stalking, unauthorized access, or to obtain private/login-gated data; and I am authorized to investigate the named scope.";

const MIN_LEGAL_BASIS = 10;

export function CaseCreateDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const router = useRouter();
  const queryClient = useQueryClient();

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [legalBasis, setLegalBasis] = useState("");
  const [aupAccepted, setAupAccepted] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Reset form whenever the dialog is (re)opened.
  useEffect(() => {
    if (open) {
      setName("");
      setDescription("");
      setLegalBasis("");
      setAupAccepted(false);
      setError(null);
    }
  }, [open]);

  const createMutation = useMutation({
    mutationFn: () =>
      api.cases.create({
        name: name.trim(),
        description: description.trim() || undefined,
        legal_basis: legalBasis.trim(),
        aup_accepted: true,
        aup_version: AUP_VERSION,
      }),
    onSuccess: (created) => {
      queryClient.invalidateQueries({ queryKey: ["cases"] });
      toast.success("Case created.");
      onOpenChange(false);
      router.push(`/cases/${created.id}/graph`);
    },
    onError: (e) => {
      setError(e instanceof ApiError ? e.message : "Could not create case. Please try again.");
    },
  });

  const legalBasisOk = legalBasis.trim().length >= MIN_LEGAL_BASIS;
  const canSubmit = name.trim().length > 0 && legalBasisOk && aupAccepted && !createMutation.isPending;

  function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (!canSubmit) return;
    createMutation.mutate();
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>New investigation</DialogTitle>
          <DialogDescription>
            Cases scope all collection. Document your authorization before you begin.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={onSubmit} className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="case-name">Name</Label>
            <Input
              id="case-name"
              required
              autoFocus
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Acme Corp exposure review"
              disabled={createMutation.isPending}
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="case-description">Description</Label>
            <Textarea
              id="case-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Optional summary of the investigation."
              className="min-h-[64px]"
              disabled={createMutation.isPending}
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="case-legal-basis">
              Legal basis / authorization <span className="text-danger">*</span>
            </Label>
            <Textarea
              id="case-legal-basis"
              required
              value={legalBasis}
              onChange={(e) => setLegalBasis(e.target.value)}
              placeholder="Describe your authorization and scope for this investigation (engagement #, client, mandate)…"
              className="min-h-[72px]"
              disabled={createMutation.isPending}
              aria-invalid={legalBasis.length > 0 && !legalBasisOk}
            />
            <p className={cn("text-xs", legalBasisOk ? "text-muted" : "text-muted")}>
              {legalBasis.trim().length}/{MIN_LEGAL_BASIS} minimum characters.
            </p>
          </div>

          {/* Acceptable-Use Policy gate */}
          <div className="space-y-2 rounded-md border border-warning/40 bg-warning/5 p-3">
            <div className="flex items-center gap-2 text-sm font-medium text-text">
              <ShieldAlert size={16} className="text-warning" />
              Acceptable-Use Policy
            </div>
            <div className="max-h-28 overflow-y-auto rounded-md border border-border bg-bg/60 p-3 text-xs leading-relaxed text-muted">
              {AUP_TEXT}
            </div>
            <label className="flex cursor-pointer items-start gap-2.5 pt-1 text-sm text-text">
              <Checkbox.Root
                checked={aupAccepted}
                onCheckedChange={(v) => setAupAccepted(v === true)}
                disabled={createMutation.isPending}
                className={cn(
                  "mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded border border-border bg-bg/60 transition-colors",
                  "data-[state=checked]:border-accent data-[state=checked]:bg-accent data-[state=checked]:text-white",
                  "focus-visible:outline-none focus-visible:shadow-focus",
                )}
              >
                <Checkbox.Indicator>
                  <Check size={12} strokeWidth={3} />
                </Checkbox.Indicator>
              </Checkbox.Root>
              <span>I have read and accept the Acceptable-Use Policy (v{AUP_VERSION}).</span>
            </label>
          </div>

          {error && (
            <p className="rounded-md border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger">
              {error}
            </p>
          )}

          <DialogFooter>
            <Button
              type="button"
              variant="ghost"
              onClick={() => onOpenChange(false)}
              disabled={createMutation.isPending}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={!canSubmit}>
              Create case
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
