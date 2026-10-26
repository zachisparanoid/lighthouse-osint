"use client";

import * as Primitive from "@radix-ui/react-tooltip";
import * as React from "react";

import { cn } from "@/lib/utils";

export const TooltipProvider = Primitive.Provider;
export const Tooltip = Primitive.Root;
export const TooltipTrigger = Primitive.Trigger;

export const TooltipContent = React.forwardRef<
  React.ElementRef<typeof Primitive.Content>,
  React.ComponentPropsWithoutRef<typeof Primitive.Content>
>(({ className, sideOffset = 6, ...props }, ref) => (
  <Primitive.Portal>
    <Primitive.Content
      ref={ref}
      sideOffset={sideOffset}
      className={cn(
        "z-50 rounded-md border border-border bg-raised px-2.5 py-1.5 text-xs text-text shadow-glow",
        "data-[state=delayed-open]:animate-fade-in",
        className,
      )}
      {...props}
    />
  </Primitive.Portal>
));
TooltipContent.displayName = "TooltipContent";

/** Convenience wrapper for the common single-trigger case. */
export function SimpleTooltip({ label, children }: { label: React.ReactNode; children: React.ReactNode }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>{children}</TooltipTrigger>
      <TooltipContent>{label}</TooltipContent>
    </Tooltip>
  );
}
