import { Shield, Sparkles } from "lucide-react";

export default function Home() {
    return (
        <div className="min-h-screen bg-background text-foreground relative overflow-hidden">
            <div className="absolute inset-0 bg-gradient-to-br from-primary/5 via-transparent to-primary/10 pointer-events-none" />
            <div className="relative z-10 flex flex-col items-center justify-center px-6 py-20 text-center">
                <div className="flex items-center gap-3 text-primary mb-4">
                    <Sparkles className="w-6 h-6" />
                    <span className="text-sm font-mono tracking-[0.4em] uppercase">
                        DeepAudit
                    </span>
                </div>
                <h1 className="text-4xl sm:text-5xl md:text-6xl font-bold tracking-tight mb-4">
                    智能代码安全审计平台
                </h1>
                <p className="max-w-2xl text-muted-foreground text-base sm:text-lg leading-relaxed">
                    聚焦安全审计全流程，从项目管理、规则配置到任务执行与报告导出，帮助团队快速发现漏洞并提升代码质量。
                </p>

                <div className="mt-10 grid gap-6 sm:grid-cols-2 max-w-3xl w-full">
                    <div className="rounded-xl border border-border bg-card/70 p-6 text-left shadow-sm">
                        <div className="flex items-center gap-2 text-primary font-semibold mb-3">
                            <Shield className="w-5 h-5" />
                            <span>工具名称</span>
                        </div>
                        <p className="text-sm text-muted-foreground font-mono">
                            DeepAudit 智能审计平台
                        </p>
                    </div>
                    <div className="rounded-xl border border-border bg-card/70 p-6 text-left shadow-sm">
                        <div className="flex items-center gap-2 text-primary font-semibold mb-3">
                            <Shield className="w-5 h-5" />
                            <span>工具用处</span>
                        </div>
                        <ul className="text-sm text-muted-foreground space-y-2 list-disc list-inside">
                            <li>统一管理代码库与审计任务进度</li>
                            <li>配置安全规则与提示词模板，提升检测覆盖</li>
                            <li>输出可追溯的审计报告与修复建议</li>
                        </ul>
                    </div>
                </div>
            </div>
        </div>
    );
}
