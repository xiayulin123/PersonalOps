import { isTauri } from "@tauri-apps/api/core";

import { isCloudEdition } from "@/lib/edition";

export function runningInTauri(): boolean {
  return isTauri();
}

export function runningInWeb(): boolean {
  return !isTauri();
}

/** Folder watch and native pickers — desktop Tauri only, not cloud web. */
export function supportsFolderWatch(): boolean {
  return isDesktopEdition() && isTauri();
}

function isDesktopEdition(): boolean {
  return !isCloudEdition();
}

export async function openExternalUrl(url: string): Promise<void> {
  if (isTauri()) {
    const { openUrl } = await import("@tauri-apps/plugin-opener");
    await openUrl(url);
    return;
  }
  window.open(url, "_blank", "noopener,noreferrer");
}

export async function confirmDestructive(
  message: string,
  title = "Confirm"
): Promise<boolean> {
  if (isTauri()) {
    const { confirm } = await import("@tauri-apps/plugin-dialog");
    return confirm(message, { title, kind: "warning" });
  }
  return window.confirm(message);
}
