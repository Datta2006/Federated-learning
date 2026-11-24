import { useState, useEffect } from 'react'
import { Cloud, Wind, ThermometerSun, Activity, LineChart } from 'lucide-react'

interface AirQualityReading {
  location: string
  aqi: number
  pm25: number
  pm10: number
  temperature: number
  humidity: number
  timestamp: string
  status: 'good' | 'moderate' | 'unhealthy'
}

export function AirQualityPage() {
  const [readings, setReadings] = useState<AirQualityReading[]>([])
  const [loading, setLoading] = useState(true)
  const [timeRange, setTimeRange] = useState<'hour' | 'day' | 'week'>('hour')

  useEffect(() => {
    // Simulate API call
    setTimeout(() => {
      setReadings([
        {
          location: 'Data Center A',
          aqi: 85,
          pm25: 32,
          pm10: 48,
          temperature: 22.5,
          humidity: 45,
          timestamp: '2024-01-15 14:30',
          status: 'moderate',
        },
        {
          location: 'Building B',
          aqi: 42,
          pm25: 15,
          pm10: 28,
          temperature: 20.1,
          humidity: 52,
          timestamp: '2024-01-15 14:30',
          status: 'good',
        },
        {
          location: 'Building C',
          aqi: 128,
          pm25: 56,
          pm10: 78,
          temperature: 21.3,
          humidity: 48,
          timestamp: '2024-01-15 14:30',
          status: 'unhealthy',
        },
      ])
      setLoading(false)
    }, 500)
  }, [])

  const getStatusColor = (status: string) => {
    const colors = {
      good: 'text-success',
      moderate: 'text-warning',
      unhealthy: 'text-destructive',
    }
    return colors[status as keyof typeof colors] || 'text-muted-foreground'
  }

  const getStatusBadge = (status: string) => {
    const styles = {
      good: 'badge-success',
      moderate: 'badge-warning',
      unhealthy: 'badge-destructive',
    }
    return styles[status as keyof typeof styles] || 'badge'
  }

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold text-foreground">Air Quality</h1>
        <p className="text-muted-foreground mt-1">
          AQI monitoring and forecasting
        </p>
      </div>

      {/* Time Range Selector */}
      <div className="flex gap-2">
        <button
          onClick={() => setTimeRange('hour')}
          className={`btn btn-sm ${timeRange === 'hour' ? 'btn-primary' : 'btn-secondary'}`}
        >
          Last Hour
        </button>
        <button
          onClick={() => setTimeRange('day')}
          className={`btn btn-sm ${timeRange === 'day' ? 'btn-primary' : 'btn-secondary'}`}
        >
          24 Hours
        </button>
        <button
          onClick={() => setTimeRange('week')}
          className={`btn btn-sm ${timeRange === 'week' ? 'btn-primary' : 'btn-secondary'}`}
        >
          7 Days
        </button>
      </div>

      {/* AQI Overview */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <AQICard
          title="Avg AQI"
          value="90"
          status="moderate"
          icon={Cloud}
        />
        <AQICard
          title="PM2.5"
          value="34 μg/m³"
          status="moderate"
          icon={Wind}
        />
        <AQICard
          title="PM10"
          value="51 μg/m³"
          status="moderate"
          icon={Wind}
        />
        <AQICard
          title="Outdoor AQI"
          value="68"
          status="good"
          icon={Activity}
        />
      </div>

      {/* Location Readings */}
      <div className="panel">
        <h2 className="panel-title mb-4">Location Readings</h2>
        
        {loading ? (
          <div className="text-center py-8">
            <div className="animate-pulse text-muted-foreground">Loading air quality data...</div>
          </div>
        ) : (
          <div className="space-y-3">
            {readings.map((reading, idx) => (
              <div key={idx} className="border border-border rounded-lg p-4">
                <div className="flex items justify-between">
                  <div>
                    <div className="font-medium text-foreground">{reading.location}</div>
                    <div className="text-sm text-muted-foreground">
                      Last reading: {reading.timestamp}
                    </div>
                  </div>
                  
                  <div className="text-right">
                    <div className={`font-bold text-lg ${getStatusColor(reading.status)}`}>
                      AQI: {reading.aqi}
                    </div>
                    <div className="text-sm text-muted-foreground">
                      PM2.5: {reading.pm25} μg/m³ • PM10: {reading.pm10} μg/m³
                    </div>
                  </div>
                </div>
                
                <div className="mt-3 grid grid-cols-2 gap-4">
                  <div>
                    <div className="text-xs text-muted-foreground">Temperature</div>
                    <div className="font-medium">{reading.temperature}°C</div>
                  </div>
                  <div>
                    <div className="text-xs text-muted-foreground">Humidity</div>
                    <div className="font-medium">{reading.humidity}%</div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Forecast */}
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="panel">
          <h3 className="font-medium text-foreground mb-3">AQI Forecast</h3>
          <div className="border-2 border-dashed border-muted rounded-lg h-48 flex items-center justify-center">
            <div className="text-center">
              <LineChart size={48} className="mx-auto mb-2 text-muted-foreground" />
              <p className="text-muted-foreground">Forecast chart will appear here</p>
            </div>
          </div>
        </div>

        <div className="panel">
          <h3 className="font-medium text-foreground mb-3">Health Recommendations</h3>
          <div className="space-y-2">
            <div className="text-sm">
              <span className="font-medium text-foreground">Moderate:</span>
              <span className="text-muted-foreground ml-2">General public: Outdoor activity OK for most people</span>
            </div>
            <div className="text-sm">
              <span className="font-medium text-foreground">Unhealthy:</span>
              <span className="text-muted-foreground ml-2">Reduce prolonged outdoor exercise</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

interface AQICardProps {
  title: string
  value: string | number
  status: 'good' | 'moderate' | 'unhealthy'
  icon: any
}

function AQICard({ title, value, status, icon: Icon }: AQICardProps) {
  const colors = {
    good: 'text-success',
    moderate: 'text-warning',
    unhealthy: 'text-destructive',
  }

  const bgColors = {
    good: 'bg-success/10',
    moderate: 'bg-warning/10',
    unhealthy: 'bg-destructive/10',
  }

  return (
    <div className={`panel text-center border ${bgColors[status]}`}>
      <Icon size={20} className={`mx-auto mb-2 ${colors[status]}`} />
      <div className={`text-xl font-bold ${colors[status]}`}>{value}</div>
      <div className="text-xs text-muted-foreground">{title}</div>
    </div>
  )
}