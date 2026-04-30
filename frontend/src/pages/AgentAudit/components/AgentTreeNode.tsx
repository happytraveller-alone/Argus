
import { useState, memo } from "react";
import { ChevronDown, ChevronRight, Bot, Cpu, Scan, FileSearch, ShieldCheck, Zap } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import type { AgentTreeNodeItemProps } from "../types";

const AGENT_TYPE_ICONS: Record<string, React.ReactNode> = {
  orchestrator: <Cpu className="w-4 h-4 text-violet-600 dark:text-violet-500" />,
  recon: <Scan className="w-4 h-4 text-teal-600 dark:text-teal-500" />,
  analysis: <FileSearch className="w-4 h-4 text-amber-600 dark:text-amber-500" />,
  verification: <ShieldCheck className="w-4 h-4 text-emerald-600 dark:text-emerald-500" />,
};

const AGENT_TYPE_BG: Record<string, string> = {
  orchestrator: 'bg-violet-500/15 border-violet-500/30',
  recon: 'bg-teal-500/15 border-teal-500/30',
  analysis: 'bg-amber-500/15 border-amber-500/30',
  verification: 'bg-emerald-500/15 border-emerald-500/30',
};

export const AgentTreeNodeItem = memo(function AgentTreeNodeItem({
  node,
  depth = 0,
  selectedId,
  highlightedId,
  onSelect,
  isLast = false
}: AgentTreeNodeItemProps & { isLast?: boolean }) {
  const [expanded, setExpanded] = useState(true);
  const hasChildren = node.children && node.children.length > 0;
  const isSelected = selectedId === node.agent_id;
  const isHighlighted = highlightedId === node.agent_id;
  const isRunning = node.status === 'running';
  const isCompleted = node.status === 'completed';
  const isFailed = node.status === 'failed';

  const typeIcon = AGENT_TYPE_ICONS[node.agent_type] || <Bot className="w-3.5 h-3.5 text-muted-foreground" />;
  const typeBg = AGENT_TYPE_BG[node.agent_type] || 'bg-muted border-border';
  const verifiedFindingsCount =
    node.verified_findings_count ?? node.findings_count ?? 0;

  const indent = depth * 24;

  return (
    <div className="relative">
      {/* 树形连接线 */}
      {depth > 0 && (
        <>
          {/* 垂直线 - 从父节点延伸下来 */}
          <div
            className="absolute border-l-2 border-border"
            style={{
              left: `${indent - 12}px`,
              top: 0,
              height: isLast ? '20px' : '100%',
            }}
          />
          {/* 水平线 - 连接到当前节点 */}
          <div
            className="absolute border-t-2 border-border"
            style={{
              left: `${indent - 12}px`,
              top: '20px',
              width: '12px',
            }}
          />
        </>
      )}

      {/* Node item */}
      <div
        id={`agent-node-${node.agent_id}`}
        className={`
          relative flex items-center gap-2 py-2 px-2 cursor-pointer rounded-md
          ${isSelected
            ? 'bg-primary/15 border-2 border-primary shadow-[0_0_12px_rgba(59,130,246,0.4)]'
            : isRunning
              ? 'bg-emerald-950/30 border-2 border-emerald-500 shadow-[0_0_10px_rgba(52,211,153,0.3)]'
              : isCompleted
                ? 'bg-card/60 border border-emerald-600'
                : isFailed
                  ? 'bg-rose-950/20 border border-rose-500'
                  : node.status === 'waiting'
                    ? 'bg-amber-950/20 border border-amber-500'
                    : 'bg-card/40 border border-border hover:border-slate-500'
          }
          ${isHighlighted ? 'ring-2 ring-primary/60' : ''}
        `}
        style={{ marginLeft: `${indent}px` }}
        onClick={() => onSelect(node.agent_id)}
      >
        {/* Expand/collapse button */}
        {hasChildren ? (
          <button
            onClick={(e) => { e.stopPropagation(); setExpanded(!expanded); }}
            className="flex-shrink-0 w-5 h-5 flex items-center justify-center rounded hover:bg-muted"
          >
            {expanded ? (
              <ChevronDown className="w-4 h-4 text-muted-foreground" />
            ) : (
              <ChevronRight className="w-4 h-4 text-muted-foreground" />
            )}
          </button>
        ) : (
          <span className="w-5" />
        )}

        {/* Status indicator */}
        <div className="relative flex-shrink-0">
          <div className={`
            w-2.5 h-2.5 rounded-full
            ${isRunning ? 'bg-emerald-500' : ''}
            ${isCompleted ? 'bg-emerald-500' : ''}
            ${isFailed ? 'bg-rose-500' : ''}
            ${node.status === 'waiting' ? 'bg-amber-500' : ''}
            ${node.status === 'created' ? 'bg-slate-400' : ''}
          `} />
          {isRunning && (
            <div className="absolute inset-0 w-2.5 h-2.5 rounded-full bg-emerald-500 animate-ping opacity-50" />
          )}
        </div>

        {/* Agent type icon */}
        <div className={`flex-shrink-0 p-1 rounded border ${typeBg}`}>
          {typeIcon}
        </div>

        {/* Agent name */}
        <span className={`
          text-sm font-mono truncate flex-1
          ${isSelected ? 'text-foreground font-semibold' : 'text-foreground'}
        `}>
          {node.agent_name}
        </span>

        {/* Metrics */}
        <div className="flex items-center gap-1.5 flex-shrink-0">
          {(node.iterations ?? 0) > 0 && (
            <div className="flex items-center gap-1 text-xs text-muted-foreground font-mono bg-muted px-1.5 py-0.5 rounded border border-border">
              <Zap className="w-3 h-3" />
              <span>{node.iterations}</span>
            </div>
          )}

          {!node.parent_agent_id && verifiedFindingsCount > 0 && (
            <Badge className="h-5 px-2 text-xs bg-rose-500/20 text-rose-300 border border-rose-500/40 font-mono font-bold">
              {verifiedFindingsCount}
            </Badge>
          )}
        </div>
      </div>

      {/* Children */}
      {expanded && hasChildren && (
        <div className="relative">
          {node.children.map((child, index) => (
            <AgentTreeNodeItem
              key={child.agent_id}
              node={child}
              depth={depth + 1}
              selectedId={selectedId}
              highlightedId={highlightedId}
              onSelect={onSelect}
              isLast={index === node.children.length - 1}
            />
          ))}
        </div>
      )}
    </div>
  );
});

export default AgentTreeNodeItem;
