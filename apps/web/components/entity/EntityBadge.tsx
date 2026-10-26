"use client";

import { entityColor, entityIcon, entityIsMono } from "@/lib/theme";
import type { EntityType } from "@/lib/types";
import { cn } from "@/lib/utils";

export function EntityDot({ type, size = 8 }: { type: EntityType; size?: number }) {
  return (
    <span
      className="inline-block shrink-0 rounded-full"
      style={{ background: entityColor(type), width: size, height: size }}
    />
  );
}

export function EntityBadge({
  type,
  value,
  label,
  className,
  showIcon = true,
}: {
  type: EntityType;
  value?: string;
  label?: string | null;
  className?: string;
  showIcon?: boolean;
}) {
  const Icon = entityIcon(type);
  const color = entityColor(type);
  const mono = entityIsMono(type);
  const text = label || value || "";
  return (
    <span className={cn("inline-flex max-w-full items-center gap-1.5", className)}>
      {showIcon && (
        <span className="flex h-4 w-4 shrink-0 items-center justify-center" style={{ color }}>
          <Icon size={13} strokeWidth={2} />
        </span>
      )}
      <span className={cn("truncate", mono && "mono text-[13px]")}>{text}</span>
    </span>
  );
}
