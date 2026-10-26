"use client";

import * as Primitive from "@radix-ui/react-select";
import { Check, ChevronDown } from "lucide-react";
import * as React from "react";

import { cn } from "@/lib/utils";

export const Select = Primitive.Root;
export const SelectValue = Primitive.Value;
export const SelectGroup = Primitive.Group;

export const SelectTrigger = React.forwardRef<
  React.ElementRef<typeof Primitive.Trigger>,
  React.ComponentPropsWithoutRef<typeof Primitive.Trigger>
>(({ className, children, ...props }, ref) => (
  <Primitive.Trigger
    ref={ref}
    className={cn(
      "flex h-9 w-full items-center justify-between gap-2 rounded-md border border-border bg-bg/60 px-3 text-sm text-text",
      "focus-visible:outline-none focus-visible:shadow-focus data-[placeholder]:text-muted",
      className,
    )}
    {...props}
  >
    {children}
    <Primitive.Icon asChild>
      <ChevronDown size={14} className="text-muted" />
    </Primitive.Icon>
  </Primitive.Trigger>
));
SelectTrigger.displayName = "SelectTrigger";

export const SelectContent = React.forwardRef<
  React.ElementRef<typeof Primitive.Content>,
  React.ComponentPropsWithoutRef<typeof Primitive.Content>
>(({ className, children, position = "popper", ...props }, ref) => (
  <Primitive.Portal>
    <Primitive.Content
      ref={ref}
      position={position}
      className={cn(
        "z-50 max-h-72 min-w-[8rem] overflow-hidden rounded-lg border border-border bg-raised shadow-glow",
        position === "popper" && "translate-y-1",
        className,
      )}
      {...props}
    >
      <Primitive.Viewport className="p-1">{children}</Primitive.Viewport>
    </Primitive.Content>
  </Primitive.Portal>
));
SelectContent.displayName = "SelectContent";

export const SelectItem = React.forwardRef<
  React.ElementRef<typeof Primitive.Item>,
  React.ComponentPropsWithoutRef<typeof Primitive.Item>
>(({ className, children, ...props }, ref) => (
  <Primitive.Item
    ref={ref}
    className={cn(
      "relative flex cursor-pointer select-none items-center rounded-md py-1.5 pl-7 pr-2 text-sm text-text outline-none",
      "data-[highlighted]:bg-bg/80 data-[disabled]:opacity-50",
      className,
    )}
    {...props}
  >
    <span className="absolute left-2 flex h-3.5 w-3.5 items-center justify-center">
      <Primitive.ItemIndicator>
        <Check size={12} className="text-accent" />
      </Primitive.ItemIndicator>
    </span>
    <Primitive.ItemText>{children}</Primitive.ItemText>
  </Primitive.Item>
));
SelectItem.displayName = "SelectItem";
