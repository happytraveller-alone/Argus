import { useState } from "react";
import { toast } from "sonner";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import EventLog from "./components/EventLog";
import QueueStatusPanel from "./components/QueueStatusPanel";
import ResultPanel from "./components/ResultPanel";
import RunBar from "./components/RunBar";
import { useAgentTestStream } from "./useAgentTestStream";

export function ReconPanel() {
  const { events, running, result, queueSnapshot, run, stop, clear } =
    useAgentTestStream();
  const [projectPath, setProjectPath] = useState("");
  const [projectName, setProjectName] = useState("test-project");
  const [frameworkHint, setFrameworkHint] = useState("");
  const [maxIter, setMaxIter] = useState("6");

  const handleRun = () => {
    if (!projectPath.trim()) {
      toast.error("请填写项目路径");
      return;
    }
    run("recon", {
      project_path: projectPath.trim(),
      project_name: projectName.trim() || "test-project",
      framework_hint: frameworkHint.trim() || null,
      max_iterations: parseInt(maxIter, 10) || 6,
    });
  };

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div className="space-y-1.5">
          <label className="text-xs text-muted-foreground">项目绝对路径 *</label>
          <Input
            placeholder="/path/to/your/project"
            value={projectPath}
            onChange={(e) => setProjectPath(e.target.value)}
            disabled={running}
            className="font-mono text-sm"
          />
        </div>
        <div className="space-y-1.5">
          <label className="text-xs text-muted-foreground">项目名称</label>
          <Input
            placeholder="my-webapp"
            value={projectName}
            onChange={(e) => setProjectName(e.target.value)}
            disabled={running}
          />
        </div>
        <div className="space-y-1.5">
          <label className="text-xs text-muted-foreground">框架提示（可选）</label>
          <Input
            placeholder="django / fastapi / express / spring"
            value={frameworkHint}
            onChange={(e) => setFrameworkHint(e.target.value)}
            disabled={running}
          />
        </div>
        <div className="space-y-1.5">
          <label className="text-xs text-muted-foreground">最大迭代次数</label>
          <Input
            type="number"
            min={1}
            max={20}
            value={maxIter}
            onChange={(e) => setMaxIter(e.target.value)}
            disabled={running}
            className="w-24"
          />
        </div>
      </div>
      <RunBar
        running={running}
        eventCount={events.length}
        onRun={handleRun}
        onStop={stop}
        onClear={clear}
      />
      <QueueStatusPanel snapshot={queueSnapshot} />
      <EventLog events={events} running={running} />
      <ResultPanel result={result} />
    </div>
  );
}

