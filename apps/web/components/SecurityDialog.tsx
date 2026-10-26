"use client";

import { Check, Copy, ShieldCheck } from "lucide-react";
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
import { Badge, Label, Separator, Spinner } from "@/components/ui/primitives";
import { ApiError, api } from "@/lib/api";
import { useAuth } from "@/lib/store";

export function SecurityDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const user = useAuth((s) => s.user);
  const setUser = useAuth((s) => s.setUser);
  const enabled = !!user?.totp_enabled;

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        onOpenChange(o);
      }}
    >
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Two-factor authentication</DialogTitle>
          <DialogDescription>
            Add a time-based one-time password (TOTP) to protect your account.
          </DialogDescription>
        </DialogHeader>

        {enabled ? (
          <DisableFlow
            onDone={() => {
              if (user) setUser({ ...user, totp_enabled: false });
              onOpenChange(false);
            }}
          />
        ) : (
          <EnableFlow
            onDone={() => {
              if (user) setUser({ ...user, totp_enabled: true });
              onOpenChange(false);
            }}
          />
        )}
      </DialogContent>
    </Dialog>
  );
}

function EnableFlow({ onDone }: { onDone: () => void }) {
  const [secret, setSecret] = useState<string | null>(null);
  const [uri, setUri] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [setupPending, setSetupPending] = useState(false);
  const [enablePending, setEnablePending] = useState(false);
  const [copied, setCopied] = useState(false);

  async function startSetup() {
    setSetupPending(true);
    try {
      const res = await api.auth.totpSetup();
      setSecret(res.secret);
      setUri(res.provisioning_uri);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Could not start 2FA setup.");
    } finally {
      setSetupPending(false);
    }
  }

  async function enable() {
    setEnablePending(true);
    try {
      await api.auth.totpEnable(code);
      toast.success("Two-factor authentication enabled.");
      onDone();
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Could not enable 2FA. Check the code.");
    } finally {
      setEnablePending(false);
    }
  }

  function copySecret() {
    if (!secret) return;
    navigator.clipboard?.writeText(secret).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  }

  if (!secret) {
    return (
      <div className="space-y-4">
        <div className="flex items-start gap-3 rounded-md border border-border bg-raised/40 p-3">
          <ShieldCheck size={18} className="mt-0.5 shrink-0 text-muted" />
          <p className="text-sm text-muted">
            You will be asked for a 6-digit code from your authenticator app each time you sign in.
          </p>
        </div>
        <DialogFooter>
          <Button onClick={startSetup} disabled={setupPending}>
            {setupPending && <Spinner className="h-4 w-4" />}
            Enable 2FA
          </Button>
        </DialogFooter>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <Label>Secret key</Label>
        <div className="flex items-center gap-2">
          <code className="mono flex-1 truncate rounded-md border border-border bg-bg/60 px-3 py-2 text-sm text-text">
            {secret}
          </code>
          <Button variant="secondary" size="icon" onClick={copySecret} aria-label="Copy secret">
            {copied ? <Check size={16} className="text-success" /> : <Copy size={16} />}
          </Button>
        </div>
      </div>

      {uri && (
        <div className="space-y-2">
          <Label>Provisioning URI</Label>
          <code className="mono block break-all rounded-md border border-border bg-bg/60 px-3 py-2 text-xs text-muted">
            {uri}
          </code>
          <p className="text-xs text-muted">
            Scan this in an authenticator app (Google Authenticator, 1Password, Authy), or add the
            secret key manually.
          </p>
        </div>
      )}

      <Separator />

      <div className="space-y-1.5">
        <Label htmlFor="enable-code">Verification code</Label>
        <Input
          id="enable-code"
          inputMode="numeric"
          pattern="[0-9]*"
          maxLength={6}
          autoFocus
          value={code}
          onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
          placeholder="000000"
          className="mono tracking-[0.3em]"
        />
      </div>

      <DialogFooter>
        <Button onClick={enable} disabled={enablePending || code.length !== 6}>
          {enablePending && <Spinner className="h-4 w-4" />}
          Confirm &amp; enable
        </Button>
      </DialogFooter>
    </div>
  );
}

function DisableFlow({ onDone }: { onDone: () => void }) {
  const [code, setCode] = useState("");
  const [pending, setPending] = useState(false);

  async function disable() {
    setPending(true);
    try {
      await api.auth.totpDisable(code);
      toast.success("Two-factor authentication disabled.");
      onDone();
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Could not disable 2FA. Check the code.");
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between rounded-md border border-success/40 bg-success/10 px-3 py-2">
        <span className="text-sm text-success">2FA is currently enabled.</span>
        <Badge variant="success">Active</Badge>
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="disable-code">Enter a current code to disable</Label>
        <Input
          id="disable-code"
          inputMode="numeric"
          pattern="[0-9]*"
          maxLength={6}
          autoFocus
          value={code}
          onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
          placeholder="000000"
          className="mono tracking-[0.3em]"
        />
      </div>

      <DialogFooter>
        <Button variant="danger" onClick={disable} disabled={pending || code.length !== 6}>
          {pending && <Spinner className="h-4 w-4" />}
          Disable 2FA
        </Button>
      </DialogFooter>
    </div>
  );
}
