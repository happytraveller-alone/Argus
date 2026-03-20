import type { Dispatch, SetStateAction } from "react";
import { Rows2, Rows3, StretchHorizontal } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import type { DataTableDensity } from "./types";

const OPTIONS: Array<{
  value: DataTableDensity;
  label: string;
  icon: typeof Rows3;
}> = [
  { value: "compact", label: "紧凑", icon: Rows2 },
  { value: "comfortable", label: "舒适", icon: Rows3 },
  { value: "spacious", label: "宽松", icon: StretchHorizontal },
];

export function DataTableDensityToggle({
  density,
  onChange,
}: {
  density: DataTableDensity;
  onChange: Dispatch<SetStateAction<DataTableDensity>> | ((next: DataTableDensity) => void);
}) {
  const ActiveIcon = OPTIONS.find((item) => item.value === density)?.icon ?? Rows3;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button type="button" variant="outline" size="sm" className="cyber-btn-outline h-9 px-3">
          <ActiveIcon className="h-4 w-4" />
          密度
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        {OPTIONS.map((option) => {
          const Icon = option.icon;
          return (
            <DropdownMenuItem
              key={option.value}
              onSelect={() => onChange(option.value)}
            >
              <Icon className="h-4 w-4" />
              {option.label}
            </DropdownMenuItem>
          );
        })}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
