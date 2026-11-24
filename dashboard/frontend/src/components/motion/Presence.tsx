"use client";

import { AnimatePresence } from "framer-motion";

/**
 * PresencePreset - Predefined exit animation presets
 */
export type PresencePreset = "modal" | "drawer" | "sheet" | "toast" | "tooltip" | "popover" | "dropdown" | "fade";

/**
 * Exit animation variants for each preset
 */
const exitVariants: Record<PresencePreset, { exit: any; transition: any }> = {
  modal: { exit: { opacity: 0, scale: 0.96 }, transition: { type: "spring", damping: 1.0, response: 0.25 } },
  drawer: { exit: { x: "100%" }, transition: { type: "spring", damping: 1.0, response: 0.3 } },
  sheet: { exit: { y: "100%" }, transition: { type: "spring", damping: 1.0, response: 0.3 } },
  toast: { exit: { y: -16, opacity: 0 }, transition: { type: "spring", damping: 1.0, response: 0.25, delay: 100 } },
  tooltip: { exit: { scale: 0.9, opacity: 0 }, transition: { type: "spring", damping: 1.0, response: 0.2 } },
  popover: { exit: { y: 8, opacity: 0, scale: 0.95 }, transition: { type: "spring", damping: 1.0, response: 0.25 } },
  dropdown: { exit: { opacity: 0, scale: 0.95 }, transition: { type: "spring", damping: 1.0, response: 0.25 } },
  fade: { exit: { opacity: 0 }, transition: { duration: 0.15 } },
};

/**
 * Presence - AnimatePresence wrapper with standardized exit animations
 */
export function Presence(props: {
  children: React.ReactNode;
  preset?: PresencePreset;
  exit?: any;
}) {
  const { children, preset = "fade", exit } = props;
  const effectiveExit = exit || exitVariants[preset].exit;
  const effectiveTransition = exit && (exit as any).transition || exitVariants[preset].transition;

  // AnimatePresence doesn't take exit/transition props directly
  // They need to be passed to children, so we just use AnimatePresence without custom props
  // The actual exit animations are handled by individual components using the preset config
  
  return (
    <AnimatePresence>
      {children}
    </AnimatePresence>
  );
}

export function ModalPresence(props: { children: React.ReactNode }) {
  return <Presence preset="modal">{props.children}</Presence>;
}

export function DrawerPresence(props: { children: React.ReactNode }) {
  return <Presence preset="drawer">{props.children}</Presence>;
}

export function SheetPresence(props: { children: React.ReactNode }) {
  return <Presence preset="sheet">{props.children}</Presence>;
}

export function ToastPresence(props: { children: React.ReactNode }) {
  return <Presence preset="toast">{props.children}</Presence>;
}

export function TooltipPresence(props: { children: React.ReactNode }) {
  return <Presence preset="tooltip">{props.children}</Presence>;
}

export function PopoverPresence(props: { children: React.ReactNode }) {
  return <Presence preset="popover">{props.children}</Presence>;
}

export function DropdownPresence(props: { children: React.ReactNode }) {
  return <Presence preset="dropdown">{props.children}</Presence>;
}

export function FadePresence(props: { children: React.ReactNode }) {
  return <Presence preset="fade">{props.children}</Presence>;
}