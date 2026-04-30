import SilentLoadingState from "@/components/performance/SilentLoadingState";

export function DataTableLoadingState({
  label: _label = "加载中...",
}: {
  label?: string;
}) {
  return <SilentLoadingState className="min-h-32 py-10" />;
}
