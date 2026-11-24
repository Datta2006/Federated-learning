import { useEffect, useState } from 'react'
import { ThermometerSun, Droplet, Cloud, WindIcon } from 'lucide-react'
import { StatCard } from '@/components/cards/StatCard'
import { StatusBadge } from '@/components/cards/StatusBadge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle, CardFooter } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, AreaChart, Area, PieChart, Pie, Cell } from 'recharts'
import { useExperimentStore } from '@/stores/experimentStore'
import { cn } from '@/lib/utils'

interface AirQualityReading {
  timestamp: string
  aqi: number
  pm25: number
  pm10: number
  no2: number
  so2: number
  co: number
  o3: number
  temperature: number
  humidity: number
  wind_speed: number
  pressure: number
}

interface ForecastingPoint {
  time: string
  aqi: number
  confidence: number
}

// Generate mock air quality data
const generateAirQualityData = (hours: number): AirQualityReading[] => {
  const data: AirQualityReading[] = []
  const baseAQI = 45 + Math.random() * 30
  const now = Date.now()

  for (let i = hours; i >= 0; i--) {
    const time = new Date(now - i * 60 * 60 * 1000)
    const variation = Math.sin(i / 4) * 15 + Math.random() * 10

    data.push({
      timestamp: time.toISOString(),
      aqi: Math.max(0, Math.min(500, baseAQI + variation)),
      pm25: Math.max(0, Math.min(150, 20 + variation * 0.8)),
      pm10: Math.max(0, Math.min(250, 35 + variation)),
      no2: Math.max(0, Math.min(200, 25 + variation * 0.5)),
      so2: Math.max(0, Math.min(100, 15 + variation * 0.3)),
      co: Math.max(0, Math.min(50, 0.5 + variation * 0.05)),
      o3: Math.max(0, Math.min(300, 40 + variation * 0.8)),
      temperature: 22 + Math.sin(i / 24) * 8 + Math.random() * 3,
      humidity: 60 + Math.random() * 20 - 10,
      wind_speed: 5 + Math.random() * 10,
      pressure: 1013 + Math.random() * 10 - 5,
    })
  }
  return data
}

// Generate forecast data
const generateForecastData = (hours: number): ForecastingPoint[] => {
  const currentAQI = 68 // Current base AQI
  const forecast: ForecastingPoint[] = []

  for (let i = 0; i <= hours; i++) {
    const time = new Date(Date.now() + i * 60 * 60 * 1000)
    const forecastAQI = currentAQI + Math.sin(i / 6) * 10 + Math.random() * 5
    const confidence = Math.max(0.6, 1 - i / (hours * 3))

    const timeStr = time.toISOString()
    const timeParts = timeStr.split('T')
    const timeComponent = timeParts[1] ? timeParts[1].slice(0, 5) : '00:00'

    forecast.push({
      time: timeComponent,
      aqi: Math.max(0, Math.min(500, forecastAQI)),
      confidence: confidence,
    })
  }
  return forecast
}

const formatAQI = (aqi: number) => {
  if (aqi <= 50) return { level: 'Good', color: 'text-success-600', bg: 'bg-success-100' }
  if (aqi <= 100) return { level: 'Moderate', color: 'text-amber-600', bg: 'bg-amber-100' }
  if (aqi <= 150) return { level: 'Unhealthy for Sensitive', color: 'text-orange-600', bg: 'bg-orange-100' }
  if (aqi <= 200) return { level: 'Unhealthy', color: 'text-destructive-600', bg: 'bg-destructive-100' }
  if (aqi <= 300) return { level: 'Very Unhealthy', color: 'text-purple-600', bg: 'bg-purple-100' }
  return { level: 'Hazardous', color: 'text-red-600', bg: 'bg-red-100' }
}

const AQI_CATEGORIES = ['Good', 'Moderate', 'Unhealthy for Sensitive', 'Unhealthy', 'Very Unhealthy', 'Hazardous']

