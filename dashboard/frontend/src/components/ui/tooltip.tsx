"use client";

import * as React from "react";
import { cn } from "@/lib/utils";

interface TooltipProviderProps {
  children: React.ReactNode;
  delayDuration?: number;
}

export const TooltipProvider = React.forwardRef<
  HTMLDivElement,
  TooltipProviderProps
>(({ delayDuration = 700, children }, ref) => (
  <div
    ref={ref}
    data-tooltip-provider
  >
    {children}
  </div>
));
TooltipProvider.displayName = "TooltipProvider";

interface TooltipContentProps {
  children: React.ReactNode;
  className?: string;
  side?: "top" | "right" | "bottom" | "left";
  align?: "start" | "center" | "end";
}

export function TooltipContent({ children, className, side = "top", align = "center" }: TooltipContentProps) {
  return (
    <div
      className={cn(
        "z-50 w-auto rounded-md bg-popover px-3 py-1.5 text-sm text-popover-foreground shadow-md",
        className
      )}
    >
      {children}
    </div>
  );
}

interface TooltipProps {
  children: React.ReactNode;
  delayDuration?: number;
}

export function Tooltip({ children, delayDuration = 700 }: TooltipProps) {
  return null;
}

export const TooltipTrigger = React.forwardRef<
  HTMLButtonElement,
  { children: React.ReactNode; asChild?: boolean; disabled?: boolean } & React.HTMLAttributes<HTMLButtonElement>
>((props, ref) => {
  const { children, asChild = false, disabled, ...rest } = props;
  
  if (asChild && React.isValidElement(children)) {
    const childProps = {
      ...rest,
      ref,
      disabled,
    };
    
    return React.cloneElement(children, childProps as Record<string, unknown>) as React.ReactElement;
  }

  return (
    <button ref={ref} disabled={disabled} {...rest}>
      {children}
    </button>
  );
});
TooltipTrigger.displayName = "TooltipTrigger";