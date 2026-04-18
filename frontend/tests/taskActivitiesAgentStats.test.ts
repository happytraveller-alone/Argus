import test from "node:test";
import assert from "node:assert/strict";

import { apiClient } from "../src/shared/api/serverClient.ts";
import {
  fetchTaskActivities,
  filterIntelligentActivities,
} from "../src/features/tasks/services/taskActivities.ts";

test("fetchTaskActivities maps effective severity stats for intelligent task summaries and folds legacy agent tasks into intelligent", async () => {
  const originalGet = apiClient.get;

  apiClient.get = (async (url: string) => {
    if (url === "/agent-tasks/") {
      return {
        data: [
          {
            id: "agent-intelligent",
            project_id: "project-1",
            name: "智能扫描-Demo",
            description: "[INTELLIGENT]智能扫描任务",
            task_type: "agent_audit",
            status: "completed",
            current_phase: null,
            current_step: null,
            total_files: 10,
            indexed_files: 10,
            analyzed_files: 10,
            files_with_findings: 2,
            total_chunks: 30,
            findings_count: 7,
            verified_count: 4,
            verified_critical_count: 1,
            verified_high_count: 1,
            verified_medium_count: 1,
            verified_low_count: 1,
            defect_summary: {
              scope: "all_findings",
              total_count: 7,
              severity_counts: {
                critical: 2,
                high: 3,
                medium: 1,
                low: 1,
                info: 0,
              },
              status_counts: {
                pending: 2,
                verified: 4,
                false_positive: 1,
              },
            },
            false_positive_count: 1,
            total_iterations: 5,
            tool_calls_count: 12,
            tokens_used: 1200,
            critical_count: 1,
            high_count: 2,
            medium_count: 3,
            low_count: 1,
            quality_score: 0,
            security_score: null,
            created_at: "2026-03-13T08:00:00.000Z",
            started_at: "2026-03-13T08:01:00.000Z",
            completed_at: "2026-03-13T08:05:00.000Z",
            progress_percentage: 100,
            audit_scope: null,
            target_vulnerabilities: null,
            verification_level: null,
            exclude_patterns: null,
            target_files: null,
            error_message: null,
          },
          {
            id: "agent-legacy",
            project_id: "project-1",
            name: "历史智能扫描-Demo",
            description: "历史迁移前任务",
            task_type: "agent_audit",
            status: "running",
            current_phase: null,
            current_step: null,
            total_files: 10,
            indexed_files: 8,
            analyzed_files: 6,
            files_with_findings: 1,
            total_chunks: 30,
            findings_count: 4,
            verified_count: 1,
            verified_critical_count: 0,
            verified_high_count: 0,
            verified_medium_count: 1,
            verified_low_count: 0,
            defect_summary: {
              scope: "all_findings",
              total_count: 4,
              severity_counts: {
                critical: 0,
                high: 1,
                medium: 2,
                low: 1,
                info: 0,
              },
              status_counts: {
                pending: 3,
                verified: 1,
                false_positive: 0,
              },
            },
            false_positive_count: 0,
            total_iterations: 3,
            tool_calls_count: 7,
            tokens_used: 800,
            critical_count: 0,
            high_count: 1,
            medium_count: 2,
            low_count: 1,
            quality_score: 0,
            security_score: null,
            created_at: "2026-03-13T09:00:00.000Z",
            started_at: "2026-03-13T09:01:00.000Z",
            completed_at: null,
            progress_percentage: 50,
            audit_scope: null,
            target_vulnerabilities: null,
            verification_level: null,
            exclude_patterns: null,
            target_files: null,
            error_message: null,
          },
        ],
      };
    }
    if (
      url.startsWith("/static-tasks/tasks") ||
      url.startsWith("/static-tasks/gitleaks/tasks") ||
      url.startsWith("/static-tasks/bandit/tasks") ||
      url.startsWith("/static-tasks/phpstan/tasks") ||
      url.startsWith("/static-tasks/pmd/tasks")
    ) {
      return { data: [] };
    }
    throw new Error(`Unexpected apiClient.get call: ${url}`);
  }) as typeof apiClient.get;

  try {
    const activities = await fetchTaskActivities(
      [{ id: "project-1", name: "Demo Project" }] as any,
      20,
    );

    const intelligent = filterIntelligentActivities(activities, "");
    assert.equal(intelligent.length, 2);

    const intelligentStats = intelligent
      .map((activity) => activity.agentFindingStats)
      .filter(Boolean)
      .sort((left, right) => right.total - left.total);
    const intelligentStatuses = intelligent.map((activity) => activity.status);

    assert.deepEqual(
      intelligentStats,
      expectStatsArray([
        {
          critical: 1,
          high: 2,
          medium: 3,
          low: 1,
          total: 7,
        },
        {
          critical: 0,
          high: 1,
          medium: 2,
          low: 1,
          total: 4,
        },
      ]),
    );
    assert.ok(intelligentStatuses.includes("running"));
  } finally {
    apiClient.get = originalGet;
  }
});

function expectStatsArray(
  values: Array<{
    critical: number;
    high: number;
    medium: number;
    low: number;
    total: number;
  }>,
) {
  return values.sort((left, right) => right.total - left.total);
}

test("fetchTaskActivities falls back to effective severity stats when defect_summary is absent", async () => {
  const originalGet = apiClient.get;

  apiClient.get = (async (url: string) => {
    if (url === "/agent-tasks/") {
      return {
        data: [
          {
            id: "agent-fallback",
            project_id: "project-1",
            name: "智能扫描-Fallback",
            description: "[INTELLIGENT]智能扫描任务",
            task_type: "agent_audit",
            status: "completed",
            current_phase: null,
            current_step: null,
            total_files: 5,
            indexed_files: 5,
            analyzed_files: 5,
            files_with_findings: 1,
            total_chunks: 10,
            findings_count: 3,
            verified_count: 2,
            verified_critical_count: 0,
            verified_high_count: 1,
            verified_medium_count: 1,
            verified_low_count: 0,
            false_positive_count: 1,
            total_iterations: 2,
            tool_calls_count: 4,
            tokens_used: 300,
            critical_count: 1,
            high_count: 1,
            medium_count: 1,
            low_count: 0,
            quality_score: 0,
            security_score: null,
            created_at: "2026-03-13T08:00:00.000Z",
            started_at: "2026-03-13T08:01:00.000Z",
            completed_at: "2026-03-13T08:05:00.000Z",
            progress_percentage: 100,
            audit_scope: null,
            target_vulnerabilities: null,
            verification_level: null,
            exclude_patterns: null,
            target_files: null,
            error_message: null,
          },
        ],
      };
    }
    if (
      url.startsWith("/static-tasks/tasks") ||
      url.startsWith("/static-tasks/gitleaks/tasks") ||
      url.startsWith("/static-tasks/bandit/tasks") ||
      url.startsWith("/static-tasks/phpstan/tasks") ||
      url.startsWith("/static-tasks/pmd/tasks")
    ) {
      return { data: [] };
    }
    throw new Error(`Unexpected apiClient.get call: ${url}`);
  }) as typeof apiClient.get;

  try {
    const activities = await fetchTaskActivities(
      [{ id: "project-1", name: "Demo Project" }] as any,
      20,
    );

    const intelligent = filterIntelligentActivities(activities, "");
    assert.equal(intelligent.length, 1);
    assert.deepEqual(intelligent[0]?.agentFindingStats, {
      critical: 1,
      high: 1,
      medium: 1,
      low: 0,
      total: 3,
    });
  } finally {
    apiClient.get = originalGet;
  }
});
