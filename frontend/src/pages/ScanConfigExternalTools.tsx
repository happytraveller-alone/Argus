import { Wrench } from "lucide-react";
import SkillToolsPanel from "@/pages/intelligent-scan/SkillToolsPanel";

export default function ScanConfigExternalTools() {
  return (
    <div className="relative flex min-h-screen flex-col bg-background p-6">
      <div className="absolute inset-0 cyber-grid-subtle pointer-events-none" />
      <div className="relative z-10 flex flex-1 flex-col">
        <div className="cyber-card flex flex-1 flex-col p-5">
          <div className="section-header mb-1">
            <Wrench className="w-4 h-4 text-primary" />
            <div className="font-mono font-bold uppercase text-sm text-foreground">
              外部工具列表
            </div>
          </div>
          <SkillToolsPanel />
        </div>
      </div>
    </div>
  );
}
