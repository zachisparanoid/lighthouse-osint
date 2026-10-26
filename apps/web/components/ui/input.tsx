import * as React from "react";

import { cn } from "@/lib/utils";

export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, type, ...props }, ref) => (
    <input
      ref={ref}
      type={type}
      className={cn(
        "h-9 w-full rounded-md border border-border bg-bg/60 px-3 text-sm text-text placeholder:text-muted/70",
        "transition-shadow focus-visible:outline-none focus-visible:shadow-focus disabled:opacity-50",
        className,
      )}
      {...props}
    />
  ),
);
Input.displayName = "Input";

export const Textarea = React.forwardRef<
  HTMLTextAreaElement,
  React.TextareaHTMLAttributes<HTMLTextAreaElement>
>(({ className, ...props }, ref) => (
  <textarea
    ref={ref}
    className={cn(
      "min-h-[80px] w-full rounded-md border border-border bg-bg/60 px-3 py-2 text-sm text-text placeholder:text-muted/70",
      "transition-shadow focus-visible:outline-none focus-visible:shadow-focus disabled:opacity-50",
      className,
    )}
    {...props}
  />
));
Textarea.displayName = "Textarea";
