"use client";

import {
  FolderSearch,
  LayoutDashboard,
  type LucideIcon,
  Radar,
  ScrollText,
  Settings,
  ShieldCheck,
  LogOut,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { SecurityDialog } from "@/components/SecurityDialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Badge } from "@/components/ui/primitives";
import { ApiError, api, setAccessToken } from "@/lib/api";
import { useAuth } from "@/lib/store";
import { cn, initials } from "@/lib/utils";

interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
}

const PRIMARY_NAV: NavItem[] = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/cases", label: "Cases", icon: FolderSearch },
];

function NavLink({ item, active }: { item: NavItem; active: boolean }) {
  const Icon = item.icon;
  return (
    <Link
      href={item.href}
      aria-current={active ? "page" : undefined}
      className={cn(
        "flex items-center gap-2.5 rounded-md px-2.5 py-2 text-sm font-medium transition-colors",
        active ? "bg-accent/10 text-accent" : "text-muted hover:bg-raised/60 hover:text-text",
      )}
    >
      <Icon size={16} className="shrink-0" />
      {item.label}
    </Link>
  );
}

export function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const user = useAuth((s) => s.user);
  const setUser = useAuth((s) => s.setUser);
  const [securityOpen, setSecurityOpen] = useState(false);

  const isAdmin = user?.role === "admin";

  function isActive(href: string) {
    return pathname === href || pathname.startsWith(`${href}/`);
  }

  async function signOut() {
    try {
      await api.auth.logout();
    } catch (e) {
      // Even if the server call fails, clear local session.
      if (e instanceof ApiError) {
        /* ignore */
      }
    } finally {
      setAccessToken(null);
      setUser(null);
      router.replace("/login");
    }
  }

  return (
    <aside className="flex w-60 shrink-0 flex-col border-r border-border bg-surface">
      {/* Logo */}
      <div className="flex h-14 items-center gap-2.5 px-4">
        <div className="flex h-8 w-8 items-center justify-center rounded-md border border-accent/40 bg-accent/10 text-accent">
          <Radar size={18} />
        </div>
        <span className="text-sm font-semibold text-text">Lighthouse</span>
      </div>

      {/* Primary nav */}
      <nav className="flex flex-col gap-0.5 px-2 py-2">
        {PRIMARY_NAV.map((item) => (
          <NavLink key={item.href} item={item} active={isActive(item.href)} />
        ))}
      </nav>

      <div className="mx-3 my-1 h-px bg-border" />

      <nav className="flex flex-col gap-0.5 px-2 py-2">
        <NavLink
          item={{ href: "/settings/keys", label: "Settings", icon: Settings }}
          active={isActive("/settings")}
        />
        {isAdmin && (
          <NavLink
            item={{ href: "/admin/audit", label: "Audit", icon: ScrollText }}
            active={isActive("/admin")}
          />
        )}
      </nav>

      <div className="flex-1" />

      {/* User menu */}
      <div className="border-t border-border p-2">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button
              className="flex w-full items-center gap-2.5 rounded-md px-2 py-2 text-left transition-colors hover:bg-raised/60 focus-visible:outline-none focus-visible:shadow-focus"
              aria-label="Account menu"
            >
              <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-border bg-raised text-xs font-semibold text-text">
                {user ? initials(user.email) : "?"}
              </span>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm text-text">{user?.email ?? "—"}</span>
                {user && (
                  <span className="block text-xs capitalize text-muted">{user.role}</span>
                )}
              </span>
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" side="top" className="w-[224px]">
            {user && (
              <>
                <div className="flex items-center justify-between px-2.5 py-1.5">
                  <span className="truncate text-xs text-muted">{user.email}</span>
                  <Badge variant={user.role === "admin" ? "accent" : "default"} className="capitalize">
                    {user.role}
                  </Badge>
                </div>
                <DropdownMenuSeparator />
              </>
            )}
            <DropdownMenuItem onSelect={() => setSecurityOpen(true)}>
              <ShieldCheck size={15} />
              Security (2FA)
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem destructive onSelect={() => void signOut()}>
              <LogOut size={15} />
              Sign out
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      <SecurityDialog open={securityOpen} onOpenChange={setSecurityOpen} />
    </aside>
  );
}
