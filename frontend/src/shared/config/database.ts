// Re-export API implementation from the new API client
// This maintains compatibility with existing imports throughout the app
import { api as newApi } from "@/shared/api/database";

export const api = newApi;

// Feature flags / Mode flags
export const isDemoMode = false;
export const isLocalMode = false;

// Supabase 不再使用（后端已实现 PostgreSQL 数据库）
// 保留此导出仅为兼容性，实际值为 null
export const supabase = null;
