import { useMemo } from "react";
import { Navigate, useLocation, useParams } from "react-router-dom";
import {
	appendReturnTo,
	buildFindingDetailPath,
	normalizeReturnToPath,
} from "@/shared/utils/findingRoute";

export default function StaticFindingDetail() {
	const { taskId, findingId } = useParams<{ taskId: string; findingId: string }>();
	const location = useLocation();

	const redirectPath = useMemo(() => {
		const normalizedTaskId = String(taskId || "").trim();
		const normalizedFindingId = String(findingId || "").trim();
		if (!normalizedTaskId || !normalizedFindingId) {
			return "/projects";
		}

		const targetPath = buildFindingDetailPath({
			source: "static",
			taskId: normalizedTaskId,
			findingId: normalizedFindingId,
		});
		const searchParams = new URLSearchParams(location.search);
		const returnTo = normalizeReturnToPath(searchParams.get("returnTo"));
		return appendReturnTo(targetPath, returnTo);
	}, [findingId, location.search, taskId]);

	return <Navigate to={redirectPath} replace />;
}