export function AnalysisPanel() {
  const { events, running, result, queueSnapshot, run, stop, clear } =
    useAgentTestStream();
  const [projectPath, setProjectPath] = useState("");
  const [projectName, setProjectName] = useState("test-project");
  const [highRiskAreas, setHighRiskAreas] = useState("");
  const [entryPoints, setEntryPoints] = useState("");
  const [taskDesc, setTaskDesc] = useState("");
  const [maxIter, setMaxIter] = useState("8");

  const handleRun = () => {
    if (!projectPath.trim()) {
      toast.error("请填写项目路径");
      return;
    }
    run("analysis", {
      project_path: projectPath.trim(),
      project_name: projectName.trim() || "test-project",
      high_risk_areas: highRiskAreas
        .split("\n")
        .map((s) => s.trim())
        .filter(Boolean),
      entry_points: entryPoints
        .split("\n")
        .map((s) => s.trim())
        .filter(Boolean),
      task_description: taskDesc.trim(),
      max_iterations: parseInt(maxIter, 10) || 8,
    });
  };

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div className="space-y-1.5">
          <label className="text-xs text-muted-foreground">项目绝对路径 *</label>
          <Input
            placeholder="/path/to/your/project"
            value={projectPath}
            onChange={(e) => setProjectPath(e.target.value)}
            disabled={running}
            className="font-mono text-sm"
          />
        </div>
        <div className="space-y-1.5">
          <label className="text-xs text-muted-foreground">项目名称</label>
          <Input
            placeholder="my-webapp"
            value={projectName}
            onChange={(e) => setProjectName(e.target.value)}
            disabled={running}
          />
        </div>
        <div className="space-y-1.5 sm:col-span-2">
          <label className="text-xs text-muted-foreground">审计任务描述（可选）</label>
          <Input
            placeholder="重点检查用户认证和权限控制逻辑"
            value={taskDesc}
            onChange={(e) => setTaskDesc(e.target.value)}
            disabled={running}
          />
        </div>
        <div className="space-y-1.5">
          <label className="text-xs text-muted-foreground">高风险区域（每行一个）</label>
          <Textarea
            placeholder={"app/api/user.py\napp/api/payment.py"}
            value={highRiskAreas}
            onChange={(e) => setHighRiskAreas(e.target.value)}
            disabled={running}
            rows={4}
            className="font-mono text-xs resize-none"
          />
        </div>
        <div className="space-y-1.5">
          <label className="text-xs text-muted-foreground">入口点（每行一个）</label>
          <Textarea
            placeholder={"GET /api/users/{id}\nPOST /api/orders"}
            value={entryPoints}
            onChange={(e) => setEntryPoints(e.target.value)}
            disabled={running}
            rows={4}
            className="font-mono text-xs resize-none"
          />
        </div>
        <div className="space-y-1.5">
          <label className="text-xs text-muted-foreground">最大迭代次数</label>
          <Input
            type="number"
            min={1}
            max={20}
            value={maxIter}
            onChange={(e) => setMaxIter(e.target.value)}
            disabled={running}
            className="w-24"
          />
        </div>
      </div>
      <RunBar
        running={running}
        eventCount={events.length}
        onRun={handleRun}
        onStop={stop}
        onClear={clear}
      />
      <QueueStatusPanel snapshot={queueSnapshot} />
      <EventLog events={events} running={running} />
      <ResultPanel result={result} />
    </div>
  );
}

const FINDING_PLACEHOLDER = JSON.stringify(
  [
    {
      title: "SQL 注入漏洞",
      vulnerability_type: "sql_injection",
      severity: "high",
      file_path: "app/api/user.py",
      function_name: "get_user",
      line_start: 42,
      description: "用户输入直接拼接到 SQL 查询中",
      code_snippet: 'query = f"SELECT * FROM users WHERE id={user_id}"',
    },
  ],
  null,
  2,
);

export function VerificationPanel() {
  const { events, running, result, run, stop, clear } = useAgentTestStream();
  const [projectPath, setProjectPath] = useState("");
  const [findingsJson, setFindingsJson] = useState(FINDING_PLACEHOLDER);
  const [maxIter, setMaxIter] = useState("6");

  const handleRun = () => {
    if (!projectPath.trim()) {
      toast.error("请填写项目路径");
      return;
    }
    let findings: unknown;
    try {
      findings = JSON.parse(findingsJson);
      if (!Array.isArray(findings)) {
        toast.error("漏洞列表必须是 JSON 数组");
        return;
      }
    } catch {
      toast.error("漏洞列表 JSON 格式错误");
      return;
    }
    run("verification", {
      project_path: projectPath.trim(),
      findings,
      max_iterations: parseInt(maxIter, 10) || 6,
    });
  };

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div className="space-y-1.5">
          <label className="text-xs text-muted-foreground">项目绝对路径 *</label>
          <Input
            placeholder="/path/to/your/project"
            value={projectPath}
            onChange={(e) => setProjectPath(e.target.value)}
            disabled={running}
            className="font-mono text-sm"
          />
        </div>
        <div className="space-y-1.5">
          <label className="text-xs text-muted-foreground">最大迭代次数</label>
          <Input
            type="number"
            min={1}
            max={20}
            value={maxIter}
            onChange={(e) => setMaxIter(e.target.value)}
            disabled={running}
            className="w-24"
          />
        </div>
        <div className="space-y-1.5 sm:col-span-2">
          <label className="text-xs text-muted-foreground">
            待验证漏洞列表（JSON 数组）
          </label>
          <Textarea
            value={findingsJson}
            onChange={(e) => setFindingsJson(e.target.value)}
            disabled={running}
            rows={12}
            className="font-mono text-xs resize-none"
          />
        </div>
      </div>
      <RunBar
        running={running}
        eventCount={events.length}
        onRun={handleRun}
        onStop={stop}
        onClear={clear}
      />
      <EventLog events={events} running={running} />
      <ResultPanel result={result} />
    </div>
  );
}

