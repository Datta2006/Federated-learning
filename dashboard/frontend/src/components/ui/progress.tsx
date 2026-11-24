"use client";

import * as React from "react";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";
import { useReducedMotion } from "@/components/motion/ReducedMotion";

export interface ProgressProps {
  value: number;
  max?: number;
  className?: string;
}

export function Progress({ value, max = 100, className }: ProgressProps) {
  const reducedMotion = useReducedMotion();
  const percent = Math.min(Math.max(value, 0), max) / max * 100;

  return (
    <motion.div
      className={cn("relative", className)}
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: reducedMotion ? 0.15 : 0.3 }}
    >
      <div className="h-2 rounded-full bg-muted overflow-hidden">
        <motion.div
          className={`h-full rounded-full ${percent < 100 ? "bg-airfed-500" : "bg-ok-500"}`}
          animate={{ width: `${percent}%` }}
          transition={{
            type: reducedMotion ? "tween" : "spring",
            damping: 1.0,
            stiffness: reducedMotion ? 150 : 200,
            duration: reducedMotion ? 0.5 : 0.8,
          }}
        />
      </div>
      {value > 0 && (
        <span
          className={cn(
            "absolute right-1 top-1/2 -translate-x-1/2 text-xs font-medium text-foreground",
            { hidden: percent === 0 }
          )}
        >
          {value}
        </span>
      )}
    </motion.div>
  );
}