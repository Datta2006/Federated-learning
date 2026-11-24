// Export all motion primitives
export type {
  SpringPreset,
} from "./Spring";

// Export Spring components and configs
export {
  springConfigs,
  Spring,
  SpringCritical,
  SpringMomentum,
  SpringReposition,
  SpringScalePress,
  SpringPageEnter,
} from "./Spring";

// Export Stagger components
export {
  Stagger,
  StaggerItem,
  StaggerPage,
  StaggerCards,
  StaggerRows,
  StaggerChart,
} from "./Stagger";

// Export PageTransition (runtime components only, types inferred)
export { PageTransition, PageEnter } from "./PageTransition";

// Export Presence components
export {
  Presence,
  ModalPresence,
  DrawerPresence,
  SheetPresence,
  ToastPresence,
  TooltipPresence,
  PopoverPresence,
  DropdownPresence,
  FadePresence,
} from "./Presence";

// Export ReducedMotion hook and context
export { useReducedMotion, ReducedMotionContext, ReducedMotionProvider } from "./ReducedMotion";

// Export useReducedMotionConfig hook
export { useReducedMotionConfig } from "./ReducedMotion";

// Export useSpring hooks and presets
export { 
  useSpringTransition,
  useSpringDuration,
  SPRING_PRESETS,
  getSpringTransition,
} from "./useSpring";

// Export useStagger hook
export { useStagger, useStaggerStyles, calculateTotalStagger } from "./useStagger";

/**
 * All motion primitives exported from this package:
 *
 * - Spring: Spring.tsx - Motion/Framer spring wrapper with config presets
 * - Stagger: Stagger.tsx - Staggered children entrance component
 * - PageTransition: PageTransition.tsx - Route-level transitions
 * - Presence: Presence.tsx - AnimatePresence wrapper with exit animations
 * - ReducedMotion: ReducedMotion.tsx - Hook + context for prefers-reduced-motion
 * - useSpring.ts: Hook for spring values (drag, scroll, count-up)
 * - useStagger.ts: Hook for staggered delays
 * - index.ts: Exports
 */