"use client";

import * as React from 'react'
import { motion } from 'framer-motion'
import { cn } from '@/lib/utils'
import { useReducedMotion } from '@/components/motion/ReducedMotion'

const cardVariants = {
  default: 'bg-card text-card-foreground border shadow-sm',
  gradient: 'bg-gradient-to-r from-airfed-500/10 to-teal-500/10 border airfed-500/20',
  elevated: 'bg-card border shadow-lg hover:shadow-xl transition-shadow',
}

const cardHeaderVariants = {
  default: 'border-b border-border pb-4',
  gradient: 'border-airfed-500/20 bg-airfed-500/5 pb-4',
}

export interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: keyof typeof cardVariants
  hover?: boolean
  entranceDelay?: number
}

export const Card = React.forwardRef<HTMLDivElement, CardProps>(
  ({ className, variant = 'default', hover = true, entranceDelay = 0, children, ...props }, ref) => {
    const reducedMotion = useReducedMotion()

    return (
      <motion.div
        ref={ref}
        initial={{ opacity: 0, y: reducedMotion ? 0 : 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{
          type: reducedMotion ? "tween" : "spring",
          damping: 1.0,
          stiffness: 200,
          duration: reducedMotion ? 0.15 : 0.4,
          delay: reducedMotion ? 0 : entranceDelay / 1000,
        }}
        whileHover={reducedMotion || !hover ? {} : { y: -2, boxShadow: "var(--shadow-2)" }}
        className={cn(
          'rounded-xl transition-all duration-300',
          cardVariants[variant],
          className
        )}
        {...props as any}
      >
        {children}
      </motion.div>
    )
  }
)
Card.displayName = 'Card'

export const CardHeader = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement> & { variant?: keyof typeof cardHeaderVariants }
>(({ className, variant = 'default', children, ...props }, ref) => (
  <div
    ref={ref}
    className={cn(
      'flex flex-col space-y-1.5 p-6 border-b border-border pb-4',
      cardHeaderVariants[variant],
      className
    )}
    {...props}
  >
    {children}
  </div>
))
CardHeader.displayName = 'CardHeader'

export const CardFooter = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, children, ...props }, ref) => (
  <div
    ref={ref}
    className={cn('flex items-center p-6 pt-0', className)}
    {...props}
  >
    {children}
  </div>
))
CardFooter.displayName = 'CardFooter'

export const CardTitle = React.forwardRef<
  HTMLParagraphElement,
  React.HTMLAttributes<HTMLParagraphElement>
>(({ className, children, ...props }, ref) => (
  <h3
    ref={ref}
    className={cn(
      'text-2xl font-bold leading-none tracking-tight',
      className
    )}
    {...props}
  >
    {children}
  </h3>
))
CardTitle.displayName = 'CardTitle'

export const CardDescription = React.forwardRef<
  HTMLParagraphElement,
  React.HTMLAttributes<HTMLParagraphElement>
>(({ className, children, ...props }, ref) => (
  <p
    ref={ref}
    className={cn('text-sm text-muted-foreground', className)}
    {...props}
  >
    {children}
  </p>
))
CardDescription.displayName = 'CardDescription'

export const CardContent = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, children, ...props }, ref) => (
  <div ref={ref} className={cn('p-6 pt-0', className)} {...props}>
    {children}
  </div>
))
CardContent.displayName = 'CardContent'