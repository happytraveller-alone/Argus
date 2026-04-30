import { useEffect, useState } from "react";
import type { ScanCreateMode } from "@/components/scan/CreateProjectScanDialog";
import type { Project } from "@/shared/types";

export function useProjectsBrowserState() {
	const [searchTerm, setSearchTerm] = useState("");
	const [projectPage, setProjectPage] = useState(1);
	const [showCreateDialog, setShowCreateDialog] = useState(false);
	const [createScanState, setCreateScanState] = useState({
		open: false,
		preselectedProjectId: "",
		initialMode: "static" as ScanCreateMode,
		navigateOnSuccess: true,
	});
	const [editProjectState, setEditProjectState] = useState<{
		open: boolean;
		project: Project | null;
	}>({
		open: false,
		project: null,
	});

	useEffect(() => {
		setProjectPage(1);
	}, [searchTerm]);

	function openCreateScanDialog(
		initialMode: ScanCreateMode = "static",
		preselectedProjectId = "",
		options?: { navigateOnSuccess?: boolean },
	) {
		setCreateScanState({
			open: true,
			preselectedProjectId,
			initialMode,
			navigateOnSuccess: options?.navigateOnSuccess ?? true,
		});
	}

	function closeCreateScanDialog() {
		setCreateScanState({
			open: false,
			preselectedProjectId: "",
			initialMode: "static",
			navigateOnSuccess: true,
		});
	}

	return {
		searchTerm,
		setSearchTerm,
		projectPage,
		setProjectPage,
		showCreateDialog,
		setShowCreateDialog,
		createScanState,
		editProjectState,
		setEditProjectState,
		openCreateScanDialog,
		closeCreateScanDialog,
	};
}
