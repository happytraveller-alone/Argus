import { Plus, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { PROJECT_ACTION_BTN_SUBTLE } from "../constants";

interface ProjectsToolbarProps {
	searchTerm: string;
	searchPlaceholder: string;
	createButtonLabel: string;
	onSearchChange: (value: string) => void;
	onCreateProjectClick: () => void;
}

export default function ProjectsToolbar({
	searchTerm,
	searchPlaceholder,
	createButtonLabel,
	onSearchChange,
	onCreateProjectClick,
}: ProjectsToolbarProps) {
	return (
		<div className="flex items-center justify-between gap-3 mb-3">
			<div className="relative w-full max-w-xl">
				<Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
				<Input
					value={searchTerm}
					onChange={(event) => onSearchChange(event.target.value)}
					placeholder={searchPlaceholder}
					className="h-9 font-mono pl-9"
				/>
			</div>
			<Button
				size="sm"
				className={`${PROJECT_ACTION_BTN_SUBTLE} h-9 px-3 shrink-0`}
				onClick={onCreateProjectClick}
			>
				<Plus className="w-4 h-4 mr-2" />
				{createButtonLabel}
			</Button>
		</div>
	);
}
