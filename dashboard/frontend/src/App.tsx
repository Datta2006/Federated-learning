import type { ComponentType } from "react";
import { useHashRoute } from "./hooks/useHashRoute";
import { OverviewPage } from "./pages/OverviewPage";
import { WorkersPage } from "./pages/WorkersPage";
import { FederatedPage } from "./pages/FederatedPage";
import { AirQualityPage } from "./pages/AirQualityPage";
import { PerformancePage } from "./pages/PerformancePage";
import { CommunicationPage } from "./pages/CommunicationPage";

const routeLabels: Record<string, string> = {
  overview: "Overview",
  workers: "Workers",
  federated: "Federated",
  air: "Air Quality",
  performance: "Performance",
  communication: "Communication",
};

const pages: Record<string, ComponentType> = {
  overview: OverviewPage,
  workers: WorkersPage,
  federated: FederatedPage,
  air: AirQualityPage,
  performance: PerformancePage,
  communication: CommunicationPage,
};

export default function App() {
  const [route] = useHashRoute();
  const Page = pages[route] ?? OverviewPage;

  return (
    <div className="min-h-full">
      <header className="sticky top-0 z-10 border-b border-ink-700/70 bg-ink-950/85 backdrop-blur">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-4 py-3">
          <div className="flex items-baseline gap-2">
            <span className="text-sm font-semibold tracking-tight text-mist-100">AirFed</span>
            <span className="text-[11px] text-mist-500">Federated PM2.5 operations</span>
          </div>
          <nav className="flex flex-wrap items-center gap-1">
            {Object.entries(routeLabels).map(([key, label]) => (
              <a
                key={key}
                href={`#/${key}`}
                className={`btn ${route === key ? "btn-active" : ""}`}
              >
                {label}
              </a>
            ))}
          </nav>
        </div>
      </header>
      <Page />
    </div>
  );
}
