"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label, Spinner } from "@/components/ui/primitives";
import { ApiError, api, setAccessToken } from "@/lib/api";
import { useAuth } from "@/lib/store";
import type { AuthResponse } from "@/lib/types";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [totpCode, setTotpCode] = useState("");
  const [totpRequired, setTotpRequired] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setPending(true);
    try {
      const res = await api.auth.login(email, password, totpRequired ? totpCode : undefined);
      if ("totp_required" in res && res.totp_required) {
        setTotpRequired(true);
        setPending(false);
        return;
      }
      const auth = res as AuthResponse;
      setAccessToken(auth.access_token);
      useAuth.getState().setUser(auth.user);
      router.replace("/dashboard");
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        setError(err.message || "Invalid email or password.");
      } else {
        setError(err instanceof ApiError ? err.message : "Something went wrong. Please try again.");
      }
      setPending(false);
    }
  }

  return (
    <div className="space-y-5">
      <div className="space-y-1">
        <h2 className="text-lg font-semibold text-text">Sign in</h2>
        <p className="text-sm text-muted">Access your investigation workspace.</p>
      </div>

      <form onSubmit={onSubmit} className="space-y-4">
        <div className="space-y-1.5">
          <Label htmlFor="email">Email</Label>
          <Input
            id="email"
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@agency.example"
            disabled={pending || totpRequired}
          />
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="password">Password</Label>
          <Input
            id="password"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="••••••••"
            disabled={pending || totpRequired}
          />
        </div>

        {totpRequired && (
          <div className="space-y-1.5 animate-slide-up">
            <Label htmlFor="totp">Authentication code</Label>
            <Input
              id="totp"
              inputMode="numeric"
              autoComplete="one-time-code"
              pattern="[0-9]*"
              maxLength={6}
              required
              autoFocus
              value={totpCode}
              onChange={(e) => setTotpCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
              placeholder="000000"
              className="mono tracking-[0.3em]"
              disabled={pending}
            />
            <p className="text-xs text-muted">Enter the 6-digit code from your authenticator app.</p>
          </div>
        )}

        {error && (
          <p className="rounded-md border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger">
            {error}
          </p>
        )}

        <Button type="submit" className="w-full" disabled={pending}>
          {pending && <Spinner className="h-4 w-4" />}
          {totpRequired ? "Verify code" : "Sign in"}
        </Button>
      </form>

      <p className="text-center text-sm text-muted">
        No account?{" "}
        <Link href="/register" className="font-medium text-accent hover:underline">
          Create one
        </Link>
      </p>
    </div>
  );
}
