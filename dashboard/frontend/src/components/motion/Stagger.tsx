"use client";

import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useReducedMotion } from "./ReducedMotion";

export interface StaggerOptions {
  /** Delay per child in ms (default: 30ms for table rows, 60ms for others) */
  delay?: number;
  /** Base index to start from (default: 0) */
  startIndex?: number;
  /** Whether to respect reduced motion (default: true) */
  respectReducedMotion?: boolean;
}

export function useStagger(
  count: number,
  options: StaggerOptions = {}
) {
  const { delay = 30, startIndex = 0, respectReducedMotion = true } = options;
  const reducedMotion = respectReducedMotion ? useReducedMotion() : false;

  const [staggerOffsets, setStaggerOffsets] = useState<number[]>([]);

  useEffect(() => {
    if (reducedMotion) {
      setStaggerOffsets(
        Array.from({ length: count }, (_, i) => 0)
      );
      return;
    }

    const offsets = Array.from({ length: count }, (_, i) => {
      const index = startIndex + i;
      return index * delay;
    });

    setStaggerOffsets(offsets);
  }, [count, delay, startIndex, reducedMotion]);

  return staggerOffsets;
}

interface StaggerProps {
  children: React.ReactNode;
  /** Delay per child in ms (default: 60ms) */
  delay?: number;
  /** Initial animation state */
  initial?: any;
  /** Final animation state */
  animate?: any;
  /** Container className */
  className?: string;
  /** Component to render as container (default: div) */
  as?: React.ElementType;
}

/**
 * Stagger - Staggered entrance animation for a list of children
 * Each child animates in with a small delay from DESIGN.md specs (30ms for rows, 60ms default)
 */
export function Stagger({
  children,
  delay = 60,
  initial = { opacity: 0, y: 10 },
  animate = { opacity: 1, y: 0 },
  className = "",
  as: Component = "div",
}: StaggerProps) {
  const prefersReducedMotion = useReducedMotion();
  const childArray = Array.isArray(children) ? children : [children];
  
  const items = childArray.map((child, index) => {
    const transition = prefersReducedMotion
      ? { duration: 0.15 }
      : { type: "spring", damping: 1.0, response: 0.5, delay: index * delay / 1000 };

    return (
      <motion.div
        key={index}
        initial={prefersReducedMotion ? { opacity: 0 } as any : (initial as any)}
        animate={(animate as any)}
        transition={transition as any}
      >
        {child}
      </motion.div>
    );
  });

  return <Component className={className}>{items}</Component>;
}

interface StaggerItemProps {
  children: React.ReactNode;
  /** Index of this item in the stagger sequence */
  index: number;
  /** Delay per item in ms (default: 60ms) */
  delay?: number;
  /** Initial animation state */
  initial?: Record<string, unknown>;
  /** Final animation state */
  animate?: Record<string, unknown>;
  /** CSS className */
  className?: string;
}

/**
 * StaggerItem - Individual item with stagger delay
 * Use inside a parent component that manages the stagger sequence
 */
export function StaggerItem({
  children,
  index,
  delay = 60,
  initial = { opacity: 0, y: 10 },
  animate = { opacity: 1, y: 0 },
  className = "",
}: StaggerItemProps) {
  const prefersReducedMotion = useReducedMotion();
  
  const transition = prefersReducedMotion
    ? { duration: 0.15 }
    : { type: "spring", damping: 1.0, response: 0.5, delay: index * delay / 1000 };

  return (
    <motion.div
      initial={prefersReducedMotion ? { opacity: 0 } as any : (initial as any)}
      animate={(animate as any)}
      transition={transition as any}
      className={className}
    >
      {children}
    </motion.div>
  );
}

/**
 * StaggerPage - Page-level stagger with multiple sections
 * Used for page content with header, main content, and footer sections
 */
export function StaggerPage({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  const prefersReducedMotion = useReducedMotion();
  
  const baseInitial = prefersReducedMotion ? { opacity: 0 } : { opacity: 0, y: 20 };
  const baseAnimate = { opacity: 1, y: 0 };
  const baseTransition = prefersReducedMotion
    ? { duration: 0.15 }
    : { type: "spring", damping: 1.0, response: 0.5 };

  return (
    <div className={className}>
      <AnimatePresence mode="popLayout">
        <motion.div
          initial={baseInitial}
          animate={baseAnimate}
          transition={baseTransition as any}
        >
          {children}
        </motion.div>
      </AnimatePresence>
    </div>
  );
}

/**
 * StaggerCards - Staggered card grid entrance
 * Optimized for card-based layouts with 80ms delay
 */
export function StaggerCards({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  const prefersReducedMotion = useReducedMotion();
  const childArray = Array.isArray(children) ? children : [children];
  
  const items = childArray.map((child, index) => {
    const transition = prefersReducedMotion
      ? { duration: 0.15 }
      : { type: "spring", damping: 1.0, response: 0.5, delay: index * 80 / 1000 };

    return (
      <motion.div
        key={index}
        initial={prefersReducedMotion ? { opacity: 0 } : { opacity: 0, y: 20, scale: 0.98 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={transition as any}
      >
        {child}
      </motion.div>
    );
  });

  return <div className={`grid gap-4 ${className}`}>{items}</div>;
}

/**
 * StaggerRows - Staggered table row entrance
 * 30ms delay per row from DESIGN.md specs
 */
export function StaggerRows({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  const prefersReducedMotion = useReducedMotion();
  const childArray = Array.isArray(children) ? children : [children];
  
  const items = childArray.map((child, index) => {
    const transition = prefersReducedMotion
      ? { duration: 0.15 }
      : { type: "spring", damping: 1.0, response: 0.5, delay: index * 30 / 1000 };

    return (
      <motion.tr
        key={index}
        initial={prefersReducedMotion ? { opacity: 0 } : { opacity: 0, x: -10 }}
        animate={{ opacity: 1, x: 0 }}
        transition={transition as any}
      >
        {child}
      </motion.tr>
    );
  });

  return <tbody className={className}>{items}</tbody>;
}

/**
 * StaggerChart - Staggered data point/series entrance
 * 40ms delay per series/point from DESIGN.md specs
 */
export function StaggerChart({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  const prefersReducedMotion = useReducedMotion();
  const childArray = Array.isArray(children) ? children : [children];
  
  const items = childArray.map((child, index) => {
    const transition = prefersReducedMotion
      ? { duration: 0.15 }
      : { type: "spring", damping: 1.0, response: 0.5, delay: index * 40 / 1000 };

    return (
      <motion.g
        key={index}
        initial={prefersReducedMotion ? { opacity: 0 } : { opacity: 0, scale: 0.8 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={transition as any}
      >
        {child}
      </motion.g>
    );
  });

  return <g className={className}>{items}</g>;
}