"use client";

import * as Primitive from "@radix-ui/react-tabs";
import * as React from "react";

import { cn } from "@/lib/utils";

export const Tabs = Primitive.Root;

export const TabsList = React.forwardRef<
  React.ElementRef<typeof Primitive.List>,
  React.ComponentPropsWithoutRef<typeof Primitive.List>
>(({ className, ...props }, ref) => (
  <Primitive.List ref={ref} className={cn("inline-flex items-center gap-1", className)} {...props} />
));
TabsList.displayName = "TabsList";

export const TabsTrigger = React.forwardRef<
  React.ElementRef<typeof Primitive.Trigger>,
  React.ComponentPropsWithoutRef<typeof Primitive.Trigger>
>(({ className, ...props }, ref) => (
  <Primitive.Trigger
    ref={ref}
    className={cn(
      "inline-flex items-center gap-2 rounded-md px-3 py-1.5 text-sm font-medium text-muted transition-colors",
      "hover:text-text data-[state=active]:bg-raised data-[state=active]:text-text",
      className,
    )}
    {...props}
  />
));
TabsTrigger.displayName = "TabsTrigger";

export const TabsContent = Primitive.Content;
