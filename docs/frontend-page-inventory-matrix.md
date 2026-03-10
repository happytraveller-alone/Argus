# Frontend Page Inventory Matrix

Last updated: 2026-03-10

This matrix is the current baseline for page-level frontend trimming under `frontend/src`.

## nav-visible

These routes are shown in the current sidebar navigation.

| Route | Entry page |
| --- | --- |
| `/` | `frontend/src/pages/AgentAudit/index.tsx` |
| `/dashboard` | `frontend/src/pages/Dashboard.tsx` |
| `/projects` | `frontend/src/pages/Projects.tsx` |
| `/tasks/static` | `frontend/src/pages/TaskManagementStatic.tsx` |
| `/tasks/intelligent` | `frontend/src/pages/TaskManagementIntelligent.tsx` |
| `/tasks/hybrid` | `frontend/src/pages/TaskManagementHybrid.tsx` |
| `/scan-config/engines` | `frontend/src/pages/ScanConfigEngines.tsx` |
| `/scan-config/intelligent-engine` | `frontend/src/pages/ScanConfigIntelligentEngine.tsx` |
| `/scan-config/external-tools` | `frontend/src/pages/ScanConfigExternalTools.tsx` |

## hidden-but-routed

These routes are not shown in navigation but remain active for detail flows, compatibility, or hidden admin access.

| Route | Entry page | Notes |
| --- | --- | --- |
| `/agent-audit/:taskId` | `frontend/src/pages/AgentAudit/index.tsx` | Task detail deep link |
| `/projects/:id` | `frontend/src/pages/ProjectDetail.tsx` | Project detail |
| `/static-analysis/:taskId` | `frontend/src/pages/StaticAnalysis.tsx` | Static result detail |
| `/finding-detail/:source/:taskId/:findingId` | `frontend/src/pages/FindingDetail.tsx` | Unified finding detail |
| `/static-analysis/:taskId/findings/:findingId` | `frontend/src/pages/StaticFindingDetail.tsx` | Compatibility redirect |
| `/admin` | `frontend/src/pages/AdminDashboard.tsx` | Hidden admin page; keep for now |

## redirect-only

These routes exist only to normalize old entry points.

| Route | Redirect target |
| --- | --- |
| `/opengrep-rules` | `/scan-config/engines?tab=opengrep` |
| `/tasks/overview` | `/tasks/static` |
| `/scan-config` | `/scan-config/engines` |

## orphan-page-file

These unmounted page-level files were removed in phase one.

- `frontend/src/pages/TaskManagementOverview.tsx`
- `frontend/src/pages/ScanConfigOverview.tsx`
- `frontend/src/pages/project-detail/components/ProjectTasksTab.tsx`
- `frontend/src/pages/project-detail/constants.ts`

## review-queue

These pages still exist but should be reviewed in a later trimming pass.

- `frontend/src/pages/AdminDashboard.tsx`

## phase-two-removed-runtime-dead-files

These runtime-dead business files were removed in phase two.

- `frontend/src/components/agent/AgentSettingsPanel.tsx`
- `frontend/src/components/agent/CreateAgentTaskDialog.tsx`
- `frontend/src/components/scan/CreateAgentScanDialog.tsx`
- `frontend/src/components/scan/CreateStaticScanDialog.tsx`
- `frontend/src/components/scan/components/ZipFileSection.tsx`
- `frontend/src/features/reports/services/reportExport.ts`
