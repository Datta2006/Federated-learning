"use client";

import * as React from 'react'
import { motion } from 'framer-motion'
import { cn } from '@/lib/utils'
import { useReducedMotion } from '@/components/motion/ReducedMotion'

const Skeleton = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement> & { animation?: 'shimmer' | 'pulse' | 'none' }
>(({ className, animation = 'shimmer', ...props }, ref) => {
  const reducedMotion = useReducedMotion()

  const baseClasses = 'relative overflow-hidden rounded-md bg-muted'
  
  if (reducedMotion || animation === 'none') {
    return (
      <div ref={ref} className={cn(baseClasses, className)} {...props}>
        <div className="absolute inset-0 bg-muted" />
      </div>
    )
  }

  const animationClasses = animation === 'pulse'
    ? 'animate-pulse'
    : 'bg-gradient-to-r from-transparent via-white/5 to-transparent'

  return (
    <motion.div
      ref={ref}
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.3 }}
      className={cn(baseClasses, animationClasses, className)}
      {...(props as any)}
    >
      <motion.div
        animate={{ x: ['100%', '-100%'] }}
        transition={{
          duration: 1.5,
          repeat: Infinity,
          repeatType: 'loop',
          ease: 'linear',
        }}
        className="absolute inset-0 bg-gradient-to-r from-transparent via-white/20 to-transparent"
      />
    </motion.div>
  )
})
Skeleton.displayName = 'Skeleton'

export { Skeleton }