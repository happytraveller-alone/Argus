export interface ToolTestPreset extends Record<string, unknown> {
  project_name: "libplist";
  file_path: string;
  function_name: string;
  line_start: number | null;
  line_end: number | null;
  tool_input: Record<string, unknown>;
}

export interface SkillDetailResponse {
  enabled: boolean;
  skill_id: string;
  name: string;
  namespace: string;
  summary: string;
  category: string;
  goal: string;
  task_list: string[];
  input_checklist: string[];
  example_input: string;
  pitfalls: string[];
  sample_prompts: string[];
  entrypoint: string;
  mirror_dir: string;
  source_root: string;
  source_dir: string;
  source_skill_md: string;
  aliases: string[];
  has_scripts: boolean;
  has_bin: boolean;
  has_assets: boolean;
  files_count: number;
  workflow_content: string | null;
  workflow_truncated: boolean | null;
  workflow_error: string | null;
  test_supported: boolean;
  test_mode: "single_skill_strict" | "structured_tool" | "disabled";
  test_reason: string | null;
  default_test_project_name: "libplist";
  tool_test_preset: ToolTestPreset | null;
}

export interface SkillTestCleanupStatus {
  success: boolean;
  temp_dir: string;
  error: string | null;
}

export interface SkillTestResult {
  skill_id: string;
  final_text: string;
  project_name: string;
  test_mode: "single_skill_strict" | "structured_tool" | "disabled";
  default_test_project_name: string;
  project_root: string;
  tool_name: string | null;
  target_function: string | null;
  resolved_file_path: string | null;
  resolved_line_start: number | null;
  resolved_line_end: number | null;
  runner_image: string | null;
  input_payload: Record<string, unknown> | null;
  cleanup: SkillTestCleanupStatus;
}

export interface SkillTestEvent {
  id: number;
  type: string;
  message?: string;
  tool_name?: string;
  tool_input?: unknown;
  tool_output?: unknown;
  metadata?: Record<string, unknown>;
  data?: SkillTestResult | Record<string, unknown> | null;
  ts: number;
}
