"use client";

import * as React from 'react'
import { motion } from 'framer-motion'
import { cn } from '@/lib/utils'
import { useReducedMotion } from '@/components/motion/ReducedMotion'

export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  error?: boolean
}

const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className, type, error, ...props }, ref) => {
    const reducedMotion = useReducedMotion()

    return (
      <motion.input
        type={type}
        className={cn(
          'flex h-10 w-full rounded-md border bg-background px-3 py-2 text-sm transition-colors file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50',
          {
            'border-input': !error,
            'border-destructive focus-visible:ring-destructive': error,
          },
          className
        )}
        ref={ref}
        animate={error && !reducedMotion ? { x: [0, -3, 3, -3, 3, 0] } : {}}
        transition={error && !reducedMotion ? { duration: 0.3 } : { duration: reducedMotion ? 0 : 0.15 }}
        whileFocus={reducedMotion ? undefined : { scale: 1 }}
        {...(props as any)}
      />
    )
  }
)
Input.displayName = 'Input'

export { Input }