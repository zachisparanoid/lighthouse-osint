"use client";

import * as Primitive from "@radix-ui/react-dropdown-menu";
import * as React from "react";

import { cn } from "@/lib/utils";

export const DropdownMenu = Primitive.Root;
export const DropdownMenuTrigger = Primitive.Trigger;
export const DropdownMenuGroup = Primitive.Group;

export const DropdownMenuContent = React.forwardRef<
  React.ElementRef<typeof Primitive.Content>,
  React.ComponentPropsWithoutRef<typeof Primitive.Content>
>(({ className, sideOffset = 6, ...props }, ref) => (
  <Primitive.Portal>
    <Primitive.Content
      ref={ref}
      sideOffset={sideOffset}
      className={cn(
        "z-50 min-w-[180px] overflow-hidden rounded-lg border border-border bg-raised p-1 shadow-glow data-[state=open]:animate-slide-up",
        className,
      )}
      {...props}
    />
  </Primitive.Portal>
));
DropdownMenuContent.displayName = "DropdownMenuContent";

export const DropdownMenuItem = React.forwardRef<
  React.ElementRef<typeof Primitive.Item>,
  React.ComponentPropsWithoutRef<typeof Primitive.Item> & { destructive?: boolean }
>(({ className, destructive, ...props }, ref) => (
  <Primitive.Item
    ref={ref}
    className={cn(
      "flex cursor-pointer select-none items-center gap-2 rounded-md px-2.5 py-1.5 text-sm outline-none transition-colors",
      "data-[highlighted]:bg-bg/80 data-[disabled]:pointer-events-none data-[disabled]:opacity-50",
      destructive ? "text-danger data-[highlighted]:text-danger" : "text-text",
      className,
    )}
    {...props}
  />
));
DropdownMenuItem.displayName = "DropdownMenuItem";

export function DropdownMenuLabel({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("px-2.5 py-1.5 text-xs font-medium text-muted", className)} {...props} />;
}
export function DropdownMenuSeparator({ className }: { className?: string }) {
  return <Primitive.Separator className={cn("-mx-1 my-1 h-px bg-border", className)} />;
}
