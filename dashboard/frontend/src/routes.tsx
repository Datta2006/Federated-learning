import { Routes, Route, Navigate } from "react-router-dom";
import App from "../App";
import OverviewPage from "./overview-status";

export default function Root() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/overview" replace />} />
      <Route path="/overview" element={<OverviewPage />} />
      <Route path="/*" element={<App />} />
    </Routes>
  );
}