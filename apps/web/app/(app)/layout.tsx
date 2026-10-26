"use client";

import { Search } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { CommandPalette } from "@/components/CommandPalette";
import { Sidebar } from "@/components/Sidebar";
import { Kbd, Spinner } from "@/components/ui/primitives";
import { TooltipProvider } from "@/components/ui/tooltip";
import { api, setAccessToken } from "@/lib/api";
import { useAuth, useUi } from "@/lib/store";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const user = useAuth((s) => s.user);
  const ready = useAuth((s) => s.ready);
  const setUser = useAuth((s) => s.setUser);
  const setReady = useAuth((s) => s.setReady);
  const setCmdkOpen = useUi((s) => s.setCmdkOpen);

  // Session restore / auth guard.
  useEffect(() => {
    let cancelled = false;
    if (useAuth.getState().user) {
      setReady(true);
      return;
    }
    (async () => {
      try {
        const res = await api.auth.refresh();
        if (cancelled) return;
        setAccessToken(res.access_token);
        setUser(res.user);
      } catch {
        if (cancelled) return;
        router.replace("/login");
      } finally {
        if (!cancelled) setReady(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [router, setReady, setUser]);

  // Global keyboard shortcuts: ⌘K / Ctrl+K and "/" to open the command palette.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setCmdkOpen(true);
        return;
      }
      if (e.key === "/") {
        const target = e.target as HTMLElement | null;
        const tag = target?.tagName;
        const typing =
          tag === "INPUT" ||
          tag === "TEXTAREA" ||
          tag === "SELECT" ||
          target?.isContentEditable;
        if (!typing) {
          e.preventDefault();
          setCmdkOpen(true);
        }
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [setCmdkOpen]);

  if (!ready) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Spinner className="h-6 w-6 text-muted" />
      </div>
    );
  }

  if (!user) {
    // Ready but unauthenticated — redirect is in flight.
    return null;
  }

  return (
    <TooltipProvider delayDuration={200}>
      <div className="flex h-screen overflow-hidden">
        <Sidebar />

        <div className="flex min-w-0 flex-1 flex-col">
          {/* Top bar */}
          <header className="flex h-14 shrink-0 items-center gap-3 border-b border-border px-6">
            <button
              type="button"
              onClick={() => setCmdkOpen(true)}
              className="group flex h-9 w-full max-w-md items-center gap-2 rounded-md border border-border bg-bg/60 px-3 text-sm text-muted transition-colors hover:border-border hover:bg-raised/40 focus-visible:outline-none focus-visible:shadow-focus"
            >
              <Search size={15} className="shrink-0" />
              <span className="flex-1 text-left">Search…</span>
              <span className="flex items-center gap-1">
                <Kbd>⌘</Kbd>
                <Kbd>K</Kbd>
              </span>
            </button>
            <span className="hidden items-center gap-1.5 text-xs text-muted sm:flex">
              <span>or press</span>
              <Kbd>/</Kbd>
            </span>
          </header>

          {/* Content */}
          <main className="flex-1 overflow-auto">{children}</main>
        </div>
      </div>

      <CommandPalette />
    </TooltipProvider>
  );
}
