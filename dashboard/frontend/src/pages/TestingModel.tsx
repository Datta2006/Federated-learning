import { useState, useEffect, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { Panel, Stat, Empty, Badge } from "@/components/primitives";
import { apiGet, apiPost } from "../lib/api";

interface PredictionResponse {
  predictions: number[];
  model_version: string;
  input: number[];
  output_shape: number;
  confidence?: number;
  latency_ms: number;
  explanation: string;
}

interface ModelVersion {
  model_version: string;
  parameters: number;
  weighted_val_loss: number | null;
}

interface ModelsResponse {
  available: boolean;
  versions: ModelVersion[];
  latest?: { model_version: string; parameters: number } | null;
  best?: { model_version: string; parameters: number } | null;
}

// EPA Air Quality Index levels for PM2.5 (µg/m³)
interface PollutionLevel {
  level: string;
  min: number;
  max: number;
  color: "ok" | "warn" | "bad";
  advice: string;
}

const POLLUTION_LEVELS: PollutionLevel[] = [
  { level: "Good", min: 0, max: 12, color: "ok", advice: "Air quality is satisfactory, with minimal risk." },
  { level: "Moderate", min: 12.1, max: 35.4, color: "warn", advice: "Air quality is acceptable, but some pollutants may be a concern for a very small number of sensitive individuals." },
  { level: "Unhealthy for Sensitive Groups", min: 35.5, max: 55.4, color: "bad", advice: "Members of sensitive groups may experience health effects. The general public is unlikely to be affected." },
  { level: "Unhealthy", min: 55.5, max: 150.4, color: "bad", advice: "Everyone may begin to experience health effects; members of sensitive groups may experience more serious health effects." },
  { level: "Very Unhealthy", min: 150.5, max: 250.4, color: "bad", advice: "Health warnings of emergency conditions. The entire population is likely to be affected." },
  { level: "Hazardous", min: 250.5, max: 500, color: "bad", advice: "Emergency conditions. Everyone is likely to be affected." },
];

function getPollutionLevel(pm25: number): PollutionLevel {
  for (const level of POLLUTION_LEVELS) {
    if (pm25 >= level.min && pm25 <= level.max) {
      return level;
    }
  }
  // Return last level as default (Hazardous for values > 500)
  const lastLevel = POLLUTION_LEVELS[POLLUTION_LEVELS.length - 1];
  return lastLevel ?? { level: "Hazardous", min: 250.5, max: 500, color: "bad", advice: "Emergency conditions. Everyone is likely to be affected." };
}

// Helper function to get color styles for pollution level
function getPolutionLevelStyle(color: PollutionLevel["color"]): string {
  switch (color) {
    case "ok":
      return "bg-green-100 dark:bg-green-900/30 border-green-300 dark:border-green-700";
    case "warn":
      return "bg-amber-100 dark:bg-amber-900/30 border-amber-300 dark:border-amber-700";
    case "bad":
      return "bg-red-100 dark:bg-red-900/30 border-red-300 dark:border-red-700";
    default:
      return "bg-muted";
  }
}

export function TestingModelPage() {
  const [input, setInput] = useState<number[]>([0.5, 0.3, 0.7, 0.2, 0.9]);
  const [modelVersion, setModelVersion] = useState<string>("");
  const [prediction, setPrediction] = useState<PredictionResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Fetch models state
  const [modelsData, setModelsData] = useState<ModelsResponse | null>(null);
  const [modelsLoading, setModelsLoading] = useState(true);

  // Fetch models function
  const fetchModels = useCallback(async (): Promise<ModelsResponse> => {
    return await apiGet<ModelsResponse>("/api/models/demo");
  }, []);

  // Fetch models on component mount
  useEffect(() => {
    fetchModels()
      .then((data) => {
        setModelsData(data);
        if (!data.available || !data.versions || data.versions.length === 0) {
          setModelVersion("v1");
        } else {
          const firstVersion = data.versions[0];
          if (firstVersion) {
            setModelVersion(firstVersion.model_version);
          } else {
            setModelVersion("v1");
          }
        }
      })
      .catch(() => {
        setModelsData(null);
        setModelVersion("v1");
      })
      .finally(() => {
        setModelsLoading(false);
      });
  }, [fetchModels]);

  const handlePredict = async () => {
    if (!modelVersion.trim()) {
      setError("Please select a model version");
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const response = await apiPost<PredictionResponse>("/api/predict/demo", {
        model_version: modelVersion,
        input: input,
      });
      setPrediction(response);
    } catch (err: any) {
      setError(err.message || "Prediction failed");
      setPrediction(null);
    } finally {
      setLoading(false);
    }
  };

  const generateRandomInput = (count: number = 5) => {
    const randomValues = Array.from({ length: count }, () =>
      parseFloat((Math.random() * 0.9 + 0.05).toFixed(4))
    );
    setInput(randomValues);
  };

  const availableModels = modelsData?.versions || [];
  const isDemoMode = !modelsData?.available || !modelsData;

  return (
    <div className="stack">
      {/* Header */}
      <div className="page-head">
        <div>
          <h1 className="page-title">Model Testing Lab</h1>
          <p className="page-sub">
            Generate random input data and test model predictions live. Perfect for
            demonstrations and debugging federated learning workflows.
          </p>
        </div>
        <div className="toolbar">
          <Badge tone={modelsData?.available ? "ok" : "warn"}>
            {modelsData?.available ? "API Connected" : "Demo Mode"}
          </Badge>
        </div>
      </div>

      {error && <div className="notice notice-bad">{error}</div>}

      {/* Main Content - Two columns */}
      <div className="cols-2">
        {/* Left Column - Input Configuration */}
        <Panel title="Input Configuration" subtitle="Configure test input and select model">
          {/* Loading State */}
          {modelsLoading ? (
            <div className="py-4 text-center">
              <p className="text-sm text-muted-foreground">Loading model registry...</p>
            </div>
          ) : isDemoMode ? (
            <div className="stack">
              <div className="py-4 text-center">
                <p className="text-sm text-muted-foreground mb-2">
                  Demo Mode - API simulation enabled
                </p>
              </div>
              <div>
                <label className="text-sm font-medium text-foreground mb-1 block">
                  Model Version
                </label>
                <input
                  type="text"
                  value={modelVersion}
                  onChange={(e) => setModelVersion(e.target.value)}
                  className="input w-full"
                  placeholder="Enter a model version (e.g., v1)"
                />
              </div>
              <div>
                <label className="text-sm font-medium text-foreground mb-2 block">
                  Input Features
                </label>
                <div className="flex gap-2 flex-wrap">
                  {input.map((val, idx) => (
                    <input
                      key={idx}
                      type="number"
                      step="0.01"
                      min="0"
                      max="1"
                      value={val}
                      onChange={(e) => {
                        const newInput = [...input];
                        newInput[idx] = parseFloat(e.target.value);
                        setInput(newInput);
                      }}
                      className="input w-16 text-sm"
                    />
                  ))}
                </div>
                <p className="text-xs text-muted-foreground mt-1">
                  {input.length} features • Range: 0.0 - 1.0
                </p>
              </div>
              <div className="flex gap-2">
                <Button
                  type="button"
                  onClick={() => setInput([0.5, 0.3, 0.7, 0.2, 0.9])}
                  variant="outline"
                >
                  Reset to Default Values
                </Button>
                <Button
                  type="button"
                  onClick={handlePredict}
                  disabled={loading || !modelVersion.trim()}
                >
                  {loading ? "Predicting..." : "Run Prediction"}
                </Button>
              </div>
            </div>
          ) : availableModels.length === 0 ? (
            <Empty title="No models available" hint="Train or register a model first." />
          ) : (
            <div className="stack">
              {/* Model Selection */}
              <div className="cols-2">
                <div>
                  <label className="text-sm font-medium text-foreground mb-1 block">
                    Model Version
                  </label>
                  <select
                    value={modelVersion}
                    onChange={(e) => setModelVersion(e.target.value)}
                    className="input w-full"
                  >
                    <option value="">-- Select a model --</option>
                    {availableModels.map((model) => (
                      <option key={model.model_version} value={model.model_version}>
                        {model.model_version} ({model.parameters.toLocaleString()} params)
                        {model.weighted_val_loss != null && (
                          <span className="text-muted-foreground text-xs">
                            {" "}
                            — loss: {model.weighted_val_loss.toFixed(4)}
                          </span>
                        )}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="flex gap-2">
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => generateRandomInput(5)}
                  >
                    Random (5)
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => generateRandomInput(7)}
                  >
                    Random (7)
                  </Button>
                </div>
              </div>

              {/* Input Values */}
              <div>
                <label className="text-sm font-medium text-foreground mb-2 block">
                  Input Features
                </label>
                <div className="flex gap-2 flex-wrap">
                  {input.map((val, idx) => (
                    <input
                      key={idx}
                      type="number"
                      step="0.01"
                      min="0"
                      max="1"
                      value={val}
                      onChange={(e) => {
                        const newInput = [...input];
                        newInput[idx] = parseFloat(e.target.value);
                        setInput(newInput);
                      }}
                      className="input w-16 text-sm"
                    />
                  ))}
                  <input
                    type="text"
                    value={input.join(", ")}
                    onChange={(e) => {
                      const values = e.target.value
                        .split(",")
                        .map((s) => parseFloat(s.trim()))
                        .filter((n) => !isNaN(n) && n >= 0 && n <= 1);
                      setInput(values.slice(0, 10));
                    }}
                    className="input flex-1 text-sm"
                    placeholder="Or paste: 0.1, 0.5, 0.9, ..."
                  />
                </div>
                <p className="text-xs text-muted-foreground mt-1">
                  {input.length} features • Range: 0.0 - 1.0
                </p>
              </div>

              {/* Predict Button */}
              <div>
                <Button
                  type="button"
                  onClick={handlePredict}
                  disabled={loading || !modelVersion.trim()}
                >
                  {loading ? "Predicting..." : "Run Prediction"}
                </Button>
              </div>
            </div>
          )}
        </Panel>

        {/* Right Column - Quick Demo */}
        <Panel title="Quick Demo" subtitle="One-click demo predictions">
          <div className="stack">
            <Button
              type="button"
              variant="outline"
              onClick={() => {
                if (availableModels.length > 0 && availableModels[0]?.model_version) {
                  setModelVersion(availableModels[0].model_version);
                  generateRandomInput(5);
                } else {
                  setModelVersion("v1");
                  generateRandomInput(3);
                }
              }}
            >
              Load Demo Model
            </Button>
            <Button
              type="button"
              variant="outline"
              onClick={() => generateRandomInput(5)}
            >
              Random Input (5)
            </Button>
            <Button
              type="button"
              variant="outline"
              onClick={() => generateRandomInput(7)}
            >
              Random Input (7)
            </Button>
          </div>
        </Panel>
      </div>

      {/* Prediction Results */}
      {prediction && (
        <Panel title="Prediction Results" subtitle={`Model v${modelVersion}`} bodyTight>
          <div className="stat-grid">
            <Stat
              label="PM2.5 Prediction"
              value={prediction.predictions.map((p) => p.toFixed(1)).join(", ")}
              sub="µg/m³ (particles per cubic meter)"
            />
            <Stat
              label="Confidence"
              value={prediction.confidence != null ? `${prediction.confidence}%` : "N/A"}
            />
            <Stat
              label="Latency"
              value={prediction.latency_ms.toString()}
              sub="ms"
            />
          </div>

          {/* Pollution Level Indicator */}
          {prediction.predictions.length > 0 && (
            (() => {
              const pm25Value = prediction.predictions[0];
              if (pm25Value === undefined) return null;
              const level = getPollutionLevel(pm25Value);
              return (
                <div className={`mt-4 p-3 rounded border ${getPolutionLevelStyle(level.color)}`}>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Badge tone={level.color === "ok" ? "ok" : level.color === "warn" ? "warn" : "bad"}>
                        {level.level} (PM2.5: {pm25Value.toFixed(1)} µg/m³)
                      </Badge>
                    </div>
                  </div>
                  <p className="text-xs text-muted-foreground mt-2">{level.advice}</p>
                  <div className="mt-2 text-xs text-muted-foreground">
                    <span className="font-medium">EPA Scale:</span>{" "}
                    {level.min === 0 ? "0" : level.min.toFixed(1)} - {level.max.toFixed(1)} µg/m³
                  </div>
                </div>
              );
            })()
          )}

          <div className="mt-4 p-3 bg-muted rounded">
            <div className="text-sm">
              <div className="flex gap-4">
                <div>
                  <span className="text-muted-foreground mr-2">Input:</span>
                  <span className="mono">{prediction.input.join(", ")}</span>
                </div>
                <div>
                  <span className="text-muted-foreground mr-2">Output:</span>
                  <span className="mono">
                    [{prediction.predictions.map((p) => p.toFixed(1)).join(", ")}]
                  </span>
                </div>
              </div>
            </div>
          </div>

          {prediction.explanation && (
            <div className="mt-3 p-3 bg-muted/50 rounded">
              <p className="text-xs text-muted-foreground">
                <strong>Explanation:</strong> {prediction.explanation}
              </p>
            </div>
          )}
        </Panel>
      )}

      {/* Info Section */}
      <Panel title="About" subtitle="Learning model testing workflow">
        <div className="text-sm text-muted-foreground">
          <p className="mb-2">
            This page demonstrates how to test federated learning models with random
            input data. The model predicts PM2.5 air quality values from input features
            (normalized values between 0 and 1).
          </p>
          <ul className="list-disc list-inside text-xs space-y-1 ml-4">
            <li>Input: 5-7 normalized features (e.g., PM2.5, temperature, humidity)</li>
            <li>Model: CNN-RNN architecture for time-series prediction</li>
            <li>Output: Single PM2.5 value prediction (µg/m³)</li>
          </ul>
        </div>
      </Panel>
    </div>
  );
}