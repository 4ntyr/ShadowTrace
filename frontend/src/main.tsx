import { StrictMode, Suspense, lazy } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "./lib/theme";
import { ApiError } from "./lib/api";
import Layout from "./components/Layout";
import { Loading } from "./components/ui";
import "./styles.css";

const Dashboard = lazy(() => import("./pages/Dashboard"));
const Groups = lazy(() => import("./pages/Groups"));
const GroupDetail = lazy(() => import("./pages/GroupDetail"));
const Graph = lazy(() => import("./pages/Graph"));
const ActivityPage = lazy(() => import("./pages/ActivityPage"));
const Hybrid = lazy(() => import("./pages/Hybrid"));
const ConflictPage = lazy(() => import("./pages/ConflictPage"));
const Sources = lazy(() => import("./pages/Sources"));
const Auth = lazy(() => import("./pages/Auth"));

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 60_000,
      refetchOnWindowFocus: false,
      retry: (n, err) => !(err instanceof ApiError && err.status < 500) && n < 2,
    },
  },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <Layout>
            <Suspense fallback={<Loading h={400} />}>
              <Routes>
                <Route path="/" element={<Dashboard />} />
                <Route path="/groups" element={<Groups />} />
                <Route path="/groups/:slug" element={<GroupDetail />} />
                <Route path="/graph" element={<Graph />} />
                <Route path="/activity" element={<ActivityPage />} />
                <Route path="/hybrid" element={<Hybrid />} />
                <Route path="/hybrid/:slug" element={<ConflictPage />} />
                <Route path="/sources" element={<Sources />} />
                <Route path="/login" element={<Auth mode="login" />} />
                <Route path="/register" element={<Auth mode="register" />} />
                <Route path="*" element={<div className="empty">Page not found.</div>} />
              </Routes>
            </Suspense>
          </Layout>
        </BrowserRouter>
      </QueryClientProvider>
    </ThemeProvider>
  </StrictMode>,
);
