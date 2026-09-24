import { Navigate, Route, Routes } from "react-router-dom";

import { Layout } from "./components/Layout";
import { RequireAuth, RequirePermission, RequireSystemAdmin } from "./components/guards";
import { AccountPage } from "./pages/AccountPage";
import { AuditPage } from "./pages/AuditPage";
import { BasemapsPage } from "./pages/BasemapsPage";
import { ChecklistPage } from "./pages/ChecklistPage";
import { CrsPage } from "./pages/CrsPage";
import { DistrictsPage } from "./pages/DistrictsPage";
import { ForgotPasswordPage, ResetPasswordPage } from "./pages/PasswordResetPages";
import { HomePage } from "./pages/HomePage";
import { LoginPage } from "./pages/LoginPage";
import { MembersPage } from "./pages/MembersPage";
import { ProjectWorkspace } from "./pages/ProjectWorkspace";
import { ProjectsPage } from "./pages/ProjectsPage";
import { ReadinessPage } from "./pages/ReadinessPage";
import { StatusPage } from "./pages/StatusPage";
import { UsersPage } from "./pages/UsersPage";

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/forgot-password" element={<ForgotPasswordPage />} />
      <Route path="/reset-password" element={<ResetPasswordPage />} />
      <Route path="/status" element={<StatusPage />} />
      <Route
        element={
          <RequireAuth>
            <Layout />
          </RequireAuth>
        }
      >
        <Route index element={<HomePage />} />
        <Route path="account" element={<AccountPage />} />
        <Route path="crs" element={<CrsPage />} />
        <Route path="basemaps" element={<BasemapsPage />} />
        <Route
          path="projects"
          element={
            <RequirePermission permission="project.view">
              <ProjectsPage />
            </RequirePermission>
          }
        />
        <Route
          path="projects/:projectId"
          element={
            <RequirePermission permission="project.view">
              <ProjectWorkspace />
            </RequirePermission>
          }
        />
        <Route
          path="projects/:projectId/checklist"
          element={
            <RequirePermission permission="project.view">
              <ChecklistPage />
            </RequirePermission>
          }
        />
        <Route
          path="readiness"
          element={
            <RequirePermission permission="project.view">
              <ReadinessPage />
            </RequirePermission>
          }
        />
        <Route
          path="members"
          element={
            <RequirePermission permission="membership.view">
              <MembersPage />
            </RequirePermission>
          }
        />
        <Route
          path="audit"
          element={
            <RequirePermission permission="audit.view">
              <AuditPage />
            </RequirePermission>
          }
        />
        <Route
          path="admin/districts"
          element={
            <RequireSystemAdmin>
              <DistrictsPage />
            </RequireSystemAdmin>
          }
        />
        <Route
          path="admin/users"
          element={
            <RequireSystemAdmin>
              <UsersPage />
            </RequireSystemAdmin>
          }
        />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
