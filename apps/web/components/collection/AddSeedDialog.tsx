"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
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
import { Input } from "@/components/ui/input";
import { Label, Spinner } from "@/components/ui/primitives";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { api, ApiError } from "@/lib/api";
import { useUi } from "@/lib/store";
import { entityLabel } from "@/lib/theme";
import { ENTITY_TYPES, type EntityType } from "@/lib/types";

const PLACEHOLDERS: Partial<Record<EntityType, string>> = {
  domain: "example.com",
  ip: "203.0.113.10",
  email: "name@example.com",
  username: "jdoe",
  person: "Jane Doe",
  organization: "Acme Corp",
  phone: "+1 555 0100",
  url: "https://example.com/path",
};

export function AddSeedDialog({
  caseId,
  open,
  onOpenChange,
}: {
  caseId: string;
  open: boolean;
  onOpenChange: (o: boolean) => void;
}) {
  const qc = useQueryClient();
  const [type, setType] = useState<EntityType>("domain");
  const [value, setValue] = useState("");
  const [runCollectors, setRunCollectors] = useState(true);
  const [autoexpand, setAutoexpand] = useState(false);
  const [pending, setPending] = useState(false);

  const reset = () => {
    setValue("");
    setRunCollectors(true);
    setAutoexpand(false);
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!value.trim()) return;
    setPending(true);
    try {
      const created = await api.entities.create(caseId, {
        type,
        value: value.trim(),
        run_collectors: runCollectors,
        autoexpand,
      });
      toast.success(`Added ${entityLabel(type)}`);
      void qc.invalidateQueries({ queryKey: ["graph", caseId] });
      void qc.invalidateQueries({ queryKey: ["entities", caseId] });
      void qc.invalidateQueries({ queryKey: ["jobs", caseId] });
      useUi.getState().setSelectedEntityId(created.id);
      useUi.getState().setFocusEntityId(created.id);
      reset();
      onOpenChange(false);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Failed to add seed");
    } finally {
      setPending(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Add seed entity</DialogTitle>
          <DialogDescription>
            Seed the investigation with a starting point. Only run collection on targets you are
            authorized to investigate.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={submit} className="space-y-4">
          <div className="grid grid-cols-[150px_1fr] gap-3">
            <div className="space-y-1.5">
              <Label>Type</Label>
              <Select value={type} onValueChange={(v) => setType(v as EntityType)}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {ENTITY_TYPES.map((t) => (
                    <SelectItem key={t} value={t}>
                      {entityLabel(t)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="seed-value">Value</Label>
              <Input
                id="seed-value"
                autoFocus
                value={value}
                onChange={(e) => setValue(e.target.value)}
                placeholder={PLACEHOLDERS[type] ?? "Enter a value"}
              />
            </div>
          </div>

          <div className="space-y-2 rounded-md border border-border bg-bg/40 p-3">
            <label className="flex items-center justify-between gap-3">
              <span className="text-sm text-text">
                Run collectors now
                <span className="block text-xs text-muted">Queue compatible free collectors.</span>
              </span>
              <Switch checked={runCollectors} onCheckedChange={setRunCollectors} />
            </label>
            <label className="flex items-center justify-between gap-3">
              <span className="text-sm text-text">
                Auto-expand
                <span className="block text-xs text-muted">
                  Recursively follow results within budget.
                </span>
              </span>
              <Switch checked={autoexpand} onCheckedChange={setAutoexpand} />
            </label>
          </div>

          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={pending || !value.trim()}>
              {pending && <Spinner className="h-4 w-4" />}
              Add seed
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
