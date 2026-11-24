import { AnimatePresence } from "framer-motion";
import { motion } from "framer-motion";
import { useLocation } from "react-router-dom";
import { springConfigs } from "./Spring";
import { useReducedMotionConfig } from "./ReducedMotion";

/**
 * PageTransition - Route-level transition wrapper
 *
 * Wraps route changes with entrance/exit animations
 * Uses AnimatePresence to animate removed pages
 * Respects prefers-reduced-motion
 */
interface PageTransitionProps {
  children: React.ReactNode;
  /** Optional spring config override */ springConfig?: {
    damping?: number;
    stiffness?: number;
    response?: number;
  };
}

/**
 * PageEnter - Entrance animation for new page content
 * Uses spring from DESIGN.md specs: damping 1.0, response 0.5
 */
export const PageEnter = ({ children, springConfig }: PageTransitionProps) => {
  const { transition } = useReducedMotionConfig();

  // Use provided config or fall back to reduced motion config
  const mergedTransition = springConfig
    ? { ...springConfigs.critical, ...springConfig }
    : transition;

  return (
    <AnimatePresence mode="sync">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -20 }}
        transition={mergedTransition}
      >
        {children}
      </motion.div>
    </AnimatePresence>
  );
};

/**
 * PageTransition - Container that wraps entire page content
 * Coordinates sidebar + header + content transitions
 */
export const PageTransition = ({ children, springConfig }: PageTransitionProps) => {
  const location = useLocation();
  const { transition } = useReducedMotionConfig();

  // Use provided config or fall back to reduced motion config
  const mergedTransition = springConfig
    ? { ...springConfigs.critical, ...springConfig }
    : transition;

  return (
    <AnimatePresence mode="sync">
      <motion.div
        initial={{ opacity: 0, x: -20 }}
        animate={{ opacity: 1, x: 0 }}
        exit={{ opacity: 0, x: 20 }}
        transition={mergedTransition}
      >
        {children}
      </motion.div>
    </AnimatePresence>
  );
};

/**
 * RouteTransition - Individual route transition with direction awareness
 *
 * @param from - The path being transitioned from
 * @param to - The path being transitioned to
 * @param direction - 'left' (navigate forward) or 'right' (navigate back)
 */
export const RouteTransition = ({
  from,
  to,
  direction = "left",
  children,
  springConfig,
}: {
  from: string;
  to: string;
  direction?: "left" | "right";
  children: React.ReactNode;
  springConfig?: {
    damping?: number;
    stiffness?: number;
    response?: number;
  };
}) => {
  const { transition } = useReducedMotionConfig();

  // Use provided config or fall back to reduced motion config
  const mergedTransition = springConfig
    ? { ...springConfigs.critical, ...springConfig }
    : transition;

  // Add direction-specific transforms
  const enterFrom = direction === "left" ? { x: 20 } : { x: -20 };
  const exitTo = direction === "left" ? { x: -20 } : { x: 20 };

  return (
    <AnimatePresence mode="sync">
      <motion.div
        initial={{ ...enterFrom, opacity: 0 }}
        animate={{ opacity: 1, x: 0 }}
        exit={{ opacity: 0, x: direction === "left" ? -20 : 20 }}
        transition={mergedTransition}
      >
        {children}
      </motion.div>
    </AnimatePresence>
  );
};