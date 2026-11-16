import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "./App.jsx";
import { ToastProvider } from "./components/overlay.jsx";
import { SettingsProvider } from "./lib/settings.jsx";
import "@fontsource-variable/public-sans";
import "./styles.css";
import "./theme.css";
import "./demo.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 2_000,
      retry: 1, // the gateway and services already retry; fail fast and show the error
      refetchOnWindowFocus: true,
      placeholderData: (previous) => previous, // keep showing old data while refreshing
    },
  },
});

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <SettingsProvider>
        <ToastProvider>
          <App />
        </ToastProvider>
      </SettingsProvider>
    </QueryClientProvider>
  </React.StrictMode>,
);
