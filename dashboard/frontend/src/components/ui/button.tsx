"use client";

import * as React from 'react'
import { Slot } from '@radix-ui/react-slot'
import { cva, type VariantProps } from 'class-variance-authority'
import { motion } from 'framer-motion'
import { cn } from '@/lib/utils'
import { useReducedMotion } from '@/components/motion/ReducedMotion'

const buttonVariants = cva(
  'inline-flex items-center justify-center rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0',
  {
    variants: {
      variant: {
        default: 'bg-primary text-primary-foreground hover:bg-primary/90 shadow-sm',
        destructive:
          'bg-destructive text-destructive-foreground hover:bg-destructive/90 shadow-sm focus-visible:ring-destructive',
        outline:
          'border border-input bg-background hover:bg-accent/50 hover:text-accent shadow-sm',
        secondary: 'bg-secondary text-secondary-foreground hover:bg-secondary/80 shadow-sm',
        ghost: 'hover:bg-accent/10 hover:text-accent',
        link: 'text-primary underline-offset-4 hover:underline transparent hover:bg-accent/10',
        // AirFed custom variants
        airfed: 'bg-airfed-500 text-white hover:bg-airfed-500/90 shadow-md hover:shadow-airfed-500/20',
        airfedOutline:
          'border border-airfed-500/50 text-airfed-500 hover:bg-airfed-500/10 hover:text-airfed-600',
        gradient:
          'bg-gradient-to-r from-airfed-500 to-teal-500 text-white hover:from-airfed-600 hover:to-teal-600 shadow-md',
      },
      size: {
        default: 'h-10 px-4 py-2',
        sm: 'h-9 rounded-md px-3 text-xs',
        lg: 'h-11 rounded-md px-8',
        icon: 'h-10 w-10',
      },
    },
    defaultVariants: {
      variant: 'default',
      size: 'default',
    },
  }
)

/**
 * Button - Enhanced with motion per DESIGN.md
 * 
 * Features:
 * - Press spring (scale 0.97) on pointer-down
 * - Loading spinner with cross-fade
 * - Focus-visible ring from DESIGN.md tokens
 * - Respects prefers-reduced-motion
 */
export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean
  isLoading?: boolean
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, isLoading, children, ...props }, ref) => {
    const reducedMotion = useReducedMotion()
    const Comp = asChild ? Slot : 'button'

    return (
      <motion.button
        // $FlowFixMe - framer-motion v14 types
        whileTap={{ scale: reducedMotion ? 1 : 0.97 }}
        initial={{ scale: 1 }}
        transition={{
          type: reducedMotion ? "tween" : "spring",
          damping: reducedMotion ? 1 : 20,
          stiffness: reducedMotion ? 150 : 200,
          duration: reducedMotion ? 0.1 : 0.1,
        }}
        ref={ref}
        className={cn(buttonVariants({ variant, size, className }))}
        disabled={isLoading}
        {...props as any}
      >
        {isLoading ? (
          <span className="flex items-center gap-2">
            <span className="spinner inline-block mr-2 h-4 w-4 animate-spin border-2 border-current border-t-transparent rounded-full" />
            {children}
          </span>
        ) : (
          children
        )}
      </motion.button>
    )
  }
)
Button.displayName = 'Button'

export { Button, buttonVariants }