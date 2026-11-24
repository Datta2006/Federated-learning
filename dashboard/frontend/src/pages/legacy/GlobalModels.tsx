import { useEffect, useState } from 'react'
import { Layers, GitBranch, CheckCircle, Clock, Download, ExternalLink, History } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle, CardFooter } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Progress } from '@/components/ui/progress'
import { useExperimentStore } from '@/stores/experimentStore'

interface GlobalModel {
  model_id: string
  name: string
  version: string
  created_at: string
  framework: string
  parameters?: number
  architecture?: string
  training_experiments?: number
  performance_metrics?: {
    accuracy?: number
    loss?: number
    f1_score?: number
  }
  file_size?: string
  download_url?: string
  status: 'active' | 'deprecated' | 'archived'
}

// Generate mock model data
const generateModelData = (): GlobalModel[] => {
  return [
    {
      model_id: 'model-v1',
      name: 'AirFed ResNet18',
      version: '1.0.0',
      created_at: new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString(),
      framework: 'PyTorch',
      parameters: 11_000_000,
      architecture: 'ResNet18',
      training_experiments: 3,
      performance_metrics: { accuracy: 0.945, loss: 0.152, f1_score: 0.938 },
      file_size: '45.2 MB',
      download_url: '/models/resnet18-v1.0.0.pt',
      status: 'active',
    },
    {
      model_id: 'model-v2',
      name: 'AirFed EfficientNet',
      version: '1.1.0',
      created_at: new Date(Date.now() - 3 * 24 * 60 * 60 * 1000).toISOString(),
      framework: 'TensorFlow',
      parameters: 5_300_000,
      architecture: 'EfficientNet-B0',
      training_experiments: 2,
      performance_metrics: { accuracy: 0.962, loss: 0.118, f1_score: 0.958 },
      file_size: '28.5 MB',
      download_url: '/models/efficientnet-v1.1.0.pb',
      status: 'active',
    },
    {
      model_id: 'model-v3',
      name: 'AirFed MobileNet',
      version: '1.0.0',
      created_at: new Date(Date.now() - 5 * 24 * 60 * 60 * 1000).toISOString(),
      framework: 'PyTorch',
      parameters: 3_500_000,
      architecture: 'MobileNetV3',
      training_experiments: 1,
      performance_metrics: { accuracy: 0.921, loss: 0.189, f1_score: 0.915 },
      file_size: '19.8 MB',
      download_url: '/models/mobilenet-v1.0.0.pt',
      status: 'deprecated',
    },
    {
      model_id: 'model-v4',
      name: 'AirFed Custom CNN',
      version: '1.1.0',
      created_at: new Date(Date.now() - 2 * 24 * 60 * 60 * 1000).toISOString(),
      framework: 'TensorFlow',
      parameters: 2_800_000,
      architecture: 'Custom CNN',
      training_experiments: 2,
      performance_metrics: { accuracy: 0.955, loss: 0.134, f1_score: 0.951 },
      file_size: '15.3 MB',
      download_url: '/models/custom-cnn-v1.1.0.pb',
      status: 'active',
    },
  ]
}

const formatParams = (params: number) => {
  if (params >= 1e9) return `${(params / 1e9).toFixed(2)}B`
  if (params >= 1e6) return `${(params / 1e6).toFixed(2)}M`
  if (params >= 1e3) return `${(params / 1e3).toFixed(1)}K`
  return params.toString()
}

