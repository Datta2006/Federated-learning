/**
 * Theme provider using next-themes
 */

import { ReactNode } from 'react'

export function ThemeProvider({ children }: { children: ReactNode }) {
  return <>{children}</>
}