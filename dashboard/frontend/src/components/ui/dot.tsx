import * as React from "react"
import { cn } from "@/lib/utils"

export interface DotProps {
  tone?: "accent" | "ok" | "warn" | "bad" | "info" | "neutral"
  className?: string
}

const dotVariants = {
  default: "h-2 w-2 rounded-full",
  success: "h-2 w-2 rounded-full bg-success-500",
  warning: "h-2 w-2 rounded-full bg-amber-500",
  error: "h-2 w-2 rounded-full bg-destructive-500",
  info: "h-2 w-2 rounded-full bg-info",
  neutral: "h-2 w-2 rounded-full bg-muted",
  accent: "h-2 w-2 rounded-full bg-primary",
  ok: "h-2 w-2 rounded-full bg-success",
  warn: "h-2 w-2 rounded-full bg-amber-500",
  bad: "h-2 w-2 rounded-full bg-destructive",
} as const

export const Dot = React.forwardRef<HTMLSpanElement, DotProps>(({ tone = "neutral", className }, ref) => {
  const baseClass = cn(
    dotVariants[tone] || dotVariants.neutral,
    className
  )

  return <span ref={ref} className={baseClass} />
})

Dot.displayName = 'Dot'

export { }