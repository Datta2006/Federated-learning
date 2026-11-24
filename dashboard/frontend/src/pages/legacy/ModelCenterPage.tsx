import { useState, useEffect } from 'react'
import { Database, Download, Upload, RefreshCw, History, Settings } from 'lucide-react'

interface Model {
  id: string
  version: string
  created: string
  parameters: number
  val_loss: number
  samples: number
  size: string
  has_weights: boolean
}

export function ModelCenterPage() {
  const [models, setModels] = useState<Model[]>([])
  const [loading, setLoading] = useState(true)
  const [selectedModel, setSelectedModel] = useState<Model | null>(null)

  useEffect(() => {
    // Simulate API call
    setTimeout(() => {
      setModels([
        {
          id: 'model-001',
          version: 'v3.2.1',
          created: '2024-01-15 14:30:00',
          parameters: 12800000,
          val_loss: 0.0423,
          samples: 84200,
          size: '48.2 MB',
          has_weights: true,
        },
        {
          id: 'model-002',
          version: 'v3.2.0',
          created: '2024-01-14 10:15:00',
          parameters: 12800000,
          val_loss: 0.0487,
          samples: 84200,
          size: '48.2 MB',
          has_weights: true,
        },
        {
          id: 'model-003',
          version: 'v3.1.0',
          created: '2024-01-10 08:45:00',
          parameters: 12000000,
          val_loss: 0.0612,
          samples: 84200,
          size: '45.1 MB',
          has_weights: false,
        },
      ])
      setLoading(false)
    }, 500)
  }, [])

  const formatParams = (params: number) => {
    if (params >= 1e6) return `${(params / 1e6).toFixed(1)}M`
    if (params >= 1e3) return `${(params / 1e3).toFixed(1)}K`
    return params.toString()
  }

  const formatLoss = (loss: number) => {
    if (loss < 0.001) return loss.toFixed(6)
    if (loss < 0.1) return loss.toFixed(4)
    return loss.toFixed(3)
  }

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold text-foreground">Models</h1>
        <p className="text-muted-foreground mt-1">
          Global model management and version history
        </p>
      </div>

      {/* Actions */}
      <div className="flex gap-2">
        <button className="btn btn-primary flex items-center gap-2">
          <Database size={16} />
          Register Model
        </button>
        <button className="btn btn-secondary flex items-center gap-2">
          <Download size={16} />
          Download
        </button>
        <button className="btn btn-secondary flex items-center gap-2">
          <Upload size={16} />
          Upload
        </button>
        <button className="btn btn-ghost flex items-center gap-2 ml-auto">
          <RefreshCw size={16} />
          Refresh
        </button>
      </div>

      {/* Model Stats */}
      <div className="grid gap-4 sm:grid-cols-4">
        <ModelStatCard
          title="Total Models"
          value="3"
        />
        <ModelStatCard
          title="With Weights"
          value="2"
          status="ok"
        />
        <ModelStatCard
          title="Latest Loss"
          value="0.042"
          status={0.042 > 0.05 ? 'warning' : 'ok'}
        />
        <ModelStatCard
          title="Total Params"
          value="34.8M"
        />
      </div>

      {/* Models Table */}
      <div className="panel">
        <h2 className="panel-title mb-4">Model Registry</h2>
        
        {loading ? (
          <div className="text-center py-8">
            <div className="animate-pulse text-muted-foreground">Loading models...</div>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="table w-full">
              <thead>
                <tr>
                  <th>Version</th>
                  <th>Created</th>
                  <th>Params</th>
                  <th>Samples</th>
                  <th>Val Loss</th>
                  <th>Size</th>
                  <th>Status</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {models.map((model) => (
                  <tr key={model.id}>
                    <td className="mono font-medium text-foreground">{model.version}</td>
                    <td>{model.created}</td>
                    <td className="mono">{formatParams(model.parameters)}</td>
                    <td className="mono">{model.samples.toLocaleString()}</td>
                    <td className="mono">{formatLoss(model.val_loss)}</td>
                    <td className="mono">{model.size}</td>
                    <td>
                      {model.has_weights ? (
                        <span className="badge badge-success text-xs">Ready</span>
                      ) : (
                        <span className="badge text-xs">Metadata Only</span>
                      )}
                    </td>
                    <td>
                      <div className="flex gap-1">
                        <button 
                          className="btn btn-ghost btn-sm"
                          onClick={() => setSelectedModel(model)}
                          aria-label="View details"
                        >
                          <Settings size={14} />
                        </button>
                        <button className="btn btn-ghost btn-sm" aria-label="Download">
                          <Download size={14} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Model Details Modal */}
      {selectedModel && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-card border border-border rounded-lg p-6 w-full max-w-md">
            <h3 className="text-lg font-semibold text-foreground mb-4">Model Details</h3>
            <div className="space-y-3">
              <div>
                <span className="text-sm text-muted-foreground">Version</span>
                <div className="font-mono text-foreground">{selectedModel.version}</div>
              </div>
              <div>
                <span className="text-sm text-muted-foreground">Created</span>
                <div className="text-foreground">{selectedModel.created}</div>
              </div>
              <div>
                <span className="text-sm text-muted-foreground">Parameters</span>
                <div className="mono text-foreground">{formatParams(selectedModel.parameters)}</div>
              </div>
              <div>
                <span className="text-sm text-muted-foreground">Validation Loss</span>
                <div className="mono text-success">{formatLoss(selectedModel.val_loss)}</div>
              </div>
              <div>
                <span className="text-sm text-muted-foreground">Training Samples</span>
                <div className="mono text-foreground">{selectedModel.samples.toLocaleString()}</div>
              </div>
              <div>
                <span className="text-sm text-muted-foreground">File Size</span>
                <div className="mono text-foreground">{selectedModel.size}</div>
              </div>
            </div>
            <div className="flex justify-end gap-2 mt-6">
              <button 
                className="btn btn-ghost"
                onClick={() => setSelectedModel(null)}
              >
                Cancel
              </button>
              <button className="btn btn-primary">
                Download
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

interface ModelStatCardProps {
  title: string
  value: string | number
  status?: 'ok' | 'warning' | 'neutral'
}

function ModelStatCard({ title, value, status = 'neutral' }: ModelStatCardProps) {
  const colors = {
    ok: 'text-success',
    warning: 'text-warning',
    neutral: 'text-foreground',
  }

  return (
    <div className="panel text-center">
      <div className={`text-xl font-bold ${colors[status]}`}>{value}</div>
      <div className="text-xs text-muted-foreground">{title}</div>
    </div>
  )
}