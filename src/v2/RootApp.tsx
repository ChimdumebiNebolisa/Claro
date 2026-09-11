import { lazy, Suspense } from "react";
import { Route, Routes } from "react-router-dom";
import MarketingShell from "./MarketingShell";
import NotFound from "./NotFound";

const WorkspaceShell = lazy(() => import("./WorkspaceShell"));
const LegacyApp = lazy(() => import("../ui/App"));

function RouteLoading() {
  return (
    <main className="v2-route-loading" role="status">
      Opening Claros…
    </main>
  );
}

const workspace = (mode: "upload" | "question" | "review" | "export") => (
  <Suspense fallback={<RouteLoading />}>
    <WorkspaceShell mode={mode} />
  </Suspense>
);

export default function RootApp() {
  return (
    <Routes>
      <Route path="/" element={<MarketingShell />} />
      <Route path="/app" element={workspace("upload")} />
      <Route path="/app/:assignmentId" element={workspace("question")} />
      <Route path="/app/:assignmentId/review" element={workspace("review")} />
      <Route
        path="/app/:assignmentId/export/:exportId"
        element={workspace("export")}
      />
      <Route
        path="/legacy/*"
        element={
          <Suspense fallback={<RouteLoading />}>
            <LegacyApp />
          </Suspense>
        }
      />
      <Route path="*" element={<NotFound />} />
    </Routes>
  );
}
