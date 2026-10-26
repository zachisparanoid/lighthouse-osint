"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { KeyRound, Lock, Plus, ShieldCheck, Trash2 } from "lucide-react";
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
  DialogTrigger,
} from "@/components/ui/dialog";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Badge,
  Card,
  CardContent,
  Label,
  Skeleton,
  Spinner,
} from "@/components/ui/primitives";
import { ApiError, api } from "@/lib/api";
import {
  KEY_SERVICE_LABELS,
  KEY_SERVICES,
  type ApiKey,
  type KeyService,
} from "@/lib/types";
import { relativeTime } from "@/lib/utils";

function validityBadge(isValid: boolean | null) {
  if (isValid === true) return <Badge variant="success">valid</Badge>;
  if (isValid === false) return <Badge variant="danger">invalid</Badge>;
  return <Badge variant="default">untested</Badge>;
}

function AddKeyDialog() {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [service, setService] = useState<KeyService>(KEY_SERVICES[0]);
  const [value, setValue] = useState("");
  const [label, setLabel] = useState("");
  const [scope, setScope] = useState<"user" | "case">("user");

  function reset() {
    setService(KEY_SERVICES[0]);
    setValue("");
    setLabel("");
    setScope("user");
  }

  const createMutation = useMutation({
    mutationFn: () =>
      api.keys.create({
        service,
        value: value.trim(),
        label: label.trim() || undefined,
        scope,
        // For "case" scope left blank we fall back to user scope server-side; keep simple.
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["keys"] });
      toast.success("Key added and encrypted at rest.");
      reset();
      setOpen(false);
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "Could not add key"),
  });

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        setOpen(o);
        if (!o) reset();
      }}
    >
      <DialogTrigger asChild>
        <Button size="sm">
          <Plus size={15} /> Add key
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Add API key</DialogTitle>
          <DialogDescription>
            Keys are encrypted at rest (Fernet) and never displayed in full.
          </DialogDescription>
        </DialogHeader>
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            if (!value.trim()) {
              toast.error("Enter the key value");
              return;
            }
            createMutation.mutate();
          }}
        >
          <div className="space-y-1.5">
            <Label>Service</Label>
            <Select value={service} onValueChange={(v) => setService(v as KeyService)}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {KEY_SERVICES.map((s) => (
                  <SelectItem key={s} value={s}>
                    {KEY_SERVICE_LABELS[s]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="key-value">API key</Label>
            <Input
              id="key-value"
              type="password"
              autoComplete="off"
              value={value}
              onChange={(e) => setValue(e.target.value)}
              placeholder="Paste your key…"
              className="mono"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="key-label">Label (optional)</Label>
            <Input
              id="key-label"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              placeholder="e.g. Personal Shodan key"
            />
          </div>
          <div className="space-y-1.5">
            <Label>Scope</Label>
            <Select value={scope} onValueChange={(v) => setScope(v as "user" | "case")}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="user">My account (all cases)</SelectItem>
                <SelectItem value="case">A specific case</SelectItem>
              </SelectContent>
            </Select>
            <p className="text-xs text-muted">
              Account-scoped keys apply across every case you can access.
            </p>
          </div>
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={createMutation.isPending}>
              {createMutation.isPending && <Spinner className="h-4 w-4" />}
              Add key
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function KeyRow({ apiKey }: { apiKey: ApiKey }) {
  const qc = useQueryClient();

  const testMutation = useMutation({
    mutationFn: () => api.keys.test(apiKey.id),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ["keys"] });
      if (res.is_valid) toast.success(res.message || "Key is valid");
      else toast.error(res.message || "Key is invalid");
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "Test failed"),
  });

  const removeMutation = useMutation({
    mutationFn: () => api.keys.remove(apiKey.id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["keys"] });
      toast.success("Key deleted");
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "Could not delete key"),
  });

  return (
    <div className="flex flex-wrap items-center gap-3 p-4">
      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md border border-border bg-raised text-muted">
        <KeyRound size={16} />
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-text">
            {KEY_SERVICE_LABELS[apiKey.service] ?? apiKey.service}
          </span>
          {validityBadge(apiKey.is_valid)}
          <Badge variant="outline" className="capitalize">
            {apiKey.owner_case_id ? "case" : "account"}
          </Badge>
        </div>
        <div className="mt-0.5 flex items-center gap-2 text-xs text-muted">
          {apiKey.label && <span className="truncate">{apiKey.label}</span>}
          <span className="mono">{apiKey.masked}</span>
        </div>
      </div>
      <span className="hidden text-xs text-muted sm:block">
        {apiKey.last_used_at ? `Used ${relativeTime(apiKey.last_used_at)}` : "Never used"}
      </span>
      <div className="flex items-center gap-2">
        <Button
          size="sm"
          variant="secondary"
          onClick={() => testMutation.mutate()}
          disabled={testMutation.isPending}
        >
          {testMutation.isPending ? <Spinner className="h-3.5 w-3.5" /> : <ShieldCheck size={14} />}
          Test
        </Button>
        <Button
          size="sm"
          variant="ghost"
          onClick={() => {
            if (window.confirm(`Delete the ${KEY_SERVICE_LABELS[apiKey.service] ?? apiKey.service} key?`))
              removeMutation.mutate();
          }}
          disabled={removeMutation.isPending}
          aria-label="Delete key"
        >
          <Trash2 size={14} />
        </Button>
      </div>
    </div>
  );
}

