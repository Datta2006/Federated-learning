import { useHashRoute } from "../hooks/useHashRoute";
import OverviewPage from "./pages/OverviewPage";

export default function App() {
  const [route] = useHashRoute();
  if (route !== "overview") return null;
  return <OverviewPage />;
}
