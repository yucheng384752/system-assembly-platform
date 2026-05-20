export function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export function scheduleAfterDelay(ms: number, action: () => void): void {
  window.setTimeout(action, ms);
}