export function AirQualityPage() {
  const { experiments } = useExperimentStore()
  const [airQualityData, setAirQualityData] = useState<AirQualityReading[]>([])
  const [forecastData, setForecastData] = useState<ForecastingPoint[]>([])
  const [timeRange, setTimeRange] = useState<'24h' | '7d' | '30d'>('24h')
  const [activeTab, setActiveTab] = useState<'current' | 'historical' | 'forecast'>('current')

  useEffect(() => {
    const hours = timeRange === '24h' ? 24 : timeRange === '7d' ? 168 : 720
    setAirQualityData(generateAirQualityData(hours))
    setForecastData(generateForecastData(timeRange === '24h' ? 24 : 48))
  }, [timeRange])

  const currentReading = airQualityData[0]
  const aqiInfo = formatAQI(currentReading?.aqi || 0)

  const avgAQI = airQualityData.reduce((sum, r) => sum + r.aqi, 0) / airQualityData.length
  const avgPM25 = airQualityData.reduce((sum, r) => sum + r.pm25, 0) / airQualityData.length
  const avgTemp = airQualityData.reduce((sum, r) => sum + r.temperature, 0) / airQualityData.length
  const avgHumidity = airQualityData.reduce((sum, r) => sum + r.humidity, 0) / airQualityData.length

  const historicalPMData = airQualityData.map(r => ({
    time: new Date(r.timestamp).toLocaleTimeString([], { hour: '2-digit' }),
    PM25: r.pm25,
    PM10: r.pm10,
  }))

  const forecastChartData = forecastData.map(f => ({
    time: f.time,
    AQI: f.aqi,
    Confidence: Math.round(f.confidence * 100),
  }))

  const pollutantData = [
    { name: 'PM2.5', value: currentReading?.pm25 ?? 0 },
    { name: 'PM10', value: currentReading?.pm10 ?? 0 },
    { name: 'NO2', value: currentReading?.no2 ?? 0 },
    { name: 'O3', value: currentReading?.o3 ?? 0 },
    { name: 'SO2', value: currentReading?.so2 ?? 0 },
  ]

  const COLORS = ['#0ea5e9', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6']

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-3xl font-bold tracking-tight text-foreground">
            Air Quality Monitoring
          </h2>
          <p className="text-muted-foreground">
            Real-time air quality data and forecasting
          </p>
        </div>
        <Select value={timeRange} onValueChange={setTimeRange as any}>
          <SelectTrigger className="w-[120px]">
            <SelectValue placeholder="Select range" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="24h">Last 24 Hours</SelectItem>
            <SelectItem value="7d">Last 7 Days</SelectItem>
            <SelectItem value="30d">Last 30 Days</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Current Readings Stats */}
      <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-4">
        <StatCard
          title="Air Quality Index"
          value={`${currentReading?.aqi || 0}`}
          description={aqiInfo.level}
          icon={<Cloud className="h-4 w-4" />}
          gradient
        />
        <StatCard
          title="PM2.5"
          value={`${currentReading?.pm25?.toFixed(1) || 0} μg/m³`}
          description="Particulate Matter"
          icon={<WindIcon className="h-4 w-4" />}
        />
        <StatCard
          title="Temperature"
          value={`${currentReading?.temperature?.toFixed(1) || 0}°C`}
          description="Current temperature"
          icon={<ThermometerSun className="h-4 w-4" />}
        />
        <StatCard
          title="Humidity"
          value={`${currentReading?.humidity?.toFixed(1) || 0}%`}
          description="Air humidity"
          icon={<Droplet className="h-4 w-4" />}
        />
      </div>

      {/* AQI Level Indicator */}
      <Card>
        <CardHeader>
          <CardTitle>Air Quality Index Details</CardTitle>
          <CardDescription>Current air quality assessment</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex items-center gap-6">
            <div className="text-center">
              <div className={`text-3xl font-bold ${aqiInfo.color}`}>
                {currentReading?.aqi || 0}
              </div>
              <StatusBadge status={aqiInfo.level === 'Good' ? 'completed' : aqiInfo.level === 'Moderate' ? 'warning' : 'critical'} />
            </div>
            <div className="flex-1 space-y-3">
              {[
                { label: 'PM2.5', value: currentReading?.pm25, unit: 'μg/m³', safe: 12 },
                { label: 'PM10', value: currentReading?.pm10, unit: 'μg/m³', safe: 54 },
                { label: 'Ozone (O3)', value: currentReading?.o3, unit: 'ppb', safe: 70 },
                { label: 'Nitrogen Dioxide (NO2)', value: currentReading?.no2, unit: 'ppb', safe: 100 },
                { label: 'Sulfur Dioxide (SO2)', value: currentReading?.so2, unit: 'ppb', safe: 35 },
              ].map(pollutant => (
                <div key={pollutant.label} className="flex items-center justify-between">
                  <span className="text-sm text-muted-foreground">{pollutant.label}</span>
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium">
                      {pollutant.value?.toFixed(1) || 0} {pollutant.unit}
                    </span>
                    {pollutant.value && pollutant.value > pollutant.safe ? (
                      <AlertLevel status="high" />
                    ) : (
                      <AlertLevel status="ok" />
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab as any} className="space-y-4">
        <TabsList className="grid w-full grid-cols-3">
          <TabsTrigger value="current">Current</TabsTrigger>
          <TabsTrigger value="historical">Historical</TabsTrigger>
          <TabsTrigger value="forecast">Forecast</TabsTrigger>
        </TabsList>

        <TabsContent value="current">
          <div className="grid gap-6 lg:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle>AQI Over Time</CardTitle>
                <CardDescription>Last 24 hours</CardDescription>
              </CardHeader>
              <CardContent>
                <ResponsiveContainer width="100%" height={250}>
                  <AreaChart data={historicalPMData}>
                    <CartesianGrid strokeDasharray="3 3" opacity={0.1} />
                    <XAxis dataKey="time" />
                    <YAxis />
                    <Tooltip />
                    <Area
                      type="monotone"
                      dataKey="AQI"
                      stackId="1"
                      stroke="#0ea5e9"
                      fill="rgba(14, 165, 233, 0.3)"
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Top Pollutants</CardTitle>
                <CardDescription>Contribution breakdown</CardDescription>
              </CardHeader>
              <CardContent>
                <ResponsiveContainer width="100%" height={250}>
                  <PieChart>
                    <Pie
                      data={pollutantData}
                      cx="50%"
                      cy="50%"
                      innerRadius={40}
                      outerRadius={80}
                      paddingAngle={5}
                      dataKey="value"
                      nameKey="name"
                      label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
                    >
                      {pollutantData.map((entry, index) => (
                        <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip formatter={(value: number) => `${value.toFixed(1)} μg/m³`} />
                  </PieChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="historical">
          <Card>
            <CardHeader>
              <CardTitle>Historical Air Quality</CardTitle>
              <CardDescription>Detailed pollutant trends</CardDescription>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={300}>
                <LineChart data={historicalPMData}>
                  <CartesianGrid strokeDasharray="3 3" opacity={0.1} />
                  <XAxis dataKey="time" />
                  <YAxis />
                  <Tooltip />
                  <Legend />
                  <Line type="monotone" dataKey="PM2.5" stroke="#0ea5e9" strokeWidth={2} dot={{ r: 3 }} />
                  <Line type="monotone" dataKey="PM10" stroke="#10b981" strokeWidth={2} dot={{ r: 3 }} />
                </LineChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="forecast">
          <div className="grid gap-6 lg:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle>AQI Forecast</CardTitle>
                <CardDescription>Predicted air quality for next 48 hours</CardDescription>
              </CardHeader>
              <CardContent>
                <ResponsiveContainer width="100%" height={250}>
                  <LineChart data={forecastChartData}>
                    <CartesianGrid strokeDasharray="3 3" opacity={0.1} />
                    <XAxis dataKey="time" />
                    <YAxis domain={[0, 150]} />
                    <Tooltip formatter={(value: number, name: string) => `${value.toFixed(1)} ${name === 'AQI' ? 'AQI' : 'Confidence%'}`} />
                    <Legend />
                    <Line
                      type="monotone"
                      dataKey="AQI"
                      stroke="#0ea5e9"
                      strokeWidth={3}
                      dot={{ r: 4 }}
                      name="AQI"
                    />
                    <Area
                      type="monotone"
                      dataKey="Confidence"
                      stroke="transparent"
                      fill="rgba(14, 165, 233, 0.1)"
                      yAxisId="right"
                      name="Confidence"
                    />
                  </LineChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Forecast Summary</CardTitle>
                <CardDescription>Expectations for next 24 hours</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <p className="text-sm text-muted-foreground mb-1">Max AQI</p>
                    <p className="text-xl font-bold">
                      {Math.max(...forecastData.map(f => f.aqi)).toFixed(0)}
                    </p>
                  </div>
                  <div>
                    <p className="text-sm text-muted-foreground mb-1">Min AQI</p>
                    <p className="text-xl font-bold">
                      {Math.min(...forecastData.map(f => f.aqi)).toFixed(0)}
                    </p>
                  </div>
                  <div>
                    <p className="text-sm text-muted-foreground mb-1">Avg Confidence</p>
                    <p className="text-xl font-bold">
                      {(forecastData.reduce((sum, f) => sum + f.confidence, 0) / forecastData.length * 100).toFixed(0)}%
                    </p>
                  </div>
                  <div>
                    <p className="text-sm text-muted-foreground mb-1">Worst Period</p>
                    <p className="text-xl font-bold">Afternoon</p>
                  </div>
                </div>
              </CardContent>
              <CardFooter>
                <Button className="w-full">View Full Forecast</Button>
              </CardFooter>
            </Card>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  )
}

const AlertLevel = ({ status }: { status: 'ok' | 'high' }) => (
  <div
    className={cn(
      'w-2 h-2 rounded-full',
      status === 'ok' ? 'bg-success-500' : 'bg-destructive-500'
    )}
  />
)