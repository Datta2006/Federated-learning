import { useState, useEffect, useCallback } from "react";

/**
 * useStagger - Hook for staggered delays
 * 
 * Calculates staggered delay indices for children entrance animations.
 * Follows DESIGN.md 4.3 specs:
 * - Page mount: 60ms per element
 * - Table rows: 30ms/row (max 200ms total)
 * - Charts: 50ms stagger
 * - Panels: 80ms stagger
 * 
 * Respects `prefers-reduced-motion` - returns uniform delays
 * 
 * @example
 * ```tsx
 * // Calculate delays for page mount
 * const delays = useStagger({ staggerMs: 60, childCount: 4, reducedMotion: false });
 * // Returns: [0, 60, 120, 180]
 * 
 * // Table rows
 * const delays = useStagger({ staggerMs: 30, childCount: 20, reducedMotion: false });
 * // Returns: [0, 30, 60, 90, ...] (max 200ms total)
 * ```
 */
export interface UseStaggerOptions {
  /** Number of children */
  childCount: number;
  /** Delay between children in ms (default: 60ms per DESIGN.md 4.3) */
  staggerMs?: number;
  /** Maximum total stagger duration in ms (default: 200ms) */
  maxTotalMs?: number;
  /** Whether to respect prefers-reduced-motion */
  reducedMotion?: boolean;
  /** Custom base delay offset */
  baseDelayMs?: number;
}

/**
 * Calculates staggered delay indices for children
 * 
 * @returns Array of delay values in ms for each child
 */
export const useStagger = (options: UseStaggerOptions): number[] => {
  const {
    childCount,
    staggerMs = 60,
    maxTotalMs = 200,
    reducedMotion = false,
    baseDelayMs = 0,
  } = options;

  // In reduced motion, use uniform delays (no stagger)
  if (reducedMotion) {
    return Array.from({ length: childCount }, (_, i) => baseDelayMs);
  }

  // Calculate delays with cap at maxTotalMs
  const delays: number[] = [];
  let maxAllowedDelay = maxTotalMs - staggerMs; // Leave room for last element

  for (let i = 0; i < childCount; i++) {
    const rawDelay = baseDelayMs + i * staggerMs;

    // Cap delay so last element doesn't exceed maxTotalMs
    const cappedDelay = rawDelay > maxAllowedDelay ? maxAllowedDelay : rawDelay;
    delays.push(cappedDelay);
  }

  return delays;
};

/**
 * Staggered animation wrapper using useStagger
 * 
 * Provides a ready-to-use component for staggered children entrance
 */
export interface StaggerWrapperProps {
  /** Children to stagger */
  children: React.ReactNode;
  /** Delay between children in ms */
  staggerMs?: number;
  /** Maximum total duration */
  maxTotalMs?: number;
  /** Initial animation state */
  initial?: {
    opacity?: number;
    translateY?: number;
    translateX?: number;
    scale?: number;
  };
  /** Animate state */
  animate?: {
    opacity?: number;
    translateY?: number;
    translateX?: number;
    scale?: number;
  };
  /** Easing */
  ease?: string;
}

/**
 * Generates style objects for each child based on stagger delays
 */
export const useStaggerStyles = (
  childCount: number,
  options: Omit<UseStaggerOptions, "childCount"> = {}
) => {
  const delays = useStagger({ childCount, ...options });
  const styles: { [key: number]: React.CSSProperties } = {};

  delays.forEach((delayMs, index) => {
    styles[index] = {
      transitionDelay: `${delayMs}ms`,
      // Base transition that will be animated
      transitionProperty: "opacity, transform",
      transitionTimingFunction: "cubic-bezier(0.16, 1, 0.3, 1)",
    };
  });

  return styles;
};

/**
 * Calculates the total stagger duration
 */
export const calculateTotalStagger = (
  childCount: number,
  staggerMs = 60,
  maxTotalMs = 200
): { totalMs: number; actualStaggerMs: number } => {
  const totalMs = (childCount - 1) * staggerMs;
  const actualStaggerMs = totalMs > maxTotalMs ? maxTotalMs / (childCount - 1) : staggerMs;

  return { totalMs, actualStaggerMs };
};