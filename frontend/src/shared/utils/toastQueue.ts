import { toast } from "sonner";

type ToastLevel = "success" | "error" | "info" | "warning";

interface ToastQueueItem {
  level: ToastLevel;
  message: string;
  description?: string;
}

const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

export async function showToastQueue(
  items: ToastQueueItem[],
  options?: { durationMs?: number; gapMs?: number }
): Promise<void> {
  const durationMs = options?.durationMs ?? 2400;
  const gapMs = options?.gapMs ?? 350;

  for (const item of items) {
    const payload = {
      description: item.description,
      duration: durationMs,
    };
    switch (item.level) {
      case "success":
        toast.success(item.message, payload);
        break;
      case "error":
        toast.error(item.message, payload);
        break;
      case "warning":
        toast.warning(item.message, payload);
        break;
      default:
        toast.info(item.message, payload);
        break;
    }
    await wait(durationMs + gapMs);
  }
}
