/** Cloud (Plan B) vs desktop (Tauri) edition — build-time flag. */

export type AppEdition = "desktop" | "cloud";

export function getAppEdition(): AppEdition {
  const raw = import.meta.env.VITE_EDITION?.trim().toLowerCase();
  return raw === "cloud" ? "cloud" : "desktop";
}

export function isCloudEdition(): boolean {
  return getAppEdition() === "cloud";
}

export function isDesktopEdition(): boolean {
  return !isCloudEdition();
}

/** Chat engines offered in the UI for this build. */
export function availableChatModes(): Array<"langgraph" | "cursor_agent"> {
  return isCloudEdition() ? ["langgraph"] : ["langgraph", "cursor_agent"];
}

/** Always show both engines in Tools UI; cloud disables Cursor Agent. */
export const UI_CHAT_ENGINE_MODES: Array<"langgraph" | "cursor_agent"> = [
  "langgraph",
  "cursor_agent",
];

export function isCursorAgentUiDisabled(): boolean {
  return isCloudEdition();
}

export const CURSOR_AGENT_DESKTOP_TOOLTIP =
  "Designing - available in desktop edition (Tauri).";

export const CURSOR_AGENT_DESKTOP_DESCRIPTION =
  "Designing - available in the desktop (Tauri) app.";

/** Life Gmail/Outlook connect is disabled in cloud web (OAuth verification burden). */
export function isLifeEmailConnectUiDisabled(): boolean {
  return isCloudEdition();
}

export const LIFE_EMAIL_CONNECT_CLOUD_TOOLTIP =
  "Unavailable in cloud web - use desktop edition (Tauri).";

export const LIFE_EMAIL_CONNECT_CLOUD_NOTE =
  "Gmail and Outlook connect reads your mail and calendar. Google and Microsoft require OAuth app verification, test users, and restricted-scope approval. This is enabled in the desktop (Tauri) app only for now.";
