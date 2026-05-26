import type { CreateProjectForm, Project } from "@/shared/types";

type UploadZipFileResult = {
	success: boolean;
	message?: string;
};

interface CreateZipProjectWorkflowParams {
	input: CreateProjectForm;
	file: File;
	createProjectWithZip: (
		input: CreateProjectForm,
		file: File,
	) => Promise<Project>;
}

interface UpdateProjectWorkflowParams {
	projectId: string;
	input: Partial<CreateProjectForm>;
	zipFile?: File | null;
	updateProject: (
		projectId: string,
		input: Partial<CreateProjectForm>,
	) => Promise<Project>;
	uploadZipFile: (
		projectId: string,
		file: File,
	) => Promise<UploadZipFileResult>;
}

export interface BatchCreateZipProjectItem {
	file: File;
	projectName: string;
}

export interface BatchCreateZipProjectsFailure {
	fileName: string;
	projectName: string;
	message: string;
}

export interface BatchCreateZipProjectsResult {
	total: number;
	successCount: number;
	failureCount: number;
	successes: Project[];
	failures: BatchCreateZipProjectsFailure[];
}

export interface BatchCreateZipProjectsProgressEvent {
	index: number;
	total: number;
	fileName: string;
	projectName: string;
	status: "importing" | "indexing" | "success" | "failed";
	message?: string;
	completedSteps?: number;
	totalSteps?: number;
	project?: Project;
}

interface CreateZipProjectsWorkflowParams {
	items: BatchCreateZipProjectItem[];
	sharedInput: Omit<CreateProjectForm, "name">;
	createZipProject: (input: CreateProjectForm, file: File) => Promise<Project>;
	onProgress?: (event: BatchCreateZipProjectsProgressEvent) => void;
}

export async function createZipProjectWorkflow(
	params: CreateZipProjectWorkflowParams,
) {
	const { input, file, createProjectWithZip } = params;
	return createProjectWithZip(
		{
			...input,
			source_type: "zip",
			repository_type: "other",
			repository_url: undefined,
		},
		file,
	);
}

export async function updateProjectWorkflow(
	params: UpdateProjectWorkflowParams,
) {
	const { projectId, input, zipFile, updateProject, uploadZipFile } = params;
	const updatedProject = await updateProject(projectId, input);
	if (!zipFile) {
		return updatedProject;
	}

	const uploadResult = await uploadZipFile(projectId, zipFile);
	if (!uploadResult.success) {
		throw new Error(uploadResult.message || "ZIP文件上传失败");
	}

	return updatedProject;
}

export async function createZipProjectsWorkflow(
	params: CreateZipProjectsWorkflowParams,
): Promise<BatchCreateZipProjectsResult> {
	const { items, sharedInput, createZipProject, onProgress } = params;
	const successes: Project[] = [];
	const failures: BatchCreateZipProjectsFailure[] = [];

	const totalSteps = Math.max(items.length * 2, 1);

	for (const [index, item] of items.entries()) {
		onProgress?.({
			index,
			total: items.length,
			fileName: item.file.name,
			projectName: item.projectName,
			status: "importing",
			message: "导入项目",
			completedSteps: index * 2,
			totalSteps,
		});

		onProgress?.({
			index,
			total: items.length,
			fileName: item.file.name,
			projectName: item.projectName,
			status: "indexing",
			message: "建立 codegraph 索引",
			completedSteps: index * 2 + 1,
			totalSteps,
		});

		try {
			const project = await createZipProject(
				{
					...sharedInput,
					name: item.projectName,
					description: sharedInput.description || "",
				},
				item.file,
			);
			successes.push(project);
			onProgress?.({
				index,
				total: items.length,
				fileName: item.file.name,
				projectName: item.projectName,
				status: "success",
				message: buildCodegraphCompletionMessage(project),
				completedSteps: Math.min(index * 2 + 2, totalSteps),
				totalSteps,
				project,
			});
		} catch (error) {
			const message =
				error instanceof Error ? error.message : "批量创建项目失败";
			failures.push({
				fileName: item.file.name,
				projectName: item.projectName,
				message,
			});
			onProgress?.({
				index,
				total: items.length,
				fileName: item.file.name,
				projectName: item.projectName,
				status: "failed",
				message,
				completedSteps: Math.min(index * 2 + 2, totalSteps),
				totalSteps,
			});
		}
	}

	return {
		total: items.length,
		successCount: successes.length,
		failureCount: failures.length,
		successes,
		failures,
	};
}

function buildCodegraphCompletionMessage(project: Project): string {
	const state = project.codegraph_index;
	if (!state) {
		return "项目已创建";
	}
	if (state.status === "ready") {
		return state.languages_indexed?.length
			? `codegraph 索引已建立 · ${state.languages_indexed.join(", ")}`
			: "codegraph 索引已建立";
	}
	if (state.status === "failed") {
		return state.message || "codegraph 索引建立失败，智能扫描会降级继续";
	}
	return state.message || "项目已创建";
}
