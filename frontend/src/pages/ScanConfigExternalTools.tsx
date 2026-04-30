import { Wrench } from "lucide-react";

export default function ScanConfigExternalTools() {
	return (
		<div className="flex min-h-screen flex-col bg-background p-6">
			<div className="flex flex-1 flex-col">
				<div className="mb-4 flex items-center gap-3 border-b border-border pb-3">
					<Wrench className="w-4 h-4 text-primary" />
					<div className="font-mono font-bold uppercase text-sm text-foreground">
						外部工具列表
					</div>
				</div>
				<div className="flex flex-1 items-center justify-center text-muted-foreground">
					暂无外部工具
				</div>
			</div>
		</div>
	);
}
