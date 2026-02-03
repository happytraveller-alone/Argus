/**
 * Admin Dashboard Page
 * Cyberpunk Terminal Aesthetic
 */

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { DatabaseManager } from "@/components/database/DatabaseManager";
import { SystemConfig } from "@/components/system/SystemConfig";
import { Settings, Database } from "lucide-react";

export default function AdminDashboard() {
  return (
    <div className="space-y-6 p-6 cyber-bg-elevated min-h-screen font-mono relative">
      {/* Grid background */}
      <div className="absolute inset-0 cyber-grid-subtle pointer-events-none" />

      {/* Main Content Tabs */}
      <Tabs defaultValue="config" className="w-full relative z-10">
        <TabsList className="grid w-full grid-cols-2 bg-muted border border-border p-1 h-auto gap-1 rounded-lg mb-6">
          <TabsTrigger
            value="config"
            className="data-[state=active]:bg-primary data-[state=active]:text-foreground font-mono font-bold uppercase py-3 text-muted-foreground transition-all rounded text-sm flex items-center gap-2"
          >
            <Settings className="w-4 h-4" />
            系统配置
          </TabsTrigger>
          <TabsTrigger
            value="data"
            className="data-[state=active]:bg-primary data-[state=active]:text-foreground font-mono font-bold uppercase py-3 text-muted-foreground transition-all rounded text-sm flex items-center gap-2"
          >
            <Database className="w-4 h-4" />
            数据管理
          </TabsTrigger>
        </TabsList>

        {/* System Config */}
        <TabsContent value="config" className="flex flex-col gap-6">
          <SystemConfig />
        </TabsContent>

        {/* Data Management */}
        <TabsContent value="data" className="space-y-6">
          <DatabaseManager />
        </TabsContent>
      </Tabs>
    </div>
  );
}
