import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { NavLink, useLocation } from "react-router-dom";
import {
  Activity,
  LayoutDashboard,
  Layers,
  List,
  Menu,
  Moon,
  Network,
  Package,
  RefreshCw,
  Server,
  Sun,
  Terminal,
  Wind,
  X,
  TestTube2,
} from "lucide-react";
import { useCommandCenter } from "../../hooks/useCommandCenter";
import { relativeTime } from "../../lib/format";
import { Dot } from "../primitives";

const routes = [
  { to: "/overview", label: "Overview", icon: LayoutDashboard, description: "System and session state at a glance" },
  { to: "/simulation-lab", label: "Simulation Lab", icon: Activity, description: "Start the network simulator and worker processes" },
  { to: "/network-topology", label: "Network Topology", icon: Network, description: "Gateway and sensor layout from the simulator" },
  { to: "/terminal", label: "Terminal", icon: Terminal, description: "Tail coordinator, broker, and worker logs" },
  { to: "/gateways", label: "Gateways", icon: Server, description: "Federated gateway clients and their shards" },
  { to: "/federated-learning", label: "Federated Learning", icon: Layers, description: "Start a session and follow the current round" },
  { to: "/models", label: "Models", icon: Package, description: "Registered model versions and evaluation" },
  { to: "/testing-model", label: "Testing Model", icon: TestTube2, description: "Generate random input and test model predictions" },
  { to: "/air-quality", label: "Air Quality", icon: Wind, description: "PM2.5 observations and model predictions" },
  { to: "/experiments", label: "Experiments", icon: List, description: "Recorded experiment runs" },
];

const titles: Record<string, { title: string; sub: string }> = {
  "/overview": { title: "Overview", sub: "Broker, coordinator, workers, and the current federated round." },
  "/simulation-lab": { title: "Simulation Lab", sub: "Run the synthetic field network and launch training workers." },
  "/network-topology": { title: "Network Topology", sub: "Live topology from the network simulator." },
  "/terminal": { title: "Terminal", sub: "Read-only process logs. Nothing here is invented." },
  "/gateways": { title: "Gateways", sub: "Federated gateway clients, partitions, and contributions." },
  "/federated-learning": { title: "Federated Learning", sub: "Control a session and watch round stages progress." },
  "/models": { title: "Models", sub: "The global model registry and offline evaluation results." },
  "/testing-model": { title: "Testing Model", sub: "Generate random input and test model predictions for demonstration." },
  "/air-quality": { title: "Air Quality", sub: "Historical observations and PM2.5 predictions by node." },
  "/experiments": { title: "Experiments", sub: "Experiment records from the backend database." },
};

function currentTheme(): "light" | "dark" {
  if (typeof document === "undefined") return "light";
  return document.documentElement.dataset["theme"] === "dark" ? "dark" : "light";
}

