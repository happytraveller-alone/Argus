const PROMPT_SKILL_ROWS = [
	{
		key: "recon",
		agentLabel: "Recon Agent",
		content:
			"优先快速建立项目画像：先识别入口、认证边界、外部输入面，再按风险优先级推进目录扫描。所有风险点必须基于真实代码证据，并尽量附带触发条件。",
	},
	{
		key: "business_logic_recon",
		agentLabel: "Business Logic Recon Agent",
		content:
			"优先枚举业务对象与敏感动作，重点关注对象所有权、状态跃迁、金额计算、权限边界。若项目缺少业务入口，应尽早给出终止依据。",
	},
	{
		key: "analysis",
		agentLabel: "Analysis Agent",
		content:
			"围绕单风险点做证据闭环：先定位代码，再追踪输入到敏感操作的数据流与控制流，结论必须可复核并明确漏洞成立条件。",
	},
	{
		key: "business_logic_analysis",
		agentLabel: "Business Logic Analysis Agent",
		content:
			"优先验证授权与状态机约束，必须检查全局补偿逻辑（中间件、依赖注入、service guard、repository filter），避免将已补偿场景误报为漏洞。",
	},
	{
		key: "verification",
		agentLabel: "Verification Agent",
		content:
			"验证阶段必须坚持可复现证据优先：先读取上下文，再最小化构造触发路径。无法稳定触发时，应明确记录阻断条件并谨慎降级结论。",
	},
] as const;

export default function PromptSkillsPanel() {
	return (
		<div className="flex flex-1 min-h-[20rem] flex-col">
			<div className="overflow-x-auto rounded-sm border border-border/50 bg-background/20">
				<table className="min-w-[920px] w-full border-collapse">
					<thead>
						<tr className="border-b border-border/50 bg-background/60 text-left">
							<th className="px-4 py-3 text-xs font-mono uppercase tracking-[0.24em] text-muted-foreground">
								序号
							</th>
							<th className="px-4 py-3 text-xs font-mono uppercase tracking-[0.24em] text-muted-foreground">
								Agent 角色
							</th>
							<th className="px-4 py-3 text-xs font-mono uppercase tracking-[0.24em] text-muted-foreground">
								Skill Key
							</th>
							<th className="px-4 py-3 text-xs font-mono uppercase tracking-[0.24em] text-muted-foreground">
								Prompt Skill
							</th>
						</tr>
					</thead>
					<tbody>
						{PROMPT_SKILL_ROWS.map((row, index) => (
							<tr
								key={row.key}
								className="border-b border-border/30 align-top transition-colors duration-150 hover:bg-background/40"
							>
								<td className="px-4 py-4 text-sm font-mono text-muted-foreground">
									{String(index + 1).padStart(2, "0")}
								</td>
								<td className="px-4 py-4 text-sm font-semibold text-foreground whitespace-nowrap">
									{row.agentLabel}
								</td>
								<td className="px-4 py-4 text-sm font-mono text-primary whitespace-nowrap">
									{row.key}
								</td>
								<td className="px-4 py-4 text-sm leading-6 text-foreground/90">
									{row.content}
								</td>
							</tr>
						))}
					</tbody>
				</table>
			</div>
		</div>
	);
}
