import type { ComponentType } from "react";
import { useState } from "react";
import {
  Activity,
  Boxes,
  ChevronRight,
  Cpu,
  LayoutDashboard,
  Menu,
  Network,
  Radio,
  RefreshCw,
  TrendingUp,
  Wind,
  X,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { CommandCenterProvider, useCommandCenter } from "./hooks/useCommandCenter";
import { useHashRoute } from "./hooks/useHashRoute";
import type { Route } from "./hooks/useHashRoute";
import { Dot } from "./components/ui";
import { formatClock, relativeTime } from "./lib/format";
import { OverviewPage } from "./pages/OverviewPage";
import { WorkersPage } from "./pages/WorkersPage";
import { FederatedPage } from "./pages/FederatedPage";
import { GlobalModelsPage } from "./pages/GlobalModelsPage";
import { AirQualityPage } from "./pages/AirQualityPage";
import { PerformancePage } from "./pages/PerformancePage";
import { CommunicationPage } from "./pages/CommunicationPage";

const NAV: { key: Route; label: string; icon: LucideIcon }[] = [
  { key: "overview", label: "Overview", icon: LayoutDashboard },
  { key: "workers", label: "Workers", icon: Cpu },
  { key: "federated", label: "Federated", icon: Network },
  { key: "global-models", label: "Global models", icon: Boxes },
  { key: "performance", label: "Performance", icon: TrendingUp },
  { key: "air", label: "Air quality", icon: Wind },
  { key: "communication", label: "Communication", icon: Radio },
];

const PAGES: Record<Route, ComponentType> = {
  overview: OverviewPage,
  workers: WorkersPage,
  federated: FederatedPage,
  "global-models": GlobalModelsPage,
  performance: PerformancePage,
  air: AirQualityPage,
  communication: CommunicationPage,
};

function Shell() {
  const [route] = useHashRoute();
  const [menuOpen, setMenuOpen] = useState(false);
  const { status, socket, lastUpdated, refresh, loading } = useCommandCenter();
  const Page = PAGES[route] ?? OverviewPage;
  const session = status?.session_view ?? null;
  const brokerUp = status?.broker.connected ?? false;
  const workers = status?.worker_counts;
  const transport =
    socket === "open" ? "live socket" : socket === "connecting" ? "reconnecting" : "polling only";

  return (
    <div className="min-h-full lg:flex">
      <aside className="fixed inset-y-0 left-0 z-30 w-60 border-r border-line bg-panel lg:static lg:block">
        <div
          className={`${menuOpen ? "block" : "hidden"} h-full lg:block`}
          aria-label="Primary navigation"
        >
          <div className="flex h-14 items-center justify-between border-b border-line px-4">
            <a href="#/overview" className="flex items-center gap-2">
              <span className="flex h-6 w-6 items-center justify-center rounded border border-accent/40 bg-accent-soft text-[10px] font-semibold text-accent">
                AF
              </span>
              <span className="text-[13px] font-medium tracking-tight text-ink-100">
                AirFed
              </span>
              <span className="text-2xs text-ink-600">ops</span>
            </a>
            <button
              className="btn btn-ghost lg:hidden"
              onClick={() => setMenuOpen(false)}
              aria-label="Close navigation"
              type="button"
            >
              <X size={14} />
            </button>
          </div>

          <nav className="space-y-0.5 p-2">
            {NAV.map(({ key, label, icon: Icon }) => (
              <a
                key={key}
                href={`#/${key}`}
                onClick={() => setMenuOpen(false)}
                className={`nav-item ${route === key ? "nav-item-active" : ""}`}
              >
                <Icon size={15} />
                <span>{label}</span>
                {route === key ? (
                  <ChevronRight size={12} className="ml-auto text-ink-600" />
                ) : null}
              </a>
            ))}
          </nav>

          <div className="mx-2 mt-2 border-t border-line pt-3">
            <div className="px-2.5 pb-2">
              <div className="label">Session</div>
              <div className="mt-1.5 flex items-center justify-between">
                <span className="mono text-[11px] text-ink-200">
                  {session?.state ?? "no state"}
                </span>
                <Dot
                  tone={
                    session?.stale
                      ? "warn"
                      : session?.active
                        ? "accent"
                        : brokerUp
                          ? "ok"
                          : "bad"
                  }
                  pulse={Boolean(session?.active && !session.stale)}
                />
              </div>
              {session?.session_id ? (
                <div className="mono mt-1 truncate text-2xs text-ink-600">
                  {session.session_id}
                </div>
              ) : null}
            </div>

            <div className="space-y-1.5 px-2.5 pb-3 text-2xs text-ink-500">
              <div className="flex items-center justify-between">
                <span>broker</span>
                <span className={brokerUp ? "text-ok-text" : "text-bad-text"}>
                  {status ? (brokerUp ? "connected" : "down") : "unknown"}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span>workers</span>
                <span className="mono text-ink-300">
                  {workers ? `${workers.online}/${workers.total}` : "—"}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span>transport</span>
                <span
                  className={
                    socket === "open" ? "text-ok-text" : "text-warn-text"
                  }
                >
                  {transport}
                </span>
              </div>
            </div>
          </div>

          <div className="absolute inset-x-0 bottom-0 border-t border-line px-4 py-3">
            <div className="flex items-center justify-between text-2xs text-ink-500">
              <span className="inline-flex items-center gap-1.5">
                <Activity size={11} />
                {status?.data_source ?? "no data"}
              </span>
              <span className="mono">
                {lastUpdated ? formatClock(lastUpdated.toISOString()) : "—"}
              </span>
            </div>
          </div>
        </div>
      </aside>

      <div className="min-w-0 flex-1 lg:pl-0">
        <header className="sticky top-0 z-20 flex h-14 items-center justify-between gap-3 border-b border-line bg-void/90 px-4 backdrop-blur sm:px-6">
          <div className="flex items-center gap-2">
            <button
              className="btn btn-ghost lg:hidden"
              onClick={() => setMenuOpen(true)}
              aria-label="Open navigation"
              type="button"
            >
              <Menu size={16} />
            </button>
            <span className="label hidden sm:inline">Operations console</span>
            <span className="text-2xs text-ink-600 sm:hidden">AirFed</span>
          </div>
          <div className="flex items-center gap-2 text-2xs text-ink-500">
            {session?.message ? (
              <span className="hidden max-w-[420px] truncate md:inline">
                {session.message}
              </span>
            ) : null}
            <span
              className={`chip ${
                socket === "open"
                  ? "border-ok/30 bg-ok-soft text-ok-text"
                  : socket === "connecting"
                    ? "border-warn/30 bg-warn-soft text-warn-text"
                    : "border-bad/30 bg-bad-soft text-bad-text"
              }`}
            >
              <Dot
                tone={socket === "open" ? "ok" : socket === "connecting" ? "warn" : "bad"}
                pulse={socket !== "open"}
              />
              {socket === "open" ? "live" : socket}
            </span>
            <button
              className="btn btn-ghost"
              onClick={refresh}
              disabled={loading}
              type="button"
              aria-label="Refresh data"
            >
              <RefreshCw size={13} className={loading ? "animate-spin" : ""} />
              <span className="hidden sm:inline">
                {lastUpdated ? relativeTime(lastUpdated.toISOString()) : "refresh"}
              </span>
            </button>
          </div>
        </header>

        <main className="mx-auto max-w-[1500px] px-4 py-5 sm:px-6 lg:py-6">
          <Page />
        </main>
      </div>
    </div>
  );
}

export default function App() {
  return (
    <CommandCenterProvider>
      <Shell />
    </CommandCenterProvider>
  );
}