export function BusinessLogicPanel() {
  const { events, running, result, run, stop, clear } = useAgentTestStream();
  const [projectPath, setProjectPath] = useState("");
  const [entryPoints, setEntryPoints] = useState("");
  const [frameworkHint, setFrameworkHint] = useState("");
  const [maxIter, setMaxIter] = useState("8");
  const [quickMode, setQuickMode] = useState(false);

  const handleRun = () => {
    if (!projectPath.trim()) {
      toast.error("请填写项目路径");
      return;
    }
    run("business-logic", {
      project_path: projectPath.trim(),
      entry_points_hint: entryPoints
        .split("\n")
        .map((s) => s.trim())
        .filter(Boolean),
      framework_hint: frameworkHint.trim() || null,
      max_iterations: parseInt(maxIter, 10) || 8,
      quick_mode: quickMode,
    });
  };

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div className="space-y-1.5">
          <label className="text-xs text-muted-foreground">项目绝对路径 *</label>
          <Input
            placeholder="/path/to/your/project"
            value={projectPath}
            onChange={(e) => setProjectPath(e.target.value)}
            disabled={running}
            className="font-mono text-sm"
          />
        </div>
        <div className="space-y-1.5">
          <label className="text-xs text-muted-foreground">框架提示（可选）</label>
          <Input
            placeholder="flask / fastapi / django / express / spring"
            value={frameworkHint}
            onChange={(e) => setFrameworkHint(e.target.value)}
            disabled={running}
          />
        </div>
        <div className="space-y-1.5 sm:col-span-2">
          <label className="text-xs text-muted-foreground">
            入口点列表（每行一个，格式：
            <code className="text-cyan-400">文件路径:函数名</code>）
          </label>
          <Textarea
            placeholder={
              "app/api/user.py:update_profile\napp/api/order.py:create_order\napp/api/admin.py:reset_password"
            }
            value={entryPoints}
            onChange={(e) => setEntryPoints(e.target.value)}
            disabled={running}
            rows={5}
            className="font-mono text-xs resize-none"
          />
          <p className="text-xs text-muted-foreground/60">
            留空则启用全局模式（自动发现所有 HTTP 入口点）
          </p>
        </div>
        <div className="flex items-center gap-4">
          <div className="space-y-1.5">
            <label className="text-xs text-muted-foreground">最大迭代次数</label>
            <Input
              type="number"
              min={1}
              max={20}
              value={maxIter}
              onChange={(e) => setMaxIter(e.target.value)}
              disabled={running}
              className="w-24"
            />
          </div>
          <label className="flex items-center gap-2 cursor-pointer mt-5">
            <input
              type="checkbox"
              checked={quickMode}
              onChange={(e) => setQuickMode(e.target.checked)}
              disabled={running}
              className="accent-cyan-400"
            />
            <span className="text-xs text-muted-foreground">快速模式</span>
          </label>
        </div>
      </div>
      <RunBar
        running={running}
        eventCount={events.length}
        onRun={handleRun}
        onStop={stop}
        onClear={clear}
      />
      <EventLog events={events} running={running} />
      <ResultPanel result={result} />
    </div>
  );
}

const BL_RISK_POINT_PLACEHOLDER = JSON.stringify(
  {
    file_path: "app/api/order.py",
    line_start: 85,
    vulnerability_type: "idor",
    severity: "high",
    description: "订单更新接口仅验证登录状态，未校验当前用户是否为订单所有者",
    confidence: 0.85,
  },
  null,
  2,
);

