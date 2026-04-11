// 通用选项接口
export interface Option {
  label: string;
  value: string;
  icon?: React.ComponentType<{ className?: string }>;
  withCount?: boolean;
}

// 用户相关类型
export interface Profile {
  id: string;
  phone?: string;
  email?: string;
  full_name?: string;
  avatar_url?: string;
  role: 'admin' | 'member';
  github_username?: string;
  gitlab_username?: string;
  created_at: string;
  updated_at: string;
}

// 项目来源类型
export type ProjectSourceType = 'repository' | 'zip';

// 仓库平台类型
export type RepositoryPlatform = 'github' | 'gitlab' | 'gitea' | 'other';

// 项目相关类型
export interface ProjectManagementMetrics {
  archive_size_bytes?: number | null;
  archive_original_filename?: string | null;
  archive_uploaded_at?: string | null;
  total_tasks: number;
  completed_tasks: number;
  running_tasks: number;
  agent_tasks: number;
  opengrep_tasks: number;
  gitleaks_tasks: number;
  bandit_tasks: number;
  phpstan_tasks: number;
  critical: number;
  high: number;
  medium: number;
  low: number;
  verified_critical?: number;
  verified_high?: number;
  verified_medium?: number;
  verified_low?: number;
  last_completed_task_at?: string | null;
  status: "pending" | "ready" | "failed";
  error_message?: string | null;
  created_at?: string;
  updated_at?: string;
}

export interface Project {
  id: string;
  name: string;
  description?: string;
  source_type: ProjectSourceType;  // 项目来源: 'repository' (远程仓库) 或 'zip' (ZIP上传)
  repository_url?: string;         // 仅 source_type='repository' 时有效
  repository_type?: RepositoryPlatform;  // 仓库平台: github, gitlab, other
  default_branch: string;
  programming_languages: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  management_metrics?: ProjectManagementMetrics | null;
}

export interface ProjectMember {
  id: string;
  project_id: string;
  user_id: string;
  role: 'owner' | 'admin' | 'member' | 'viewer';
  permissions: string;
  joined_at: string;
  created_at: string;
  user?: Profile;
  project?: Project;
}

// 表单相关类型
export interface CreateProjectForm {
  name: string;
  description?: string;
  source_type?: ProjectSourceType;  // 项目来源类型
  repository_url?: string;          // 仅 source_type='repository' 时需要
  repository_type?: RepositoryPlatform;  // 仓库平台
  default_branch?: string;
  programming_languages: string[];
}

// 统计相关类型
export interface ProjectStats {
  total_projects: number;
  active_projects: number;
  total_tasks: number;
  completed_tasks: number;
  interrupted_tasks: number;
  running_tasks: number;
  failed_tasks: number;
  total_issues: number;
  resolved_issues: number;
  avg_quality_score: number;
}

export interface DashboardScanRunsItem {
  project_id: string;
  project_name: string;
  static_runs: number;
  intelligent_runs: number;
  hybrid_runs: number;
  total_runs: number;
}

export interface DashboardVulnsItem {
  project_id: string;
  project_name: string;
  static_vulns: number;
  intelligent_vulns: number;
  hybrid_vulns: number;
  total_vulns: number;
}

export interface DashboardRuleConfidenceItem {
  confidence: "HIGH" | "MEDIUM" | "LOW" | "UNSPECIFIED";
  total_rules: number;
  enabled_rules: number;
}

export interface DashboardRuleConfidenceByLanguageItem {
  language: string;
  high_count: number;
  medium_count: number;
}

export interface DashboardCweDistributionItem {
  cwe_id: string;
  cwe_name: string;
  total_findings: number;
  opengrep_findings: number;
  agent_findings: number;
  bandit_findings: number;
}

export interface DashboardSummaryItem {
  total_projects: number;
  current_effective_findings: number;
  current_verified_findings: number;
  total_model_tokens: number;
  false_positive_rate: number;
  scan_success_rate: number;
  avg_scan_duration_ms: number;
  window_scanned_projects: number;
  window_new_effective_findings: number;
  window_verified_findings: number;
  window_false_positive_rate: number;
  window_scan_success_rate: number;
  window_avg_scan_duration_ms: number;
}

export interface DashboardDailyActivityItem {
  date: string;
  completed_scans: number;
  agent_findings: number;
  opengrep_findings: number;
  gitleaks_findings: number;
  bandit_findings: number;
  phpstan_findings: number;
  pmd_findings?: number;
  yasa_findings: number;
  static_findings: number;
  intelligent_verified_findings: number;
  hybrid_verified_findings: number;
  total_new_findings: number;
}

export interface DashboardVerificationFunnelItem {
  raw_findings: number;
  effective_findings: number;
  verified_findings: number;
  false_positive_count: number;
}

export interface DashboardTaskStatusBreakdownItem {
  pending: number;
  running: number;
  completed: number;
  failed: number;
  interrupted: number;
  cancelled: number;
}

export interface DashboardEngineBreakdownItem {
  engine: "llm" | "opengrep" | "gitleaks" | "bandit" | "phpstan" | "yasa" | "pmd";
  completed_scans: number;
  effective_findings: number;
  verified_findings: number;
  false_positive_count: number;
  avg_scan_duration_ms: number;
  success_rate: number;
}

export interface DashboardProjectHotspotItem {
  project_id: string;
  project_name: string;
  risk_score: number;
  scan_runs_window: number;
  effective_findings: number;
  verified_findings: number;
  false_positive_rate: number;
  dominant_language: string;
  last_scan_at?: string | null;
  top_engine: string;
}

