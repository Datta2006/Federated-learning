"use client";

import { useEffect, useState, createContext, useContext, ReactNode } from "react";

/**
 * Context for prefers-reduced-motion preference
 * Allows SSR-safe access to the reduced motion setting
 */
export const ReducedMotionContext = createContext<{ prefersReducedMotion: boolean }>({
  prefersReducedMotion: false,
});

/**
 * Provider for reduced motion preference
 * Initializes the media query listener on client-side
 */
export function ReducedMotionProvider({ children }: { children: ReactNode }) {
  const [prefersReducedMotion, setPrefersReducedMotion] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) {
      return;
    }
    const mediaQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
    setPrefersReducedMotion(mediaQuery.matches);

    const handler = (event: any) => {
      setPrefersReducedMotion(event.matches);
    };

    mediaQuery.addEventListener("change", handler);
    return () => mediaQuery.removeEventListener("change", handler);
  }, []);

  return (
    <ReducedMotionContext.Provider value={{ prefersReducedMotion }}>
      {children}
    </ReducedMotionContext.Provider>
  );
}

/**
 * Hook to access prefers-reduced-motion setting
 * Returns false during SSR, then actual preference after hydration
 */
export function useReducedMotion(): boolean {
  const context = useContext(ReducedMotionContext);
  if (!context) {
    return false;
  }
  return context.prefersReducedMotion;
}

/**
 * Hook that returns reduced motion config for motion components
 * Use this to pass to transition configs
 */
export function useReducedMotionConfig() {
  const prefersReducedMotion = useReducedMotion();

  return {
    prefersReducedMotion,
    transition: prefersReducedMotion
      ? { duration: 0.15 }
      : undefined,
  };
}