export function BusinessLogicReconPanel() {
  const { events, running, result, queueSnapshot, run, stop, clear } =
    useAgentTestStream();
  const [projectPath, setProjectPath] = useState("");
  const [projectName, setProjectName] = useState("test-project");
  const [frameworkHint, setFrameworkHint] = useState("");
  const [maxIter, setMaxIter] = useState("10");

  const handleRun = () => {
    if (!projectPath.trim()) {
      toast.error("请填写项目路径");
      return;
    }
    run("business-logic-recon", {
      project_path: projectPath.trim(),
      project_name: projectName.trim() || "test-project",
      framework_hint: frameworkHint.trim() || null,
      max_iterations: parseInt(maxIter, 10) || 10,
    });
  };

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div className="space-y-1.5">
          <label className="text-xs text-muted-foreground">项目绝对路径 *</label>
          <Input
            placeholder="/path/to/your/project"
            value={projectPath}
            onChange={(e) => setProjectPath(e.target.value)}
            disabled={running}
            className="font-mono text-sm"
          />
        </div>
        <div className="space-y-1.5">
          <label className="text-xs text-muted-foreground">项目名称</label>
          <Input
            placeholder="my-webapp"
            value={projectName}
            onChange={(e) => setProjectName(e.target.value)}
            disabled={running}
          />
        </div>
        <div className="space-y-1.5">
          <label className="text-xs text-muted-foreground">框架提示（可选）</label>
          <Input
            placeholder="django / fastapi / express / spring"
            value={frameworkHint}
            onChange={(e) => setFrameworkHint(e.target.value)}
            disabled={running}
          />
        </div>
        <div className="space-y-1.5">
          <label className="text-xs text-muted-foreground">最大迭代次数</label>
          <Input
            type="number"
            min={1}
            max={30}
            value={maxIter}
            onChange={(e) => setMaxIter(e.target.value)}
            disabled={running}
            className="w-24"
          />
        </div>
      </div>
      <RunBar
        running={running}
        eventCount={events.length}
        onRun={handleRun}
        onStop={stop}
        onClear={clear}
      />
      <QueueStatusPanel snapshot={queueSnapshot} />
      <EventLog events={events} running={running} />
      <ResultPanel result={result} />
    </div>
  );
}

export function BusinessLogicAnalysisPanel() {
  const { events, running, result, queueSnapshot, run, stop, clear } =
    useAgentTestStream();
  const [projectPath, setProjectPath] = useState("");
  const [riskPointJson, setRiskPointJson] = useState(BL_RISK_POINT_PLACEHOLDER);
  const [maxIter, setMaxIter] = useState("10");

  const handleRun = () => {
    if (!projectPath.trim()) {
      toast.error("请填写项目路径");
      return;
    }
    let riskPoint: unknown;
    try {
      riskPoint = JSON.parse(riskPointJson);
      if (typeof riskPoint !== "object" || Array.isArray(riskPoint) || !riskPoint) {
        toast.error("风险点必须是 JSON 对象");
        return;
      }
    } catch {
      toast.error("风险点 JSON 格式错误");
      return;
    }
    run("business-logic-analysis", {
      project_path: projectPath.trim(),
      risk_point: riskPoint,
      max_iterations: parseInt(maxIter, 10) || 10,
    });
  };

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div className="space-y-1.5">
          <label className="text-xs text-muted-foreground">项目绝对路径 *</label>
          <Input
            placeholder="/path/to/your/project"
            value={projectPath}
            onChange={(e) => setProjectPath(e.target.value)}
            disabled={running}
            className="font-mono text-sm"
          />
        </div>
        <div className="space-y-1.5">
          <label className="text-xs text-muted-foreground">最大迭代次数</label>
          <Input
            type="number"
            min={1}
            max={30}
            value={maxIter}
            onChange={(e) => setMaxIter(e.target.value)}
            disabled={running}
            className="w-24"
          />
        </div>
        <div className="space-y-1.5 sm:col-span-2">
          <label className="text-xs text-muted-foreground">
            业务逻辑风险点（JSON 对象，来自 BL Recon 阶段输出）
          </label>
          <Textarea
            value={riskPointJson}
            onChange={(e) => setRiskPointJson(e.target.value)}
            disabled={running}
            rows={10}
            className="font-mono text-xs resize-none"
          />
          <p className="text-xs text-muted-foreground/60">
            必填字段：<code className="text-cyan-400">file_path</code>、
            <code className="text-cyan-400">line_start</code>、
            <code className="text-cyan-400">description</code>、
            <code className="text-cyan-400">vulnerability_type</code>
          </p>
        </div>
      </div>
      <RunBar
        running={running}
        eventCount={events.length}
        onRun={handleRun}
        onStop={stop}
        onClear={clear}
      />
      <QueueStatusPanel snapshot={queueSnapshot} />
      <EventLog events={events} running={running} />
      <ResultPanel result={result} />
    </div>
  );
}
