/**
 * CodeQL Rules API Client
 */

import { apiClient } from "@/shared/api/serverClient";

export interface CodeqlRule {
    id: string;
    name: string;
    language: string;
    asset_path: string;
    file_format: string;
    source: string;
    is_active: boolean;
    metadata: Record<string, unknown>;
    content: string;
}

export interface CodeqlRulesPage {
    data: CodeqlRule[];
    total: number;
}

export interface CodeqlRuleStats {
    total: number;
    active: number;
    inactive: number;
    language_count: number;
    languages: string[];
}

export async function getCodeqlRulesPage(params: {
    skip?: number;
    limit?: number;
    keyword?: string;
    language?: string;
}): Promise<CodeqlRulesPage> {
    const response = await apiClient.get("/static-tasks/codeql/rules", { params });
    return response.data;
}

export async function getCodeqlRuleStats(): Promise<CodeqlRuleStats> {
    const response = await apiClient.get("/static-tasks/codeql/rules/stats");
    return response.data;
}
