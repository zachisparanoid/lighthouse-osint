"use client";

import * as Primitive from "@radix-ui/react-switch";
import * as React from "react";

import { cn } from "@/lib/utils";

export const Switch = React.forwardRef<
  React.ElementRef<typeof Primitive.Root>,
  React.ComponentPropsWithoutRef<typeof Primitive.Root>
>(({ className, ...props }, ref) => (
  <Primitive.Root
    ref={ref}
    className={cn(
      "peer inline-flex h-5 w-9 shrink-0 cursor-pointer items-center rounded-full border border-border transition-colors",
      "data-[state=checked]:bg-accent data-[state=unchecked]:bg-bg focus-visible:outline-none focus-visible:shadow-focus",
      className,
    )}
    {...props}
  >
    <Primitive.Thumb className="pointer-events-none block h-3.5 w-3.5 translate-x-0.5 rounded-full bg-text shadow transition-transform data-[state=checked]:translate-x-[18px]" />
  </Primitive.Root>
));
Switch.displayName = "Switch";
