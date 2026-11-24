"use client";

import * as React from "react";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";
import { useReducedMotion } from "@/components/motion/ReducedMotion";

export interface DataRowProps {
  label: React.ReactNode;
  value: React.ReactNode;
  mono?: boolean;
  index?: number;
}

export function DataRow({
  label,
  value,
  mono = true,
  index = 0,
}: DataRowProps) {
  const reducedMotion = useReducedMotion();
  const staggerDelay = index * 30;

  return (
    <motion.div
      initial={{ opacity: reducedMotion ? 0 : 0, x: reducedMotion ? 0 : -20 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{
        type: reducedMotion ? "tween" : "spring",
        damping: 1.0,
        stiffness: 200,
        duration: reducedMotion ? 0.1 : 0.3,
        delay: reducedMotion ? 0 : staggerDelay / 1000,
      }}
      className="data-row"
    >
      <span className="data-key">{label}</span>
      <span className={mono ? "data-value" : "text-right text-ink-200"}> {value}</span>
    </motion.div>
  );
}