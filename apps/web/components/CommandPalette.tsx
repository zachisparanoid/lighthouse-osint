"use client";

import { Command } from "cmdk";
import {
  FolderSearch,
  LayoutDashboard,
  Plus,
  ScrollText,
  Search,
  Settings,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import { useAuth, useUi } from "@/lib/store";
import { cn } from "@/lib/utils";

const itemClass = cn(
  "flex cursor-pointer items-center gap-2.5 rounded-md px-2.5 py-2 text-sm text-muted outline-none",
  "data-[selected=true]:bg-bg data-[selected=true]:text-text",
  "[&_svg]:shrink-0",
);

export function CommandPalette() {
  const open = useUi((s) => s.cmdkOpen);
  const setOpen = useUi((s) => s.setCmdkOpen);
  const isAdmin = useAuth((s) => s.user?.role === "admin");
  const router = useRouter();

  const { data: cases } = useQuery({
    queryKey: ["cases"],
    queryFn: api.cases.list,
    enabled: open,
  });

  function go(href: string) {
    setOpen(false);
    router.push(href);
  }

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center p-4 pt-[12vh]"
      role="presentation"
    >
      <button
        type="button"
        aria-label="Close command palette"
        className="absolute inset-0 bg-black/60 backdrop-blur-sm animate-fade-in"
        onClick={() => setOpen(false)}
      />
      <Command
        label="Command palette"
        className="relative z-10 w-full max-w-xl overflow-hidden rounded-lg border border-border bg-surface shadow-glow animate-slide-up"
        loop
      >
        <div className="flex items-center gap-2 border-b border-border px-3">
          <Search size={16} className="shrink-0 text-muted" />
          <Command.Input
            autoFocus
            placeholder="Search cases, navigate, or run an action…"
            className="h-11 w-full bg-transparent text-sm text-text placeholder:text-muted/70 focus:outline-none"
          />
        </div>

        <Command.List className="max-h-[60vh] overflow-y-auto p-2">
          <Command.Empty className="py-8 text-center text-sm text-muted">
            No results found.
          </Command.Empty>

          <Command.Group
            heading="Navigation"
            className="[&_[cmdk-group-heading]]:px-2.5 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-xs [&_[cmdk-group-heading]]:font-medium [&_[cmdk-group-heading]]:text-muted"
          >
            <Command.Item className={itemClass} onSelect={() => go("/dashboard")}>
              <LayoutDashboard size={16} />
              Dashboard
            </Command.Item>
            <Command.Item className={itemClass} onSelect={() => go("/cases")}>
              <FolderSearch size={16} />
              Cases
            </Command.Item>
            <Command.Item
              className={itemClass}
              keywords={["settings", "keys", "api"]}
              onSelect={() => go("/settings/keys")}
            >
              <Settings size={16} />
              Settings → Keys
            </Command.Item>
            {isAdmin && (
              <Command.Item
                className={itemClass}
                keywords={["admin", "audit", "log"]}
                onSelect={() => go("/admin/audit")}
              >
                <ScrollText size={16} />
                Admin → Audit
              </Command.Item>
            )}
          </Command.Group>

          <Command.Group
            heading="Actions"
            className="mt-1 [&_[cmdk-group-heading]]:px-2.5 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-xs [&_[cmdk-group-heading]]:font-medium [&_[cmdk-group-heading]]:text-muted"
          >
            <Command.Item
              className={itemClass}
              keywords={["new", "create", "case", "investigation"]}
              onSelect={() => go("/cases?new=1")}
            >
              <Plus size={16} />
              New case
            </Command.Item>
          </Command.Group>

          {cases && cases.length > 0 && (
            <Command.Group
              heading="Cases"
              className="mt-1 [&_[cmdk-group-heading]]:px-2.5 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-xs [&_[cmdk-group-heading]]:font-medium [&_[cmdk-group-heading]]:text-muted"
            >
              {cases.map((c) => (
                <Command.Item
                  key={c.id}
                  value={`case ${c.name} ${c.id}`}
                  className={itemClass}
                  onSelect={() => go(`/cases/${c.id}/graph`)}
                >
                  <FolderSearch size={16} />
                  <span className="truncate">{c.name}</span>
                </Command.Item>
              ))}
            </Command.Group>
          )}
        </Command.List>
      </Command>
    </div>
  );
}
