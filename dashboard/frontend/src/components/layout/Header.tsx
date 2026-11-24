import { useState, useEffect } from 'react'

interface HeaderProps {
  onSidebarToggle?: () => void
}

export function Header({ onSidebarToggle }: HeaderProps) {
  const [mounted, setMounted] = useState(false)

  useEffect(() => {
    setMounted(true)
  }, [])

  const toggleTheme = () => {
    const root = document.documentElement
    const currentTheme = root.getAttribute('data-theme') || 'light'
    const newTheme = currentTheme === 'dark' ? 'light' : 'dark'
    root.setAttribute('data-theme', newTheme)
    localStorage.setItem('airfed-theme', newTheme)
  }

  const toggleSidebar = () => {
    if (onSidebarToggle) onSidebarToggle()
  }

  return (
    <header className="flex h-16 items-center justify-between border-b border-border bg-card bg-opacity-50 px-4 lg:px-8">
      {/* Left Side */}
      <div className="flex items-center gap-4">
        {/* Mobile Menu Button */}
        {onSidebarToggle && (
          <button
            className="md:hidden rounded-lg p-2 text-foreground hover:bg-muted transition-colors"
            onClick={toggleSidebar}
            aria-label="Toggle menu"
          >
            <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="3" y1="12" x2="21" y2="12" />
              <line x1="4" y1="6" x2="20" y2="6" />
              <line x1="4" y1="18" x2="20" y2="18" />
            </svg>
          </button>
        )}

        {/* Page Title */}
        <div>
          <h1 className="text-lg font-semibold text-foreground">
            Federated Learning Dashboard
          </h1>
          <p className="text-xs text-muted-foreground">
            Monitor and manage your FL experiments in real-time
          </p>
        </div>
      </div>

      {/* Right Side */}
      <div className="flex items-center gap-4">
        {/* Theme Toggle */}
        {mounted && (
          <button
            className="rounded-lg p-2 text-foreground hover:bg-muted transition-colors"
            onClick={toggleTheme}
            aria-label="Toggle theme"
          >
            <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="5" />
              <path d="M12 1v2" />
              <path d="M12 21v2" />
              <path d="M4.93 4.93l1.41 1.41" />
              <path d="M17.66 17.66l1.41 1.41" />
              <path d="M12 5v2" />
              <path d="M12 17v2" />
              <path d="M4.93 19.07l1.41-1.41" />
              <path d="M17.66 2.34l1.41-1.41" />
              <path d="M5 12h2" />
              <path d="M17 12h2" />
              <path d="M4 12h2" />
              <path d="M17 12h2" />
            </svg>
          </button>
        )}

        {/* User Menu */}
        <button
          className="rounded-full h-9 w-9 flex items-center justify-center text-foreground hover:bg-muted transition-colors"
          aria-label="User menu"
        >
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-primary/10 text-primary font-bold">
            UF
          </div>
        </button>
      </div>
    </header>
  )
}