export function GlobalModelsPage() {
  const { experiments } = useExperimentStore()
  const [models, setModels] = useState<GlobalModel[]>([])
  const [searchTerm, setSearchTerm] = useState('')
  const [modelFilter, setModelFilter] = useState<'all' | 'active' | 'deprecated'>('all')

  useEffect(() => {
    setModels(generateModelData())
  }, [])

  const filteredModels = models.filter(model => {
    const matchesSearch = model.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
                          model.version.toLowerCase().includes(searchTerm.toLowerCase()) ||
                          model.model_id.toLowerCase().includes(searchTerm.toLowerCase())
    const matchesFilter = modelFilter === 'all' || model.status === modelFilter
    return matchesSearch && matchesFilter
  })

  const activeModels = models.filter(m => m.status === 'active')
  const totalParams = models.reduce((sum, m) => sum + (m.parameters || 0), 0)

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-3xl font-bold tracking-tight text-foreground">
            Global Models
          </h2>
          <p className="text-muted-foreground">
            Manage model versions and track performance
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant="outline" className="text-xs">
            {activeModels.length} Active Models
          </Badge>
        </div>
      </div>

      {/* Stats */}
      <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">Model Versions</CardTitle>
            <GitBranch className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{models.length}</div>
            <p className="text-xs text-muted-foreground">+2 this week</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">Total Parameters</CardTitle>
            <Layers className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{formatParams(totalParams)}</div>
            <p className="text-xs text-muted-foreground">Across all models</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">Best Accuracy</CardTitle>
            <CheckCircle className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">96.2%</div>
            <p className="text-xs text-muted-foreground">EfficientNet-B0 v1.1.0</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">Avg Test Time</CardTitle>
            <Clock className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">1.4s</div>
            <p className="text-xs text-muted-foreground">Per inference</p>
          </CardContent>
        </Card>
      </div>

      {/* Controls */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Input
            type="search"
            placeholder="Search models..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="h-9 w-[300px]"
          />
          <Select value={modelFilter} onValueChange={setModelFilter as any}>
            <SelectTrigger className="h-9 w-[150px]">
              <SelectValue placeholder="Filter by status" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Models</SelectItem>
              <SelectItem value="active">Active</SelectItem>
              <SelectItem value="deprecated">Deprecated</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <Button>
          <GitBranch className="mr-2 h-4 w-4" />
          Create New Model
        </Button>
      </div>

      {/* Models Grid */}
      <div className="grid gap-6 lg:grid-cols-2">
        {filteredModels.map((model) => (
          <Card key={model.model_id} className="hover:shadow-md transition-shadow">
            <CardHeader>
              <div className="flex items-start justify-between">
                <div className="space-y-1">
                  <CardTitle className="text-xl">{model.name}</CardTitle>
                  <CardDescription>
                    v{model.version} • {model.framework}
                  </CardDescription>
                </div>
                <StatusBadge status={model.status === 'active' ? 'running' : 'completed'} />
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-3 gap-4 text-center">
                <div>
                  <p className="text-2xl font-bold text-foreground">
                    {model.performance_metrics?.accuracy?.toFixed(1) || '-'}%
                  </p>
                  <p className="text-xs text-muted-foreground">Accuracy</p>
                </div>
                <div>
                  <p className="text-2xl font-bold text-foreground">
                    {formatParams(model.parameters || 0)}
                  </p>
                  <p className="text-xs text-muted-foreground">Parameters</p>
                </div>
                <div>
                  <p className="text-2xl font-bold text-foreground">
                    {model.file_size}
                  </p>
                  <p className="text-xs text-muted-foreground">Model Size</p>
                </div>
              </div>

              <div>
                <div className="mb-2 flex items-center justify-between">
                  <span className="text-sm text-muted-foreground">Performance Score</span>
                  <span className="text-sm font-medium">
                    {((model.performance_metrics?.accuracy || 0) * 100 / 100).toFixed(1)}
                  </span>
                </div>
                <Progress value={(model.performance_metrics?.accuracy || 0) * 100} />
              </div>

              <div className="text-xs text-muted-foreground">
                <p>Architecture: {model.architecture}</p>
                <p>Trained on {model.training_experiments || 1} experiment{model.training_experiments !== 1 ? 's' : ''}</p>
                <p>Created: {new Date(model.created_at).toLocaleDateString()}</p>
              </div>
            </CardContent>
            <CardFooter className="border-t border-border p-4">
              <div className="flex items-center justify-between w-full">
                <div className="flex items-center gap-1 text-xs text-muted-foreground">
                  <History className="h-3 w-3" />
                  <span>Last updated: 2 days ago</span>
                </div>
                <div className="flex gap-2">
                  <Button variant="ghost" size="sm">
                    <Download className="h-4 w-4" />
                    <span className="ml-1">Download</span>
                  </Button>
                  <Button variant="ghost" size="sm">
                    <ExternalLink className="h-4 w-4" />
                    <span className="ml-1">View Details</span>
                  </Button>
                </div>
              </div>
            </CardFooter>
          </Card>
        ))}
      </div>

      {filteredModels.length === 0 && (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-12">
            <Layers className="h-12 w-12 text-muted-foreground opacity-50 mb-4" />
            <p className="text-lg font-medium text-foreground">No models found</p>
            <p className="text-sm text-muted-foreground mt-1">
              Try adjusting your search or filter criteria
            </p>
          </CardContent>
        </Card>
      )}
    </div>
  )
}

const StatusBadge = ({ status }: { status: 'active' | 'deprecated' | 'archived' | 'running' | 'completed' }) => {
  const config = {
    active: { label: 'Active', colors: 'bg-success-100 text-success-700' },
    deprecated: { label: 'Deprecated', colors: 'bg-amber-100 text-amber-700' },
    archived: { label: 'Archived', colors: 'bg-gray-100 text-gray-700' },
    running: { label: 'Running', colors: 'bg-airfed-100 text-airfed-700' },
    completed: { label: 'Completed', colors: 'bg-success-100 text-success-700' },
  }
  const badge = config[status] || config.completed
  return <Badge className={badge.colors}>{badge.label}</Badge>
}