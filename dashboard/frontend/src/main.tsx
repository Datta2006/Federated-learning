import { Routes, Route, Navigate } from "react-router-dom";
import App from "./App";
import OverviewPage from "./pages/OverviewPage";

export default function ViteRoot() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/overview" replace />} />
      <Route path="/overview" element={<OverviewPage />} />
      <Route path="/*" element={<App />} />
    </Routes>
  );
}
