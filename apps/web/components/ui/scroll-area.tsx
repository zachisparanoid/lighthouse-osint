"use client";

import * as Primitive from "@radix-ui/react-scroll-area";
import * as React from "react";

import { cn } from "@/lib/utils";

export const ScrollArea = React.forwardRef<
  React.ElementRef<typeof Primitive.Root>,
  React.ComponentPropsWithoutRef<typeof Primitive.Root>
>(({ className, children, ...props }, ref) => (
  <Primitive.Root ref={ref} className={cn("relative overflow-hidden", className)} {...props}>
    <Primitive.Viewport className="h-full w-full rounded-[inherit]">{children}</Primitive.Viewport>
    <Primitive.Scrollbar
      orientation="vertical"
      className="flex w-2 touch-none select-none p-0.5"
    >
      <Primitive.Thumb className="relative flex-1 rounded-full bg-border" />
    </Primitive.Scrollbar>
    <Primitive.Corner />
  </Primitive.Root>
));
ScrollArea.displayName = "ScrollArea";
