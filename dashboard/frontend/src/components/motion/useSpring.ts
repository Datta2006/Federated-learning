"use client";

import { useReducedMotion } from "./ReducedMotion";

/**
 * useSpringTransition - Hook that returns the appropriate spring transition config
 * respecting prefers-reduced-motion.
 * 
 * @param options - Spring configuration options
 * @returns Transition object for Framer Motion
 * 
 * @example
 * ```tsx
 * const transition = useSpringTransition({ damping: 1.0, stiffness: 150 });
 * <motion.div transition={transition} />
 * ```
 */
export const useSpringTransition = (
  damping: number = 1.0,
  stiffness: number = 150,
  mass: number = 1
) => {
  const prefersReducedMotion = useReducedMotion();

  if (prefersReducedMotion) {
    return { duration: 0.15 };
  }

  return {
    type: "spring" as const,
    damping,
    stiffness,
    mass,
  };
};

/**
 * useSpringDuration - Returns the appropriate duration for an animation,
 * respecting prefers-reduced-motion.
 * 
 * When reduced motion is enabled, durations are shortened.
 */
export const useSpringDuration = (
  normalDuration: number = 0.3,
  reducedDuration: number = 0.15
): number => {
  const prefersReducedMotion = useReducedMotion();
  return prefersReducedMotion ? reducedDuration : normalDuration;
};

/**
 * Spring presets from DESIGN.md
 */
export const SPRING_PRESETS = {
  // Press/Press interactions (button taps, etc.)
  press: { damping: 1.0, stiffness: 500, mass: 1 },
  // Card hover lifts
  hover: { damping: 1.0, stiffness: 150, mass: 1 },
  // Badge/Status mount
  mount: { damping: 1.0, stiffness: 200, mass: 1 },
  // Dialog entrance/exit
  dialog: { damping: 15, stiffness: 500, mass: 1 },
  // Counter animations
  counter: { damping: 1.0, stiffness: 150, mass: 1 },
  // Staggered lists
  stagger: { damping: 1.0, stiffness: 120, mass: 1 },
};

/**
 * Options for spring transition configuration
 */
export interface UseSpringOptions {
  damping?: number;
  stiffness?: number;
  mass?: number;
}

/**
 * Options for counter spring animation
 */
export interface UseSpringCounterOptions {
  damping?: number;
  stiffness?: number;
  duration?: number;
}

/**
 * getSpringTransition - Utility function to get a spring transition config
 * respecting reduced motion preferences.
 * 
 * @param preset - Key of SPRING_PRESETS to use
 * @returns Transition object for Framer Motion
 */
export const getSpringTransition = (
  preset: keyof typeof SPRING_PRESETS = "press",
  customDamping?: number,
  customStiffness?: number
) => {
  const prefersReducedMotion = useReducedMotion();
  const config = SPRING_PRESETS[preset];
  const damping = customDamping ?? config.damping;
  const stiffness = customStiffness ?? config.stiffness;

  if (prefersReducedMotion) {
    return { duration: 0.15 };
  }

  return {
    type: "spring" as const,
    damping,
    stiffness,
    mass: config.mass,
  };
};