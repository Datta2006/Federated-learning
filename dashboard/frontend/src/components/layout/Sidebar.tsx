import { NavLink, useLocation } from 'react-router-dom'
import {
  LayoutDashboard,
  Brain,
  Network,
  Terminal,
  Server,
  BarChart3,
  Layers,
  Cloud,
  History,
} from 'lucide-react'
import { useExperimentStore } from '@/stores/experimentStore'
import { useState, useEffect } from 'react'

const sidebarRoutes = [
  {
    name: 'Overview',
    href: '/overview',
    icon: LayoutDashboard,
    description: 'Control centre dashboard',
  },
  {
    name: 'Simulation Lab',
    href: '/simulation-lab',
    icon: Brain,
    description: 'IoT device simulation controls',
  },
  {
    name: 'Network Topology',
    href: '/network-topology',
    icon: Network,
    description: 'Live network visualization',
  },
  {
    name: 'Terminal',
    href: '/terminal',
    icon: Terminal,
    description: 'Live API command execution',
  },
  {
    name: 'Gateways',
    href: '/gateways',
    icon: Server,
    description: 'Gateway orchestration',
  },
  {
    name: 'Federated Learning',
    href: '/federated-learning',
    icon: BarChart3,
    description: 'Training orchestration',
  },
  {
    name: 'Models',
    href: '/models',
    icon: Layers,
    description: 'Global model management',
  },
  {
    name: 'Air Quality',
    href: '/air-quality',
    icon: Cloud,
    description: 'AQI monitoring and forecasting',
  },
  {
    name: 'Experiments',
    href: '/experiments',
    icon: History,
    description: 'Experiment history',
  },
]

interface SidebarProps {
  open: boolean
  setOpen: (open: boolean) => void
}

export function Sidebar({ open, setOpen }: SidebarProps) {
  const location = useLocation()
  const { experiments } = useExperimentStore()

  // Calculate stats for the badge
  const totalExperiments = experiments.length
  const runningCount = experiments.filter(e => e.status === 'running').length
  const failedCount = experiments.filter(e => e.status === 'failed').length

  const activeRoute = sidebarRoutes.find(route => route.href === location.pathname)

  // Mobile sidebar
  const isMobile = typeof window !== 'undefined' && window.innerWidth < 768

  const handleNavClick = () => {
    if (isMobile) setOpen(false)
  }

  // Desktop sidebar - always visible on desktop
  if (!isMobile) {
    return (
      <aside className="fixed top-0 left-0 h-full w-64 flex-col overflow-y-auto border-r border-border bg-card bg-opacity-50 backdrop-blur">
        <SidebarContent
          activeRoute={activeRoute}
          totalExperiments={totalExperiments}
          runningCount={runningCount}
          failedCount={failedCount}
        />
      </aside>
    )
  }

  // Mobile sidebar with overlay
  return (
    <>
      {/* Sidebar */}
      {open && (
        <aside className="fixed top-0 left-0 z-50 h-full w-64 flex-col overflow-y-auto border-r border-border bg-card">
          <SidebarContent
            activeRoute={activeRoute}
            totalExperiments={totalExperiments}
            runningCount={runningCount}
            failedCount={failedCount}
            onClose={() => setOpen(false)}
          />
        </aside>
      )}

      {/* Overlay */}
      {open && (
        <div
          className="fixed inset-0 bg-black/20 z-40"
          onClick={() => setOpen(false)}
          aria-hidden="true"
        />
      )}

      {/* Mobile Menu Button */}
      <button
        onClick={() => setOpen(true)}
        className="fixed top-4 left-4 z-50 rounded-full bg-primary p-2 text-primary-foreground shadow-lg hover:bg-primary/90 md:hidden"
        aria-label="Toggle sidebar"
      >
        <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <line x1="3" y1="12" x2="21" y2="12" />
        </svg>
      </button>
    </>
  )
}

interface SidebarContentProps {
  activeRoute: (typeof sidebarRoutes)[0] | undefined
  totalExperiments: number
  runningCount: number
  failedCount: number
  onClose?: () => void
}

function SidebarContent({
  activeRoute,
  totalExperiments,
  runningCount,
  failedCount,
  onClose,
}: SidebarContentProps) {
  const location = useLocation()

  const handleNavClick = () => {
    if (onClose) onClose()
  }

  return (
    <>
      {/* Logo/Brand */}
      <div className="flex h-16 items-center justify-between border-b border-border px-6 pb-3.5 pt-3">
        <div className="flex items-center space-x-2">
          <div className="relative h-8 w-8 rounded-lg bg-gradient-to-r from-primary to-teal-500 flex items-center justify-center">
            <Layers className="h-5 w-5 text-white" />
          </div>
          <div className="text-xl font-bold tracking-tight text-foreground">
            AirFed
          </div>
        </div>
        {typeof window !== 'undefined' && window.innerWidth < 768 && (
          <button
            onClick={() => onClose?.()}
            className="rounded-lg p-2 text-muted-foreground hover:bg-muted hover:text-foreground"
            aria-label="Close sidebar"
          >
            <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="15" y1="9" x2="9" y2="15" />
              <line x1="9" y1="9" x2="15" y2="9" />
            </svg>
          </button>
        )}
      </div>

      {/* Stats */}
      <div className="mb-6 px-6">
        <div className="flex items-center gap-3 rounded-lg bg-muted/50 p-3">
          <div className="flex-1">
            <p className="text-xs font-medium text-muted-foreground">Active Experiments</p>
            <p className="text-lg font-semibold text-foreground">{totalExperiments}</p>
          </div>
          {runningCount > 0 && (
            <span className="badge badge-primary">
              {runningCount} running
            </span>
          )}
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex flex-col gap-1 px-3">
        {sidebarRoutes.map((route) => {
          const Icon = route.icon
          const isActive = location.pathname === route.href

          return (
            <NavLink
              key={route.name}
              to={route.href}
              onClick={handleNavClick}
              className={({ isActive }) =>
                `flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-all duration-150 ${isActive ? 'bg-primary/10 text-primary font-semibold' : 'text-foreground hover:bg-muted/50 hover:text-primary'}`
              }
            >
              <Icon className="h-5 w-5" />
              <span className="flex-1">{route.name}</span>
              {route.name === 'Experiments' && failedCount > 0 && (
                <span className="badge badge-destructive">
                  {failedCount}
                </span>
              )}
            </NavLink>
          )
        })}
      </nav>

      {/* Footer */}
      <div className="mt-auto border-t border-border p-6">
        <div className="text-xs text-muted-foreground">
          <p>Phase 2 Dashboard v1.0</p>
          <p className="mt-1">AirFed Federated Learning Platform</p>
        </div>
      </div>
    </>
  )
}