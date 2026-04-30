import { lazy, Suspense } from "react";
import ProjectsPage from "@/pages/projects/ProjectsPage";
import { createApiProjectsPageDataSource } from "@/pages/projects/data/createApiProjectsPageDataSource";

const CreateProjectScanDialog = lazy(
	() => import("@/components/scan/CreateProjectScanDialog"),
);

const projectsPageDataSource = createApiProjectsPageDataSource();

export default function Projects() {
	return (
		<ProjectsPage
			dataSource={projectsPageDataSource}
			renderCreateScanDialog={(props) =>
				props.open ? (
					<Suspense fallback={null}>
						<CreateProjectScanDialog {...props} />
					</Suspense>
				) : null
			}
		/>
	);
}