export function DashboardLayout({ children }: { children: ReactNode }) {
  const location = useLocation();
  const [navOpen, setNavOpen] = useState(false);
  const [theme, setTheme] = useState<"light" | "dark">(currentTheme);
  const { status, error, loading, lastUpdated, socket, refresh } = useCommandCenter();
  const meta = titles[location.pathname] ?? { title: "AirFed", sub: "Federated PM2.5 operations console." };

  useEffect(() => {
    document.documentElement.dataset["theme"] = theme;
    try {
      localStorage.setItem("airfed-theme", theme);
    } catch {
      /* storage can be unavailable */
    }
  }, [theme]);

  useEffect(() => {
    setNavOpen(false);
  }, [location.pathname]);

  const brokerOk = Boolean(status?.broker.connected);
  const coordinatorOk = Boolean(status?.processes?.coordinator?.running);
  const sessionState = status?.session_view?.state ?? "idle";
  const counts = status?.worker_counts;

  return (
    <div className="shell">
      <aside className={navOpen ? "sidebar open" : "sidebar"}>
        <div className="sidebar-head">
          <div className="brand-mark" aria-hidden="true">
            AF
          </div>
          <div style={{ minWidth: 0, flex: 1 }}>
            <div className="brand-name">AirFed</div>
            <div className="brand-sub">Operations console</div>
          </div>
          <button
            className="icon-button hamburger"
            type="button"
            aria-label="Close navigation"
            onClick={() => setNavOpen(false)}
          >
            <X size={16} />
          </button>
        </div>

        <nav className="nav" aria-label="Main navigation">
          <div className="nav-label">Monitor</div>
          {routes.slice(0, 4).map((route) => {
            const Icon = route.icon;
            return (
              <NavLink
                key={route.to}
                to={route.to}
                title={route.description}
                className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}
              >
                <Icon size={15} />
                <span>{route.label}</span>
              </NavLink>
            );
          })}
          <div className="nav-label" style={{ marginTop: 10 }}>
            Federated
          </div>
          {routes.slice(4).map((route) => {
            const Icon = route.icon;
            return (
              <NavLink
                key={route.to}
                to={route.to}
                title={route.description}
                className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}
              >
                <Icon size={15} />
                <span>{route.label}</span>
              </NavLink>
            );
          })}
        </nav>

        <div className="sidebar-foot">
          <div className="row">
            <Dot tone={brokerOk ? "ok" : "bad"} />
            <span>Broker {brokerOk ? "connected" : "unreachable"}</span>
          </div>
          <div className="row">
            <Dot tone={socket === "open" ? "ok" : "warn"} />
            <span>Live stream {socket}</span>
          </div>
          <div className="row">
            <Dot tone={coordinatorOk ? "ok" : "warn"} />
            <span>Coordinator {coordinatorOk ? "running" : "stopped"}</span>
          </div>
          <div className="faint" style={{ marginTop: 2 }}>
            {status?.data_source ?? "waiting for status"}
          </div>
        </div>
      </aside>

      {navOpen && <div className="scrim" onClick={() => setNavOpen(false)} aria-hidden="true" />}

      <div className="main">
        <header className="topbar">
          <div className="row" style={{ minWidth: 0 }}>
            <button
              className="icon-button hamburger"
              type="button"
              aria-label="Open navigation"
              onClick={() => setNavOpen(true)}
            >
              <Menu size={17} />
            </button>
            <div style={{ minWidth: 0 }}>
              <div className="topbar-title">{meta.title}</div>
              <div className="topbar-sub">{meta.sub}</div>
            </div>
          </div>

          <div className="topbar-actions">
            <span className={`badge ${brokerOk ? "badge-ok" : "badge-bad"}`} title="MQTT broker connection">
              <Dot tone={brokerOk ? "ok" : "bad"} />
              {brokerOk ? "broker online" : "broker offline"}
            </span>
            <span className={`badge ${socket === "open" ? "badge-ok" : "badge-warn"}`} title="WebSocket stream">
              stream {socket}
            </span>
            <span className="badge badge-neutral" title={`Session state: ${sessionState}`}>
              session {sessionState}
            </span>
            {counts && (
              <span className="badge badge-neutral" title="Online workers">
                workers {counts.online}/{counts.total}
              </span>
            )}
            <button
              className="icon-button"
              type="button"
              aria-label="Refresh data"
              title={`Refresh now${lastUpdated ? ` · updated ${relativeTime(lastUpdated.toISOString())}` : ""}`}
              onClick={refresh}
            >
              <RefreshCw size={15} />
            </button>
            <button
              className="icon-button"
              type="button"
              aria-label={theme === "dark" ? "Use light theme" : "Use dark theme"}
              onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
            >
              {theme === "dark" ? <Sun size={15} /> : <Moon size={15} />}
            </button>
          </div>
        </header>

        {error && !status && (
          <div style={{ padding: "12px 28px 0" }}>
            <div className="notice notice-bad" role="alert">
              <span style={{ flex: 1 }}>Status API unreachable: {error}</span>
              <button className="btn btn-sm" type="button" onClick={refresh}>
                Retry
              </button>
            </div>
          </div>
        )}

        <main className="content" id="main">
          {loading && !status ? (
            <div className="loading-text">Loading live status…</div>
          ) : (
            children
          )}
        </main>
      </div>
    </div>
  );
}