export interface DashboardLanguageRiskItem {
  language: string;
  project_count: number;
  loc_number: number;
  effective_findings: number;
  verified_findings: number;
  false_positive_count: number;
  findings_per_kloc: number;
  rules_high: number;
  rules_medium: number;
}

export interface DashboardRecentTaskItem {
  task_id: string;
  task_type: string;
  title: string;
  engine: string;
  status: string;
  created_at: string;
  detail_path: string;
}

export interface DashboardTaskStatusScanTypeBreakdown {
  static: number;
  intelligent: number;
  hybrid: number;
}

export interface DashboardTaskStatusByScanTypeItem {
  pending: DashboardTaskStatusScanTypeBreakdown;
  running: DashboardTaskStatusScanTypeBreakdown;
  completed: DashboardTaskStatusScanTypeBreakdown;
  failed: DashboardTaskStatusScanTypeBreakdown;
  interrupted: DashboardTaskStatusScanTypeBreakdown;
  cancelled: DashboardTaskStatusScanTypeBreakdown;
}

export interface DashboardProjectRiskDistributionItem {
  project_id: string;
  project_name: string;
  critical_count: number;
  high_count: number;
  medium_count: number;
  low_count: number;
  total_findings: number;
}

export interface DashboardVerifiedVulnerabilityTypeItem {
  type_code: string;
  type_name: string;
  verified_count: number;
}

export interface DashboardStaticEngineRuleTotalItem {
  engine: "opengrep" | "gitleaks" | "bandit" | "phpstan" | "yasa" | "pmd";
  total_rules: number;
}

export interface DashboardLanguageLocItem {
  language: string;
  loc_number: number;
  project_count: number;
}

export interface DashboardSnapshotResponse {
  generated_at: string;
  total_scan_duration_ms: number;
  scan_runs: DashboardScanRunsItem[];
  vulns: DashboardVulnsItem[];
  rule_confidence: DashboardRuleConfidenceItem[];
  rule_confidence_by_language: DashboardRuleConfidenceByLanguageItem[];
  cwe_distribution: DashboardCweDistributionItem[];
  summary: DashboardSummaryItem;
  daily_activity: DashboardDailyActivityItem[];
  verification_funnel: DashboardVerificationFunnelItem;
  task_status_breakdown: DashboardTaskStatusBreakdownItem;
  task_status_by_scan_type: DashboardTaskStatusByScanTypeItem;
  engine_breakdown: DashboardEngineBreakdownItem[];
  project_hotspots: DashboardProjectHotspotItem[];
  language_risk: DashboardLanguageRiskItem[];
  recent_tasks: DashboardRecentTaskItem[];
  project_risk_distribution: DashboardProjectRiskDistributionItem[];
  verified_vulnerability_types: DashboardVerifiedVulnerabilityTypeItem[];
  static_engine_rule_totals: DashboardStaticEngineRuleTotalItem[];
  language_loc_distribution: DashboardLanguageLocItem[];
}

export interface StaticScanOverviewItem {
  project_id: string;
  project_name: string;
  last_scan_tool: "opengrep" | "gitleaks" | "bandit" | "phpstan" | "yasa" | "pmd";
  last_scan_task_id: string;
  paired_gitleaks_task_id?: string | null;
  last_scan_at: string;
  severe_count: number;
  hint_count: number;
  info_count: number;
  total_findings: number;
}

export interface StaticScanOverviewResponse {
  items: StaticScanOverviewItem[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface ProjectDescriptionGenerateResponse {
  description: string;
  language_info: string;
  source: "llm" | "static";
}

export interface IssueStats {
  by_type: Record<string, number>;
  by_severity: Record<string, number>;
  by_status: Record<string, number>;
  trend_data: Array<{
    date: string;
    count: number;
  }>;
}

// API响应类型
export interface ApiResponse<T> {
  data: T;
  message?: string;
  success: boolean;
}

export interface PaginatedResponse<T> {
  data: T[];
  total: number;
  page: number;
  limit: number;
  has_more: boolean;
}

// 代码分析结果类型
export interface CodeAnalysisResult {
  issues: Array<{
    type: string;
    severity: string;
    title: string;
    description: string;
    suggestion: string;
    line: number;
    column?: number;
    code_snippet: string;
    ai_explanation: string;
    xai?: {
      what: string;
      why: string;
      how: string;
      learn_more?: string;
    };
  }>;
  quality_score: number;
  summary: {
    total_issues: number;
    critical_issues: number;
    high_issues: number;
    medium_issues: number;
    low_issues: number;
  };
  metrics: {
    complexity: number;
    maintainability: number;
    security: number;
    performance: number;
  };
  // 后端返回的额外字段
  analysis_id?: string;
  analysis_time?: number;
}

// GitHub/GitLab集成类型
export interface Repository {
  id: string;
  name: string;
  full_name: string;
  description?: string;
  html_url: string;
  clone_url: string;
  default_branch: string;
  language?: string;
  languages?: Record<string, number>;
  private: boolean;
  updated_at: string;
}

export interface Branch {
  name: string;
  commit: {
    sha: string;
    url: string;
  };
  protected: boolean;
}

// 通知类型
export interface Notification {
  id: string;
  type: 'task_completed' | 'task_failed' | 'new_issue' | 'issue_resolved';
  title: string;
  message: string;
  data?: any;
  read: boolean;
  created_at: string;
}

// 系统配置类型
export interface SystemConfig {
  max_file_size: number;
  supported_languages: string[];
  analysis_timeout: number;
  max_concurrent_tasks: number;
  notification_settings: {
    email_enabled: boolean;
    webhook_url?: string;
  };
}