export default function KeysPage() {
  const { data: keys, isLoading, isError, error } = useQuery<ApiKey[]>({
    queryKey: ["keys"],
    queryFn: () => api.keys.list(),
  });

  const presentServices = new Set((keys ?? []).map((k) => k.service));

  return (
    <div className="mx-auto max-w-3xl space-y-6 p-6">
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-1">
          <h1 className="text-lg font-semibold text-text">API keys (BYOK)</h1>
          <p className="max-w-xl text-sm text-muted">
            Bring your own keys to unlock keyed collectors. Keys are encrypted at rest with Fernet and
            are never shown in full — they power the Shodan, Have I Been Pwned, and OpenCorporates modules.
          </p>
        </div>
        <AddKeyDialog />
      </div>

      {/* Per-service status summary */}
      <div className="grid gap-3 sm:grid-cols-3">
        {KEY_SERVICES.map((s) => {
          const present = presentServices.has(s);
          return (
            <Card key={s}>
              <CardContent className="flex items-center gap-3 p-3">
                <div
                  className={
                    present
                      ? "flex h-8 w-8 items-center justify-center rounded-md border border-success/40 bg-success/10 text-success"
                      : "flex h-8 w-8 items-center justify-center rounded-md border border-border bg-raised text-muted"
                  }
                >
                  {present ? <ShieldCheck size={15} /> : <Lock size={15} />}
                </div>
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium text-text">{KEY_SERVICE_LABELS[s]}</p>
                  <p className="text-xs text-muted">{present ? "Key present" : "No key"}</p>
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      {/* Key list */}
      <Card>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="space-y-2 p-4">
              {Array.from({ length: 3 }).map((_, i) => (
                <Skeleton key={i} className="h-16 w-full" />
              ))}
            </div>
          ) : isError ? (
            <EmptyState
              icon={KeyRound}
              title="Couldn’t load keys"
              description={error instanceof ApiError ? error.message : "Please try again."}
            />
          ) : !keys || keys.length === 0 ? (
            <EmptyState
              icon={KeyRound}
              title="No keys yet"
              description="Add a key to enable keyed collectors like Shodan or Have I Been Pwned."
            />
          ) : (
            <div className="divide-y divide-border">
              {keys.map((k) => (
                <KeyRow key={k.id} apiKey={k} />
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
