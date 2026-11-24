import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { CommandCenterProvider } from "./hooks/useCommandCenter";
import "./index.css";

const root = ReactDOM.createRoot(document.getElementById("root") as HTMLElement);

root.render(
  <React.StrictMode>
    <CommandCenterProvider>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </CommandCenterProvider>
  </React.StrictMode>,
);
