import { Navigate, Route, Routes } from "react-router-dom";
import { DashboardLayout } from "@/components/layout/DashboardLayout";
import { OverviewPage } from "@/pages/Overview";
import { SimulationLabPage } from "@/pages/SimulationLab";
import { LiveNetworkTopologyPage } from "@/pages/LiveNetworkTopology";
import { LiveTerminalPage } from "@/pages/LiveTerminal";
import { GatewayControlCentrePage } from "@/pages/GatewayControlCentre";
import { FederatedLearningControlCentrePage } from "@/pages/FederatedLearningControlCentre";
import { ModelCenterPage } from "@/pages/ModelCenter";
import { AirQualityIntelligencePage } from "@/pages/AirQualityIntelligence";
import { ExperimentsPage } from "@/pages/Experiments";

const routes = [
  { path: "/overview", element: <OverviewPage /> },
  { path: "/simulation-lab", element: <SimulationLabPage /> },
  { path: "/network-topology", element: <LiveNetworkTopologyPage /> },
  { path: "/terminal", element: <LiveTerminalPage /> },
  { path: "/gateways", element: <GatewayControlCentrePage /> },
  { path: "/federated-learning", element: <FederatedLearningControlCentrePage /> },
  { path: "/models", element: <ModelCenterPage /> },
  { path: "/air-quality", element: <AirQualityIntelligencePage /> },
  { path: "/experiments", element: <ExperimentsPage /> },
];

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/overview" replace />} />
      {routes.map((route) => (
        <Route
          key={route.path}
          path={route.path}
          element={<DashboardLayout>{route.element}</DashboardLayout>}
        />
      ))}
      <Route path="*" element={<Navigate to="/overview" replace />} />
    </Routes>
  );
}
