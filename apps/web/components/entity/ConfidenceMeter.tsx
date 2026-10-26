"use client";

import { confidenceColor } from "@/lib/utils";
import { cn } from "@/lib/utils";

export function ConfidenceMeter({
  value,
  size = "md",
  showLabel = true,
  className,
}: {
  value: number;
  size?: "sm" | "md";
  showLabel?: boolean;
  className?: string;
}) {
  const color = confidenceColor(value);
  return (
    <div className={cn("flex items-center gap-2", className)}>
      <div
        className={cn("relative w-full overflow-hidden rounded-full bg-bg", size === "sm" ? "h-1" : "h-1.5")}
      >
        <div
          className="absolute inset-y-0 left-0 rounded-full transition-[width] duration-300 ease-out"
          style={{ width: `${Math.max(0, Math.min(100, value))}%`, background: color }}
        />
      </div>
      {showLabel && (
        <span className="mono shrink-0 text-xs tabular-nums" style={{ color }}>
          {value}
        </span>
      )}
    </div>
  );
}
