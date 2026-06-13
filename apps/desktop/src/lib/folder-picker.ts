import { open } from "@tauri-apps/plugin-dialog";

export async function pickWatchFolder(): Promise<string | null> {
  const selected = await open({
    directory: true,
    multiple: false,
    title: "Select folder to watch",
  });

  if (selected === null) {
    return null;
  }

  return typeof selected === "string" ? selected : selected[0] ?? null;
}
