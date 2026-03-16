import type { CreateProjectForm, Project } from "@/shared/types";

type UploadZipFileResult = {
	success: boolean;
	message?: string;
};

interface CreateZipProjectWorkflowParams {
	input: CreateProjectForm;
	file: File;
	createProject: (input: CreateProjectForm) => Promise<Project>;
	deleteProject: (projectId: string) => Promise<void>;
	uploadZipFile: (
		projectId: string,
		file: File,
	) => Promise<UploadZipFileResult>;
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
	status: "creating" | "success" | "failed";
	message?: string;
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
	const { input, file, createProject, deleteProject, uploadZipFile } = params;
	const createdProject = await createProject({
		...input,
		source_type: "zip",
		repository_type: "other",
		repository_url: undefined,
	});

	try {
		const uploadResult = await uploadZipFile(createdProject.id, file);
		if (!uploadResult.success) {
			throw new Error(uploadResult.message || "压缩包上传失败");
		}
		return createdProject;
	} catch (error) {
		await deleteProject(createdProject.id);
		throw error;
	}
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

	for (const [index, item] of items.entries()) {
		onProgress?.({
			index,
			total: items.length,
			fileName: item.file.name,
			projectName: item.projectName,
			status: "creating",
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
