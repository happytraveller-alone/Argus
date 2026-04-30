import { Wrench } from "lucide-react";
import SkillToolsPanel from "@/pages/intelligent-scan/SkillToolsPanel";
import type { ExternalToolResourcePayload } from "@/shared/api/database";

interface ScanConfigExternalToolsProps {
	initialResources?: ExternalToolResourcePayload[];
}

export default function ScanConfigExternalTools({
	initialResources = [],
}: ScanConfigExternalToolsProps) {
	return (
		<div className="flex min-h-screen flex-col bg-background p-6">
			<div className="flex flex-1 flex-col">
				<div className="flex flex-1 flex-col">
					<div className="mb-4 flex items-center gap-3 border-b border-border pb-3">
						<Wrench className="w-4 h-4 text-primary" />
						<div className="font-mono font-bold uppercase text-sm text-foreground">
							外部工具列表
						</div>
					</div>
					<SkillToolsPanel initialResources={initialResources} />
				</div>
			</div>
		</div>
	);
}
