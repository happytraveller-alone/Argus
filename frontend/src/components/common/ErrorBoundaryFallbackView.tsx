import React from 'react';
import { Button } from '@/components/ui/button';
import { cn } from '@/shared/utils/utils';
import {
  AlertTriangle,
  Home,
  RefreshCcw,
  RefreshCw,
  Server,
  TerminalSquare,
  WifiOff,
} from 'lucide-react';
import {
  type ErrorBoundaryAction,
  type ErrorBoundaryActionKey,
  type ErrorBoundaryViewModel,
  type ErrorBoundaryVariant,
} from './errorBoundaryState';

export interface ErrorBoundaryFallbackViewProps {
  state: ErrorBoundaryViewModel;
  error: Error | null;
  errorInfo: React.ErrorInfo | null;
  onReset: () => void;
  onGoHome: () => void;
  onReload: () => void;
  isDev?: boolean;
}

type VariantVisuals = {
  icon: typeof AlertTriangle;
  badgeClassName: string;
  iconClassName: string;
  iconWrapClassName: string;
  panelBorderClassName: string;
  panelGlow: string;
  actionClassName: string;
};

const VARIANT_VISUALS: Record<ErrorBoundaryVariant, VariantVisuals> = {
  generic: {
    icon: AlertTriangle,
    badgeClassName:
      'border-rose-400/30 bg-rose-500/10 text-rose-100',
    iconClassName: 'text-rose-300',
    iconWrapClassName:
      'border-rose-400/30 bg-gradient-to-br from-rose-500/22 via-rose-500/12 to-orange-500/12',
    panelBorderClassName: 'border-rose-400/24',
    panelGlow: 'radial-gradient(circle, rgba(244,63,94,0.16) 0%, rgba(15,23,42,0) 72%)',
    actionClassName:
      'border-rose-400/25 bg-rose-500/10 text-rose-50 hover:border-rose-300/40 hover:bg-rose-500/16',
  },
  'backend-offline': {
    icon: Server,
    badgeClassName:
      'border-sky-400/30 bg-sky-500/10 text-sky-100',
    iconClassName: 'text-sky-200',
    iconWrapClassName:
      'border-sky-400/30 bg-gradient-to-br from-sky-500/22 via-cyan-500/14 to-blue-500/12',
    panelBorderClassName: 'border-sky-400/24',
    panelGlow: 'radial-gradient(circle, rgba(14,165,233,0.18) 0%, rgba(15,23,42,0) 72%)',
    actionClassName:
      'border-sky-400/25 bg-sky-500/10 text-sky-50 hover:border-sky-300/40 hover:bg-sky-500/16',
  },
};

