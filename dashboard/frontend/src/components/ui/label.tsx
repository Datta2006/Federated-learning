"use client";

import * as React from "react";
import * as LabelPrimitive from "@radix-ui/react-label";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";
import { useReducedMotion } from "@/components/motion/ReducedMotion";

const Label = React.forwardRef<
  React.ElementRef<typeof LabelPrimitive.Root>,
  React.ComponentProps<typeof LabelPrimitive.Root>
>(({ className, children, ...props }, ref) => {
  const reducedMotion = useReducedMotion();

  return (
    <LabelPrimitive.Root
      ref={ref}
      className={cn(
        "text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70",
        reducedMotion ? "" : "transition-colors duration-200",
        className
      )}
      {...props}
    >
      {children}
    </LabelPrimitive.Root>
  );
});

Label.displayName = LabelPrimitive.Root.displayName;

export { Label };