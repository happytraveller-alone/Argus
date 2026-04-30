
export const SUPPORTED_LANGUAGES = [
  'javascript',
  'typescript',
  'python',
  'java',
  'go',
  'rust',
  'cpp',
  'csharp',
  'php',
  'ruby',
  'swift',
  'kotlin',
] as const;

export const ISSUE_TYPES = {
  BUG: 'bug',
  SECURITY: 'security',
  PERFORMANCE: 'performance',
  STYLE: 'style',
  MAINTAINABILITY: 'maintainability',
} as const;

export const SEVERITY_LEVELS = {
  CRITICAL: 'critical',
  HIGH: 'high',
  MEDIUM: 'medium',
  LOW: 'low',
} as const;

export const TASK_STATUS = {
  PENDING: 'pending',
  RUNNING: 'running',
  COMPLETED: 'completed',
  FAILED: 'failed',
  CANCELLED: 'cancelled',
} as const;

export const USER_ROLES = {
  ADMIN: 'admin',
  MEMBER: 'member',
} as const;

export const PROJECT_ROLES = {
  OWNER: 'owner',
  ADMIN: 'admin',
  MEMBER: 'member',
  VIEWER: 'viewer',
} as const;

export const PROJECT_SOURCE_TYPES = {
  REPOSITORY: 'repository',
  ZIP: 'zip',
} as const;

export const ANALYSIS_DEPTH = {
  BASIC: 'basic',
  STANDARD: 'standard',
  DEEP: 'deep',
} as const;

export const DEFAULT_CONFIG = {
  MAX_FILE_SIZE: 200 * 1024, // 200KB (对齐后端 MAX_FILE_SIZE_BYTES)
  MAX_FILES_PER_SCAN: 0, // 对齐后端 MAX_ANALYZE_FILES，0表示无限制
  ANALYSIS_TIMEOUT: 30000, // 30秒
  DEBOUNCE_DELAY: 300, // 300ms
} as const;

export const PROJECT_DETAIL_REQUEST_TIMEOUT_MS = 12_000;
export const PROJECT_DETAIL_ISSUES_MAX_TASKS = 20;
export const PROJECT_DETAIL_ISSUES_FETCH_CONCURRENCY = 5;

export const API_ENDPOINTS = {
  PROJECTS: '/api/projects',
  AUDIT_TASKS: '/api/audit-tasks',
  INSTANT_ANALYSIS: '/api/instant-analysis',
  USERS: '/api/users',
} as const;

export const STORAGE_KEYS = {
  THEME: 'argus-theme',
  USER_PREFERENCES: 'argus-preferences',
  RECENT_PROJECTS: 'argus-recent-projects',
} as const;

export * from './projectTypes';
