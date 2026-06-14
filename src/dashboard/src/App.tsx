import { Routes, Route, Navigate } from "react-router-dom";
import { Layout } from "./components/Layout";
import { DashboardPage } from "./pages/DashboardPage";
import { ProjectDetailPage } from "./pages/ProjectDetailPage";

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<DashboardPage />} />
        <Route path="/projects/:projectId" element={<ProjectDetailPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Layout>
  );
}
