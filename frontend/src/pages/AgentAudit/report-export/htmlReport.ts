import { marked } from "marked";
import type { AgentTask } from "@/shared/api/agentTasks";

export async function generateReportExportHtml(
  markdown: string,
  task: AgentTask,
): Promise<string> {
  const contentHtml = await marked.parse(markdown);
  const score = task.security_score || 0;
  const scoreDisplay = score.toFixed(0);
  const totalFindings = task.findings_count || 0;
  const criticalCount = task.critical_count || 0;
  const highCount = task.high_count || 0;
  const mediumCount = task.medium_count || 0;
  const lowCount = task.low_count || 0;
  const verifiedCount = task.verified_count || 0;
  const taskName = task.name || `Task ${task.id.slice(0, 8)}`;
  const generateDate = new Date().toLocaleString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });

  const getScoreGrade = (value: number) => {
    if (value >= 90) return { grade: "A", color: "#10b981", bg: "rgba(16, 185, 129, 0.1)" };
    if (value >= 80) return { grade: "B", color: "#22c55e", bg: "rgba(34, 197, 94, 0.1)" };
    if (value >= 70) return { grade: "C", color: "#eab308", bg: "rgba(234, 179, 8, 0.1)" };
    if (value >= 60) return { grade: "D", color: "#f97316", bg: "rgba(249, 115, 22, 0.1)" };
    return { grade: "F", color: "#ef4444", bg: "rgba(239, 68, 68, 0.1)" };
  };
  const scoreInfo = getScoreGrade(score);
  const circumference = 2 * Math.PI * 40;
  const strokeDashoffset = circumference - (score / 100) * circumference;

  return `<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>安全扫描报告 - ${taskName}</title>
  <style>
    :root {
      --bg-body: #06060a;
      --bg-primary: #0a0a0f;
      --bg-secondary: #0f0f15;
      --bg-tertiary: #16161f;
      --bg-card: #12121a;
      --text-primary: #f8fafc;
      --text-secondary: #94a3b8;
      --text-muted: #64748b;
      --accent: #ff6b2c;
      --accent-glow: rgba(255, 107, 44, 0.2);
      --border: #1e293b;
      --success: #10b981;
      --critical: #dc2626;
      --critical-bg: rgba(220, 38, 38, 0.12);
      --high: #f97316;
      --high-bg: rgba(249, 115, 22, 0.1);
      --medium: #eab308;
      --low: #3b82f6;
      --code-bg: #0d1117;
    }
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      background: var(--bg-body);
      color: var(--text-secondary);
      line-height: 1.6;
      font-size: 14px;
    }
    .container { max-width: 900px; margin: 0 auto; padding: 0 1.5rem; }
    .header { background: linear-gradient(135deg, var(--bg-primary), var(--bg-secondary)); border-bottom: 1px solid var(--border); padding: 1.25rem 0; position: relative; }
    .header::before { content: ""; position: absolute; top: -50%; right: -10%; width: 300px; height: 300px; background: radial-gradient(circle, var(--accent-glow) 0%, transparent 70%); pointer-events: none; }
    .header-content { position: relative; display: flex; justify-content: space-between; align-items: center; }
    .header-title { font-size: 1.25rem; font-weight: 700; color: var(--text-primary); text-align: center; flex: 1; margin: 0 1rem; }
    .header-meta { text-align: right; font-size: 0.7rem; color: var(--text-muted); }
    .stats-section { padding: 1rem 0; background: var(--bg-primary); border-bottom: 1px solid var(--border); }
    .stats-grid { display: flex; align-items: center; gap: 1.25rem; }
    .score-ring-container { display: flex; align-items: center; gap: 0.75rem; padding: 0.75rem 1rem; background: var(--bg-card); border-radius: 12px; border: 1px solid var(--border); }
    .score-ring { position: relative; width: 56px; height: 56px; }
    .score-ring svg { transform: rotate(-90deg); width: 56px; height: 56px; }
    .score-ring-bg { fill: none; stroke: var(--border); stroke-width: 5; }
    .score-ring-progress { fill: none; stroke: ${scoreInfo.color}; stroke-width: 5; stroke-linecap: round; stroke-dasharray: ${circumference}; stroke-dashoffset: ${strokeDashoffset}; filter: drop-shadow(0 0 4px ${scoreInfo.color}40); }
    .score-ring-content { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; }
    .score-value { font-size: 1.1rem; font-weight: 800; color: ${scoreInfo.color}; line-height: 1; font-family: 'SF Mono', monospace; }
    .score-grade { font-size: 0.55rem; font-weight: 600; color: ${scoreInfo.color}; background: ${scoreInfo.bg}; padding: 0.1rem 0.3rem; border-radius: 3px; margin-top: 0.15rem; }
    .score-label { font-size: 0.65rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.05em; }
    .stats-cards { display: flex; gap: 0.5rem; flex: 1; }
    .stat-card { flex: 1; background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; padding: 0.6rem 0.75rem; }
    .stat-card-header { display: flex; align-items: center; gap: 0.4rem; margin-bottom: 0.25rem; }
    .stat-card-icon { width: 18px; height: 18px; border-radius: 4px; display: flex; align-items: center; justify-content: center; font-size: 0.65rem; font-weight: 700; }
    .stat-card-icon.critical { background: var(--critical-bg); color: var(--critical); }
    .stat-card-icon.high { background: var(--high-bg); color: var(--high); }
    .stat-card-icon.total { background: rgba(99, 102, 241, 0.08); color: #6366f1; }
    .stat-card-icon.verified { background: rgba(16,185,129,0.1); color: var(--success); }
    .stat-card-label { font-size: 0.6rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.05em; }
    .stat-card-value { font-size: 1.25rem; font-weight: 700; color: var(--text-primary); font-family: 'SF Mono', monospace; line-height: 1; }
    .stat-card-value.critical { color: var(--critical); }
    .stat-card-value.high { color: var(--high); }
    .severity-section { padding: 0.75rem 0; background: var(--bg-primary); }
    .severity-bar-wrap { display: flex; align-items: center; gap: 1rem; }
    .severity-bar-title { font-size: 0.65rem; color: var(--text-muted); text-transform: uppercase; white-space: nowrap; }
    .severity-bar { flex: 1; display: flex; height: 6px; border-radius: 3px; overflow: hidden; background: var(--border); }
    .severity-segment { height: 100%; }
    .severity-segment.critical { background: var(--critical); }
    .severity-segment.high { background: var(--high); }
    .severity-segment.medium { background: var(--medium); }
    .severity-segment.low { background: var(--low); }
    .severity-legend { display: flex; gap: 0.75rem; }
    .severity-legend-item { display: flex; align-items: center; gap: 0.25rem; font-size: 0.6rem; color: var(--text-muted); }
    .severity-dot { width: 6px; height: 6px; border-radius: 50%; }
    .severity-dot.critical { background: var(--critical); }
    .severity-dot.high { background: var(--high); }
    .severity-dot.medium { background: var(--medium); }
    .severity-dot.low { background: var(--low); }
    .main-content { padding: 1.5rem 0; background: var(--bg-body); }
    .content-wrapper { background: var(--bg-primary); border-radius: 12px; border: 1px solid var(--border); padding: 1.5rem; }
    h1, h2, h3, h4 { color: var(--text-primary); font-weight: 600; letter-spacing: -0.01em; }
    h1 { font-size: 1.25rem; margin: 1.5rem 0 0.75rem; padding-bottom: 0.5rem; border-bottom: 2px solid var(--accent); display: flex; align-items: center; gap: 0.5rem; }
    h1::before { content: "§"; color: var(--accent); font-weight: 400; }
    h2 { font-size: 1.1rem; margin: 1.25rem 0 0.5rem; padding-bottom: 0.35rem; border-bottom: 1px solid var(--border); }
    h2::before { content: "//"; color: var(--accent); margin-right: 0.35rem; font-weight: 400; opacity: 0.7; }
    h3 { font-size: 1rem; margin: 1rem 0 0.4rem; padding-left: 0.75rem; border-left: 2px solid var(--accent); }
    h4 { font-size: 0.9rem; margin: 0.75rem 0 0.35rem; color: var(--text-secondary); }
    p { margin-bottom: 0.6rem; font-size: 0.875rem; }
    pre { background: var(--code-bg); border: 1px solid var(--border); border-radius: 8px; margin: 0.75rem 0; overflow: hidden; font-size: 0.8rem; }
    pre::before { content: "CODE"; display: block; background: var(--bg-tertiary); padding: 0.35rem 0.75rem; font-size: 0.6rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.05em; border-bottom: 1px solid var(--border); }
    pre code { display: block; padding: 0.75rem; overflow-x: auto; line-height: 1.5; }
    code { font-family: 'SF Mono', 'Monaco', 'Consolas', monospace; font-size: 0.85em; color: #e2e8f0; }
    p code, li code, td code { background: var(--bg-tertiary); color: var(--accent); padding: 0.15em 0.35em; border-radius: 4px; font-size: 0.8em; border: 1px solid var(--border); }
    table { width: 100%; border-collapse: collapse; margin: 0.75rem 0; background: var(--bg-card); border-radius: 8px; overflow: hidden; border: 1px solid var(--border); font-size: 0.8rem; }
    th { padding: 0.6rem 0.75rem; text-align: left; font-weight: 600; font-size: 0.65rem; color: var(--text-secondary); text-transform: uppercase; background: var(--bg-tertiary); border-bottom: 1px solid var(--border); }
    td { padding: 0.5rem 0.75rem; border-bottom: 1px solid var(--border); }
    tr:last-child td { border-bottom: none; }
    tr:hover td { background: rgba(255, 255, 255, 0.02); }
    ul, ol { margin: 0.5rem 0 0.5rem 1.25rem; }
    li { margin-bottom: 0.25rem; font-size: 0.875rem; }
    li::marker { color: var(--accent); }
    blockquote { margin: 0.75rem 0; padding: 0.6rem 1rem; background: var(--bg-card); border-left: 3px solid var(--accent); border-radius: 0 8px 8px 0; font-size: 0.85rem; }
    blockquote p:last-child { margin-bottom: 0; }
    a { color: var(--accent); text-decoration: none; }
    a:hover { text-decoration: underline; }
    hr { border: none; height: 1px; background: linear-gradient(90deg, transparent, var(--border), transparent); margin: 1.5rem 0; }
    strong { color: var(--text-primary); font-weight: 600; }
    em { color: var(--text-muted); }
    .report-footer { padding: 1rem 0; background: var(--bg-primary); border-top: 1px solid var(--border); text-align: center; }
    .footer-content { display: flex; align-items: center; justify-content: center; gap: 0.5rem; font-size: 0.7rem; color: var(--text-muted); }
    @media (max-width: 768px) {
      .container { padding: 0 1rem; }
      .stats-grid { flex-direction: column; gap: 0.75rem; }
      .score-ring-container { width: 100%; justify-content: center; }
      .stats-cards { flex-wrap: wrap; }
      .stat-card { min-width: calc(50% - 0.25rem); }
      .severity-bar-wrap { flex-direction: column; align-items: stretch; gap: 0.5rem; }
      .severity-legend { justify-content: center; }
      .content-wrapper { padding: 1rem; }
    }
    @media print {
      :root { --bg-body: #fff; --bg-primary: #fff; --bg-secondary: #f8fafc; --bg-tertiary: #f1f5f9; --bg-card: #fff; --text-primary: #0f172a; --text-secondary: #475569; --text-muted: #64748b; --border: #e2e8f0; --code-bg: #f8fafc; }
      body { background: white; font-size: 11pt; }
      .header::before { display: none; }
      .content-wrapper { border: none; padding: 0; }
      pre { break-inside: avoid; }
      code { color: #1e293b; }
      p code, li code { background: #f1f5f9; color: #c2410c; }
      a { color: #2563eb; }
    }
  </style>
</head>
<body>
  <header class="header">
    <div class="container">
      <div class="header-content">
        <h1 class="header-title">${taskName}</h1>
        <div class="header-meta">${generateDate}</div>
      </div>
    </div>
  </header>
  <section class="stats-section">
    <div class="container">
      <div class="stats-grid">
        <div class="score-ring-container">
          <div class="score-ring">
            <svg viewBox="0 0 56 56">
              <circle class="score-ring-bg" cx="28" cy="28" r="23"></circle>
              <circle class="score-ring-progress" cx="28" cy="28" r="23"></circle>
            </svg>
            <div class="score-ring-content">
              <span class="score-value">${scoreDisplay}</span>
              <span class="score-grade">${scoreInfo.grade}</span>
            </div>
          </div>
          <span class="score-label">安全评分</span>
        </div>
        <div class="stats-cards">
          <div class="stat-card"><div class="stat-card-header"><div class="stat-card-icon total">∑</div><span class="stat-card-label">总数</span></div><div class="stat-card-value">${totalFindings}</div></div>
          <div class="stat-card"><div class="stat-card-header"><div class="stat-card-icon critical">!</div><span class="stat-card-label">严重</span></div><div class="stat-card-value critical">${criticalCount}</div></div>
          <div class="stat-card"><div class="stat-card-header"><div class="stat-card-icon high">▲</div><span class="stat-card-label">高危</span></div><div class="stat-card-value high">${highCount}</div></div>
          <div class="stat-card"><div class="stat-card-header"><div class="stat-card-icon verified">✓</div><span class="stat-card-label">验证</span></div><div class="stat-card-value" style="color:var(--success)">${verifiedCount}</div></div>
        </div>
      </div>
    </div>
  </section>
  <section class="severity-section">
    <div class="container">
      <div class="severity-bar-wrap">
        <span class="severity-bar-title">分布</span>
        <div class="severity-bar">
          ${
            totalFindings > 0
              ? `<div class="severity-segment critical" style="width:${(criticalCount / totalFindings) * 100}%"></div>
            <div class="severity-segment high" style="width:${(highCount / totalFindings) * 100}%"></div>
            <div class="severity-segment medium" style="width:${(mediumCount / totalFindings) * 100}%"></div>
            <div class="severity-segment low" style="width:${(lowCount / totalFindings) * 100}%"></div>`
              : ""
          }
        </div>
        <div class="severity-legend">
          <div class="severity-legend-item"><div class="severity-dot critical"></div>${criticalCount}</div>
          <div class="severity-legend-item"><div class="severity-dot high"></div>${highCount}</div>
          <div class="severity-legend-item"><div class="severity-dot medium"></div>${mediumCount}</div>
          <div class="severity-legend-item"><div class="severity-dot low"></div>${lowCount}</div>
        </div>
      </div>
    </div>
  </section>
  <main class="main-content">
    <div class="container"><div class="content-wrapper">${contentHtml}</div></div>
  </main>
  <footer class="report-footer">
    <div class="container"><div class="footer-content"><span>安全扫描报告</span><span>·</span><span>${generateDate}</span></div></div>
  </footer>
</body>
</html>`;
}
