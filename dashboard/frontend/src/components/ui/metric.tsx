"use client";

import * as React from "react";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";
import { useReducedMotion } from "@/components/motion/ReducedMotion";

const toneStyle: Record<
  "accent" | "ok" | "warn" | "bad" | "info" | "neutral",
  { text: string; border: string; bg: string }
> = {
  accent: {
    text: "text-accent-text",
    border: "border-accent/35",
    bg: "bg-accent-dim",
  },
  ok: {
    text: "text-ok-text",
    border: "border-ok/30",
    bg: "bg-ok-soft",
  },
  warn: {
    text: "text-warn-text",
    border: "border-warn/30",
    bg: "bg-warn-soft",
  },
  bad: {
    text: "text-bad-text",
    border: "border-bad/35",
    bg: "bg-bad-soft",
  },
  info: {
    text: "text-info-text",
    border: "border-info/30",
    bg: "bg-info-soft",
  },
  neutral: {
    text: "text-ink-400",
    border: "border-line2",
    bg: "bg-raise",
  },
};

export interface MetricProps {
  label: React.ReactNode;
  value: React.ReactNode;
  hint?: React.ReactNode;
  tone?: "accent" | "ok" | "warn" | "bad" | "info" | "neutral";
  className?: string;
}

export function Metric({
  label,
  value,
  hint,
  tone = "neutral",
  className,
}: MetricProps) {
  const reducedMotion = useReducedMotion();

  const style = toneStyle[tone];

  return (
    <motion.div
      initial={{ opacity: reducedMotion ? 1 : 0, y: reducedMotion ? 0 : 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{
        type: reducedMotion ? "tween" : "spring",
        damping: 1.0,
        stiffness: 200,
        duration: reducedMotion ? 0.1 : 0.3,
      }}
      className={cn(`border-line/80 px-4 py-3`, className)}>
      <div className="label">{label}</div>
      <div className={cn(
        "mt-2 flex items-baseline gap-2",
        style.text
      )}>
        <motion.span
          initial={reducedMotion ? undefined : { scale: 0.9 }}
          animate={{ scale: 1 }}
          transition={{
            type: reducedMotion ? "tween" : "spring",
            damping: 1.0,
            stiffness: 200,
            duration: reducedMotion ? 0 : 0.8,
          }}
          className="metric"
        >
          {value}
        </motion.span>
      </div>
      {hint ? (
        <div className="mt-1.5 truncate text-[11px] text-ink-500">{hint}</div>
      ) : null}
    </motion.div>
  );
}