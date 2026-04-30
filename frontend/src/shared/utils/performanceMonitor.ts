
import { logger } from './logger';

class PerformanceMonitor {
  private marks = new Map<string, number>();

  start(label: string) {
    this.marks.set(label, performance.now());
  }

  end(label: string, logToConsole = false) {
    const startTime = this.marks.get(label);
    if (!startTime) {
      console.warn(`Performance mark "${label}" not found`);
      return 0;
    }

    const duration = performance.now() - startTime;
    this.marks.delete(label);

    logger.logPerformance(label, Math.round(duration));

    if (logToConsole) {
      console.log(`⏱️ ${label}: ${duration.toFixed(2)}ms`);
    }

    return duration;
  }

  async measure<T>(label: string, fn: () => T | Promise<T>): Promise<T> {
    this.start(label);
    try {
      const result = await fn();
      this.end(label);
      return result;
    } catch (error) {
      this.end(label);
      throw error;
    }
  }

  monitorPagePerformance() {
    return;
  }

  monitorResourceLoading() {
    return;
  }

  monitorMemory() {
    return;
  }

  monitorLongTasks() {
    return;
  }

  initAll() {
    this.monitorPagePerformance();
    this.monitorResourceLoading();
    this.monitorMemory();
    this.monitorLongTasks();
  }
}

export const performanceMonitor = new PerformanceMonitor();
