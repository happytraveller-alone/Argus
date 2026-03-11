import { Wrench } from "lucide-react";
import SkillToolsPanel from "@/pages/intelligent-scan/SkillToolsPanel";

export default function ScanConfigExternalTools() {
  return (
    <div className="space-y-6 p-6 bg-background min-h-screen relative">
      <div className="absolute inset-0 cyber-grid-subtle pointer-events-none" />
      <div className="relative z-10 space-y-6">
        <div className="cyber-card p-5 space-y-4">
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
