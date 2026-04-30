import { Globe, Package } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import type { Project } from "@/shared/types";
import { isRepositoryProject } from "@/shared/utils/projectUtils";

export default function ProjectCard({
  project,
  selected,
  onSelect,
}: {
  project: Project;
  selected: boolean;
  onSelect: () => void;
}) {
  const isRepo = isRepositoryProject(project);

  return (
    <div
      className={`flex items-center gap-3 p-3 cursor-pointer rounded transition-all ${
        selected
          ? "bg-primary/10 border border-primary/50"
          : "hover:bg-muted border border-transparent"
      }`}
      onClick={onSelect}
    >
      <Checkbox
        checked={selected}
        className="border-border data-[state=checked]:bg-primary data-[state=checked]:border-primary"
      />

      <div className={`p-1.5 rounded ${isRepo ? "bg-blue-500/20" : "bg-amber-500/20"}`}>
        {isRepo ? (
          <Globe className="w-4 h-4 text-blue-600 dark:text-blue-400" />
        ) : (
          <Package className="w-4 h-4 text-amber-600 dark:text-amber-400" />
        )}
      </div>

      <div className="flex-1 min-w-0 overflow-hidden">
        <div className="flex items-center gap-2">
          <span
            className={`font-mono text-base truncate ${
              selected ? "text-foreground font-bold" : "text-foreground"
            }`}
          >
            {project.name}
          </span>
          <Badge
            className={`text-xs px-1 py-0 font-mono ${
              isRepo
                ? "bg-blue-500/20 text-blue-600 dark:text-blue-400 border-blue-500/30"
                : "bg-amber-500/20 text-amber-600 dark:text-amber-400 border-amber-500/30"
            }`}
          >
            {isRepo ? "REPO" : "ZIP"}
          </Badge>
        </div>
        {project.description && (
          <p
            className="text-sm text-muted-foreground mt-0.5 font-mono line-clamp-2"
            title={project.description}
          >
            {project.description}
          </p>
        )}
      </div>
    </div>
  );
}
