"use client";

import * as React from 'react'
import { cva, type VariantProps } from 'class-variance-authority'
import { motion } from 'framer-motion'
import { cn } from '@/lib/utils'
import { useReducedMotion } from '@/components/motion/ReducedMotion'

const badgeVariants = cva(
  'inline-flex items-center justify-center rounded-md border px-2 py-1 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disable-pointer-events:none disabled:opacity-50',
  {
    variants: {
      variant: {
        default:
          'border-transparent bg-primary text-primary-foreground hover:bg-primary/80',
        secondary:
          'border-transparent bg-secondary text-secondary-foreground hover:bg-secondary/80',
        destructive:
          'border-transparent bg-destructive text-destructive-foreground hover:bg-destructive/80 focus-visible:ring-destructive',
        outline: 'border border-input bg-background hover:bg-accent/50',
        // AirFed custom variants
        airfed: 'border-airfed-500/50 text-airfed-500 bg-airfed-500/10 hover:bg-airfed-500/20',
        success: 'border-success-500/50 text-success-500 bg-success-500/10 hover:bg-success-500/20',
        warning: 'border-amber-500/50 text-amber-500 bg-amber-500/10 hover:bg-amber-500/20',
        error: 'border-destructive-500/50 text-destructive-500 bg-destructive-500/10 hover:bg-destructive-500/20',
        online: 'border-success-500/50 text-success-500 bg-success-500/10',
        offline: 'border-gray-500/50 text-gray-500 bg-gray-500/10',
        running: 'border-airfed-500/50 text-airfed-500 bg-airfed-500/10',
        converged: 'border-success-500/50 text-success-500 bg-success-500/10',
        diverging: 'border-destructive-500/50 text-destructive-500 bg-destructive-500/10',
      },
      size: {
        default: 'h-6 px-2.5',
        sm: 'h-5 px-2 text-xs',
        lg: 'h-7 px-3 text-sm',
      },
    },
    defaultVariants: {
      variant: 'default',
      size: 'default',
    },
  }
)

export type BadgeTone = "accent" | "ok" | "warn" | "bad" | "info" | "neutral";

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {
  tone?: BadgeTone;
  label?: string;
}

const Badge = React.forwardRef<HTMLDivElement, BadgeProps>(
  ({ className, variant, size, children, tone, label, ...props }, ref) => {
    const reducedMotion = useReducedMotion()

    // Map tone to variant for backwards compatibility
    const toneToVariant: Record<string, string> = {
      accent: "airfed",
      ok: "success",
      warn: "warning",
      bad: "error",
      info: "info",
      neutral: "secondary",
    };
    const resolvedVariant = (variant || (tone ? toneToVariant[tone] : "default")) as "default" | "secondary" | "destructive" | "outline" | "airfed" | "success" | "warning" | "error" | "online" | "offline" | "running" | "converged" | "diverging";

    return (
      <motion.div
        ref={ref}
        initial={{ scale: reducedMotion ? 1 : 0.8, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        transition={{
          type: reducedMotion ? "tween" : "spring",
          damping: 1.0,
          stiffness: reducedMotion ? 150 : 200,
          duration: reducedMotion ? 0.01 : 0.25,
        }}
        className={cn(badgeVariants({ variant: resolvedVariant, size, className }))}
        {...(props as any)}
      >
        <motion.span
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.3 }}
        >
          {label ?? children}
        </motion.span>
      </motion.div>
    )
  }
)
Badge.displayName = 'Badge'

export type StatusPillProps = {
  status: string;
  label?: string;
  className?: string;
};

export const StatusPill = React.forwardRef<HTMLDivElement, StatusPillProps>(
  ({ status, label, className, ...props }, ref) => {
    const variantMap: Record<string, string> = {
      running: 'running',
      starting: 'running',
      waiting: 'warning',
      paused: 'secondary',
      stopping: 'warning',
      finished: 'success',
      converged: 'converged',
      diverging: 'diverging',
      online: 'online',
      offline: 'offline',
      active: 'airfed',
      idle: 'secondary',
      error: 'error',
      failed: 'destructive',
    };
    
    const variant = variantMap[status] || 'secondary';
    
    return (
      <Badge
        ref={ref}
        variant={variant as any}
        className={cn(className)}
        {...(props as any)}
      >
        {label ?? status}
      </Badge>
    );
  }
);

StatusPill.displayName = 'StatusPill';

export { Badge, badgeVariants };