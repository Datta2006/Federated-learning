import { useState, useEffect } from 'react'
import { Play, Stop, Settings, Users } from 'lucide-react'
import { useExperimentStore } from '@/stores/experimentStore'

export function SimulationLabPage() {
  const { simulations, startSimulation, stopSimulation } = useExperimentStore()
  const [isRunning, setIsRunning] = useState(false)

  const activeSims = simulations?.filter(s => s.status === 'active') || []

  const handleToggle = () => {
    if (isRunning) {
      stopSimulation()
    } else {
      startSimulation()
    }
    setIsRunning(!isRunning)
  }

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold text-foreground">Simulation Lab</h1>
        <p className="text-muted-foreground mt-1">
          IoT device simulation controls and monitoring
        </p>
      </div>

      {/* Quick Actions */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <button
          onClick={handleToggle}
          className={`btn flex items-center justify-center gap-2 ${
            isRunning ? 'btn-destructive' : 'btn-primary'
          }`}
        >
          {isRunning ? <Stop size={16} /> : <Play size={16} />}
          {isRunning ? 'Stop Simulation' : 'Start Simulation'}
        </button>

        <button className="btn btn-secondary flex items-center justify-center gap-2">
          <Settings size={16} />
          Configuration
        </button>

        <button className="btn btn-secondary flex items-center gap-2">
          <Settings size={16} />
          Advanced Settings
        </button>

        <div className="panel">
          <div className="text-center">
            <p className="text-3xl font-bold text-foreground">{activeSims.length}</p>
            <p className="text-sm text-muted-foreground">Active Simulations</p>
          </div>
        </div>
      </div>

      {/* Active Simulations */}
      <div className="panel">
        <h2 className="panel-title mb-4">Active Simulations</h2>
        
        {activeSims.length > 0 ? (
          <div className="space-y-3">
            {activeSims.map((sim: any) => (
              <div key={sim.id} className="border border-border rounded-lg p-3">
                <div className="flex items-center justify-between">
                  <div>
                    <div className="font-medium text-foreground">{sim.name}</div>
                    <div className="text-sm text-muted-foreground">
                      {sim.nodes} nodes • {sim.duration}m simulation
                    </div>
                  </div>
                  <button className="btn btn-destructive btn-sm">Stop</button>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-center py-8 text-muted-foreground">
            No active simulations. Start one above to begin.
          </p>
        )}
      </div>

      {/* Simulation Types */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <div className="panel">
          <h3 className="font-medium text-foreground mb-2">Air Quality</h3>
          <p className="text-sm text-muted-foreground mb-3">
            Synthetic PM2.5 data for testing
          </p>
          <button className="btn btn-primary btn-sm w-full">Configure</button>
        </div>

        <div className="panel">
          <h3 className="font-medium text-foreground mb-2">Network Topology</h3>
          <p className="text-sm text-muted-foreground mb-3">
            Mobile device simulation
          </p>
          <button className="btn btn-secondary btn-sm w-full">Configure</button>
        </div>

        <div className="panel">
          <h3 className="font-medium text-foreground mb-2">Load Testing</h3>
          <p className="text-sm text-muted-foreground mb-3">
            High-volume data generation
          </p>
          <button className="btn btn-secondary btn-sm w-full">Configure</button>
        </div>
      </div>
    </div>
  )
}