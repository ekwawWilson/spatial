import { Navigate, Route, Routes } from "react-router-dom";

import { Layout } from "./components/Layout";
import { PublicFrame } from "./components/PublicFrame";
import { RequireAuth, RequirePermission, RequireSystemAdmin } from "./components/guards";
import { AccountPage } from "./pages/AccountPage";
import { AddressingPage } from "./pages/AddressingPage";
import { AuditPage } from "./pages/AuditPage";
import { BasemapsPage } from "./pages/BasemapsPage";
import { ChecklistPage } from "./pages/ChecklistPage";
import { CompliancePage } from "./pages/CompliancePage";
import { ConflictsPage } from "./pages/ConflictsPage";
import { CrsPage } from "./pages/CrsPage";
import { DataRoomPage } from "./pages/DataRoomPage";
import { DistrictsPage } from "./pages/DistrictsPage";
import { CasePage, EnforcementPage } from "./pages/EnforcementPage";
import { LandApplicationPage, LandApplicationsPage } from "./pages/LandApplicationsPage";
import { LocalPlanPage } from "./pages/LocalPlanPage";
import { RatesPage } from "./pages/RatesPage";
import { ReturnsPage } from "./pages/ReturnsPage";
import { CommitteesPage, MeetingPage } from "./pages/CommitteesPage";
import { ForgotPasswordPage, ResetPasswordPage } from "./pages/PasswordResetPages";
import { HomePage } from "./pages/HomePage";
import { ImageryPage } from "./pages/ImageryPage";
import { LoginPage } from "./pages/LoginPage";
import { MembersPage } from "./pages/MembersPage";
import { PermitPage } from "./pages/PermitPage";
import { PermitsPage } from "./pages/PermitsPage";
import { PlanSheetPage } from "./pages/PlanSheetPage";
import { ProjectWorkspace } from "./pages/ProjectWorkspace";
import { ProjectsPage } from "./pages/ProjectsPage";
import { PublicRoomPage, PublicRoomsPage } from "./pages/PublicRoomPage";
import { ReadinessPage } from "./pages/ReadinessPage";
import { RelationsPage } from "./pages/RelationsPage";
import { StatusPage } from "./pages/StatusPage";
import { UsersPage } from "./pages/UsersPage";
import { VerifyPage } from "./pages/VerifyPage";
import { ZoningPage } from "./pages/ZoningPage";

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/forgot-password" element={<ForgotPasswordPage />} />
      <Route path="/reset-password" element={<ResetPasswordPage />} />
      <Route path="/status" element={<StatusPage />} />
      <Route element={<PublicFrame />}>
        <Route path="/verify/:token" element={<VerifyPage />} />
        <Route path="/public" element={<PublicRoomsPage />} />
        <Route path="/public/:code" element={<PublicRoomPage />} />
      </Route>
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
          path="projects/:projectId/relations"
          element={
            <RequirePermission permission="project.view">
              <RelationsPage />
            </RequirePermission>
          }
        />
        <Route
          path="projects/:projectId/permits"
          element={
            <RequirePermission permission="permit.view">
              <PermitsPage />
            </RequirePermission>
          }
        />
        <Route
          path="projects/:projectId/permits/:permitId"
          element={
            <RequirePermission permission="permit.view">
              <PermitPage />
            </RequirePermission>
          }
        />
        <Route
          path="projects/:projectId/rates"
          element={
            <RequirePermission permission="revenue.view">
              <RatesPage />
            </RequirePermission>
          }
        />
        <Route
          path="projects/:projectId/plan"
          element={
            <RequirePermission permission="project.view">
              <LocalPlanPage />
            </RequirePermission>
          }
        />
        <Route
          path="projects/:projectId/land"
          element={
            <RequirePermission permission="permit.view">
              <LandApplicationsPage />
            </RequirePermission>
          }
        />
        <Route
          path="projects/:projectId/land/:applicationId"
          element={
            <RequirePermission permission="permit.view">
              <LandApplicationPage />
            </RequirePermission>
          }
        />
        <Route
          path="projects/:projectId/enforcement"
          element={
            <RequirePermission permission="enforcement.view">
              <EnforcementPage />
            </RequirePermission>
          }
        />
        <Route
          path="projects/:projectId/enforcement/:caseId"
          element={
            <RequirePermission permission="enforcement.view">
              <CasePage />
            </RequirePermission>
          }
        />
        <Route
          path="projects/:projectId/addressing"
          element={
            <RequirePermission permission="project.view">
              <AddressingPage />
            </RequirePermission>
          }
        />
        <Route
          path="projects/:projectId/sheet"
          element={
            <RequirePermission permission="project.view">
              <PlanSheetPage />
            </RequirePermission>
          }
        />
        <Route
          path="projects/:projectId/zoning"
          element={
            <RequirePermission permission="project.view">
              <ZoningPage />
            </RequirePermission>
          }
        />
        <Route
          path="projects/:projectId/imagery"
          element={
            <RequirePermission permission="project.view">
              <ImageryPage />
            </RequirePermission>
          }
        />
        <Route
          path="projects/:projectId/conflicts"
          element={
            <RequirePermission permission="project.view">
              <ConflictsPage />
            </RequirePermission>
          }
        />
        <Route
          path="committees"
          element={
            <RequirePermission permission="permit.view">
              <CommitteesPage />
            </RequirePermission>
          }
        />
        <Route
          path="committees/:meetingId"
          element={
            <RequirePermission permission="permit.view">
              <MeetingPage />
            </RequirePermission>
          }
        />
        <Route
          path="returns"
          element={
            <RequirePermission permission="reports.view">
              <ReturnsPage />
            </RequirePermission>
          }
        />
        <Route
          path="deadlines"
          element={
            <RequirePermission permission="reports.view">
              <CompliancePage />
            </RequirePermission>
          }
        />
        <Route
          path="data-room"
          element={
            <RequirePermission permission="dataroom.view">
              <DataRoomPage />
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
