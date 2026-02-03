/**
 * Admin Dashboard Page
 * Cyberpunk Terminal Aesthetic
 */

import { DatabaseManager } from "@/components/database/DatabaseManager";

export default function AdminDashboard() {
  return (
    <div className="space-y-6 p-6 cyber-bg-elevated min-h-screen font-mono relative">
      {/* Grid background */}
      <div className="absolute inset-0 cyber-grid-subtle pointer-events-none" />
      <div className="relative z-10">
        <DatabaseManager />
      </div>
    </div>
  );
}
