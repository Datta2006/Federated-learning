"use client";

import { forwardRef } from "react";
import { motion } from "framer-motion";
import { useReducedMotion } from "./ReducedMotion";

/**
 * Spring configuration presets following DESIGN.md specs
 */
export type SpringPreset = "critical" | "momentum" | "reposition" | "scalePress" | "pageEnter";

export const springConfigs = {
  critical: { damping: 1.0, response: 0.35 },
  momentum: { damping: 0.8, response: 0.3 },
  reposition: { damping: 1.0, response: 0.4 },
  scalePress: { damping: 1.0, response: 0.15 },
  pageEnter: { damping: 1.0, response: 0.5 },
} as const;

/**
 * Spring - Motion/Framer spring wrapper with config presets
 */
export const Spring = forwardRef<HTMLDivElement, any>(
  (props, ref) => {
    const { preset = "critical", whileHover, whileTap, transition, initial, animate, exit, children, ...rest } = props;
    const prefersReducedMotion = useReducedMotion();

    const presetKey = preset as keyof typeof springConfigs;
    const presetConfig = springConfigs[presetKey];
    const baseTransition = prefersReducedMotion
      ? { duration: 0.15 }
      : {
          type: "spring",
          damping: presetConfig.damping,
          stiffness: 1 / (4 * presetConfig.damping * presetConfig.response ** 2),
        };

    const mergedTransition = {
      ...baseTransition,
      ...transition,
    };

    let effectiveInitial: any;
    if (initial !== undefined) {
      effectiveInitial = initial;
    } else if (preset === "pageEnter") {
      effectiveInitial = prefersReducedMotion ? { opacity: 1, y: 0 } : { opacity: 0, y: 20 };
    } else if (preset === "scalePress") {
      effectiveInitial = prefersReducedMotion ? { opacity: 1, scale: 1 } : { opacity: 0, scale: 0.9 };
    } else {
      effectiveInitial = prefersReducedMotion ? { opacity: 1 } : { opacity: 0, scale: 0.95 };
    }

    return (
      <motion.div
        ref={ref}
        initial={effectiveInitial}
        animate={animate}
        exit={exit}
        transition={mergedTransition}
        whileHover={whileHover}
        whileTap={whileTap}
        {...rest}
      >
        {children}
      </motion.div>
    );
  }
);

Spring.displayName = "Spring";

/**
 * Convenience components for common patterns
 */
export const SpringCritical = forwardRef<HTMLDivElement, any>((props, ref) => (
  <Spring ref={ref} preset="critical" {...props} />
));
SpringCritical.displayName = "SpringCritical";

export const SpringMomentum = forwardRef<HTMLDivElement, any>((props, ref) => (
  <Spring ref={ref} preset="momentum" {...props} />
));
SpringMomentum.displayName = "SpringMomentum";

export const SpringReposition = forwardRef<HTMLDivElement, any>((props, ref) => (
  <Spring ref={ref} preset="reposition" {...props} />
));
SpringReposition.displayName = "SpringReposition";

export const SpringScalePress = forwardRef<HTMLDivElement, any>((props, ref) => (
  <Spring ref={ref} preset="scalePress" {...props} />
));
SpringScalePress.displayName = "SpringScalePress";

export const SpringPageEnter = forwardRef<HTMLDivElement, any>((props, ref) => (
  <Spring ref={ref} preset="pageEnter" {...props} />
));
SpringPageEnter.displayName = "SpringPageEnter";