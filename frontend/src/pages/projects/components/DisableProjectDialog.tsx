import { Trash2 } from "lucide-react";
import {
	AlertDialog,
	AlertDialogAction,
	AlertDialogCancel,
	AlertDialogContent,
	AlertDialogDescription,
	AlertDialogFooter,
	AlertDialogHeader,
	AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import type { Project } from "@/shared/types";

interface DisableProjectDialogProps {
	open: boolean;
	project: Project | null;
	onOpenChange: (open: boolean) => void;
	onConfirm: () => void;
}

export default function DisableProjectDialog({
	open,
	project,
	onOpenChange,
	onConfirm,
}: DisableProjectDialogProps) {
	return (
		<AlertDialog open={open} onOpenChange={onOpenChange}>
			<AlertDialogContent className="cyber-card border-border cyber-dialog p-0">
				<AlertDialogHeader className="p-6">
					<AlertDialogTitle className="font-mono text-lg uppercase tracking-wider flex items-center gap-2 text-foreground">
						<Trash2 className="w-5 h-5 text-rose-400" />
						确认禁用
					</AlertDialogTitle>
					<AlertDialogDescription className="text-muted-foreground font-mono">
						您确定要禁用{" "}
						<span className="font-bold text-rose-400">"{project?.name}"</span>{" "}
						吗？
					</AlertDialogDescription>
				</AlertDialogHeader>

				<div className="px-6 pb-6">
					<div className="bg-sky-500/10 border border-sky-500/30 p-4 rounded">
						<p className="text-sky-300 font-bold mb-2 font-mono uppercase text-sm">
							系统通知:
						</p>
						<ul className="list-none text-sky-400/80 space-y-1 text-xs font-mono">
							<li className="flex items-center gap-2">
								<span className="text-sky-400">&gt;</span> 项目将被禁用
							</li>
							<li className="flex items-center gap-2">
								<span className="text-sky-400">&gt;</span> 扫描数据保留
							</li>
							<li className="flex items-center gap-2">
								<span className="text-sky-400">&gt;</span> 可通过状态切换按钮恢复
							</li>
						</ul>
					</div>
				</div>

				<AlertDialogFooter className="p-4 border-t border-border bg-muted/50">
					<AlertDialogCancel className="cyber-btn-outline">
						取消
					</AlertDialogCancel>
					<AlertDialogAction
						onClick={onConfirm}
						className="cyber-btn bg-rose-500/90 border-rose-500/50 text-foreground hover:bg-rose-500"
					>
						确认禁用
					</AlertDialogAction>
				</AlertDialogFooter>
			</AlertDialogContent>
		</AlertDialog>
	);
}