export function ErrorBoundaryFallbackView({
  state,
  error,
  errorInfo,
  onReset,
  onGoHome,
  onReload,
  isDev = false,
}: ErrorBoundaryFallbackViewProps) {
  const visuals = VARIANT_VISUALS[state.variant];
  const StatusIcon = visuals.icon;

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden gradient-bg px-4 py-8 sm:px-6">
      <div className="absolute inset-0 cyber-grid-subtle opacity-90" />
      <div
        className="absolute left-1/2 top-16 h-72 w-72 -translate-x-1/2 rounded-full blur-3xl"
        style={{ background: visuals.panelGlow }}
      />
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_top,rgba(255,255,255,0.05),transparent_42%),linear-gradient(180deg,rgba(15,23,42,0.14),rgba(2,6,23,0.66))]" />

      <div className="relative z-10 w-full max-w-6xl">
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1.45fr)_minmax(320px,0.85fr)]">
          <section className={cn('terminal-window', visuals.panelBorderClassName)}>
            <div className="terminal-header">
              <div className="terminal-dots">
                <span className="terminal-dot terminal-dot-red" />
                <span className="terminal-dot terminal-dot-yellow" />
                <span className="terminal-dot terminal-dot-green" />
              </div>
              <span className="terminal-title">{state.statusCode}</span>
              <span
                className={cn(
                  'ml-auto rounded-sm border px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.28em]',
                  visuals.badgeClassName
                )}
              >
                {state.badgeLabel}
              </span>
            </div>

            <div className="terminal-content space-y-6 p-6 sm:p-8">
              <div className="flex flex-col gap-5 sm:flex-row sm:items-start">
                <div
                  className={cn(
                    'flex h-20 w-20 shrink-0 items-center justify-center rounded-sm border shadow-[0_0_32px_rgba(15,23,42,0.38)]',
                    visuals.iconWrapClassName
                  )}
                >
                  <StatusIcon className={cn('h-10 w-10', visuals.iconClassName)} />
                </div>

                <div className="space-y-3">
                  <p className="text-xs uppercase tracking-[0.4em] text-slate-400">
                    System Status
                  </p>
                  <h2 className="text-3xl font-black text-white sm:text-4xl">
                    {state.title}
                  </h2>
                  <p className="max-w-2xl text-base leading-7 text-slate-200 sm:text-lg">
                    {state.description}
                  </p>
                </div>
              </div>

              <div className="grid gap-4 md:grid-cols-2">
                <div
                  className={cn(
                    'rounded-sm border bg-black/35 p-4',
                    visuals.panelBorderClassName
                  )}
                >
                  <p className="text-xs uppercase tracking-[0.28em] text-slate-400">
                    状态摘要
                  </p>
                  <p className="mt-3 text-sm leading-7 text-slate-200">
                    {state.summary}
                  </p>
                </div>
                <div
                  className={cn(
                    'rounded-sm border bg-black/35 p-4',
                    visuals.panelBorderClassName
                  )}
                >
                  <p className="text-xs uppercase tracking-[0.28em] text-slate-400">
                    建议操作
                  </p>
                  <p className="mt-3 text-sm leading-7 text-slate-200">
                    {state.guidance}
                  </p>
                </div>
              </div>

              {error && (
                <div
                  className={cn(
                    'overflow-hidden rounded-sm border bg-black/45',
                    visuals.panelBorderClassName
                  )}
                >
                  <div className="flex items-center justify-between border-b border-white/10 px-4 py-3">
                    <div className="flex items-center gap-2 text-sm font-semibold text-slate-100">
                      <WifiOff className="h-4 w-4" />
                      <span>诊断信号</span>
                    </div>
                    <span className="text-xs uppercase tracking-[0.28em] text-slate-400">
                      {state.statusCode}
                    </span>
                  </div>
                  <div className="p-4">
                    <p className="break-all font-mono text-sm leading-6 text-amber-100">
                      {error.message}
                    </p>
                  </div>
                </div>
              )}

              {isDev && error?.stack && (
                <details className="rounded-sm border border-white/10 bg-black/35 p-4 text-xs text-slate-200">
                  <summary className="cursor-pointer font-semibold text-slate-100">
                    查看错误堆栈
                  </summary>
                  <pre className="mt-3 overflow-auto whitespace-pre-wrap break-words rounded-sm border border-white/10 bg-black/45 p-3 font-mono text-xs text-slate-200">
                    {error.stack}
                  </pre>
                </details>
              )}

              {isDev && errorInfo?.componentStack && (
                <details className="rounded-sm border border-white/10 bg-black/35 p-4 text-xs text-slate-200">
                  <summary className="cursor-pointer font-semibold text-slate-100">
                    查看组件堆栈
                  </summary>
                  <pre className="mt-3 overflow-auto whitespace-pre-wrap break-words rounded-sm border border-white/10 bg-black/45 p-3 font-mono text-xs text-slate-200">
                    {errorInfo.componentStack}
                  </pre>
                </details>
              )}
            </div>
          </section>

          <aside className={cn('cyber-card p-0', visuals.panelBorderClassName)}>
            <div className="cyber-card-header justify-between border-b border-white/10">
              <div className="flex items-center gap-3">
                <TerminalSquare className="h-4 w-4 text-slate-100" />
                <span className="text-sm font-bold uppercase tracking-[0.28em] text-slate-100">
                  Recovery Console
                </span>
              </div>
              <span className="rounded-sm border border-white/10 px-2 py-1 text-[11px] uppercase tracking-[0.24em] text-slate-400">
                READY
              </span>
            </div>

            <div className="space-y-6 p-6">
              <div
                className={cn(
                  'rounded-sm border bg-black/35 p-4',
                  visuals.panelBorderClassName
                )}
              >
                <p className="text-xs uppercase tracking-[0.28em] text-slate-400">
                  当前模式
                </p>
                <p className="mt-3 text-lg font-semibold text-white">
                  {state.badgeLabel}
                </p>
                <p className="mt-2 text-sm leading-7 text-slate-300">
                  {state.footer}
                </p>
              </div>

              <div className="space-y-3">
                {state.actions.map((action) => (
                  <ErrorBoundaryActionButton
                    key={action.key}
                    action={action}
                    onReset={onReset}
                    onGoHome={onGoHome}
                    onReload={onReload}
                    emphasisClassName={visuals.actionClassName}
                  />
                ))}
              </div>

              <div className="rounded-sm border border-dashed border-white/10 bg-black/25 p-4">
                <p className="text-xs uppercase tracking-[0.28em] text-slate-400">
                  提示
                </p>
                <p className="mt-3 text-sm leading-7 text-slate-300">
                  如果你正在本地开发，请优先确认后端服务是否已经监听
                  <span className="mx-1 font-mono text-slate-100">8000</span>
                  端口，然后再重试当前页面。
                </p>
              </div>
            </div>
          </aside>
        </div>
      </div>
    </div>
  );
}

function ErrorBoundaryActionButton({
  action,
  onReset,
  onGoHome,
  onReload,
  emphasisClassName,
}: {
  action: ErrorBoundaryAction;
  onReset: () => void;
  onGoHome: () => void;
  onReload: () => void;
  emphasisClassName: string;
}) {
  const Icon = getActionIcon(action.key);
  const actionHandler = getActionHandler(action.key, {
    onReset,
    onGoHome,
    onReload,
  });

  return (
    <Button
      type="button"
      onClick={actionHandler}
      variant={action.variant}
      className={cn(
        'min-h-12 w-full justify-start gap-3 px-4 py-3 text-left text-sm',
        action.variant === 'default'
          ? emphasisClassName
          : 'border-white/10 bg-white/[0.03] text-slate-100 hover:border-white/20 hover:bg-white/[0.06]'
      )}
    >
      <Icon className="h-4 w-4" />
      <span>{action.label}</span>
    </Button>
  );
}

function getActionIcon(actionKey: ErrorBoundaryActionKey) {
  switch (actionKey) {
    case 'reset':
      return RefreshCcw;
    case 'home':
      return Home;
    case 'reload':
      return RefreshCw;
    default:
      return RefreshCw;
  }
}

function getActionHandler(
  actionKey: ErrorBoundaryActionKey,
  handlers: {
    onReset: () => void;
    onGoHome: () => void;
    onReload: () => void;
  }
) {
  switch (actionKey) {
    case 'reset':
      return handlers.onReset;
    case 'home':
      return handlers.onGoHome;
    case 'reload':
      return handlers.onReload;
    default:
      return handlers.onReload;
  }
}
