import React from "react";
import { createRoot } from "react-dom/client";
import { MotionConfig } from "framer-motion";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "./App";
import "./index.css";

const qc = new QueryClient({ defaultOptions: { queries: { staleTime: 60_000, retry: 1 } } });
createRoot(document.getElementById("root")!).render(
  <React.StrictMode><MotionConfig reducedMotion="user"><QueryClientProvider client={qc}><App /></QueryClientProvider></MotionConfig></React.StrictMode>,
);
