import { DragEvent, useCallback, useEffect, useRef, useState } from "react";
import { Eye, FileText, FolderOpen, Loader2, ScanText, Trash2, Upload } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  checkHealth,
  deleteFile,
  deleteWatchFolder,
  getWatchFolder,
  listFiles,
  runFileOcr,
  saveWatchFolder,
  uploadFile,
  type FileRecord,
  type WatchFolder,
} from "@/lib/api";
import { pickWatchFolder } from "@/lib/folder-picker";
import { supportsFolderWatch } from "@/lib/platform";
import { cn } from "@/lib/utils";

type FilesTabProps = {
  workspaceId: string;
};

const STATUS_LABELS: Record<string, string> = {
  pending: "Pending",
  indexing: "Indexing",
  ocr: "Running OCR",
  ready: "Ready",
  failed: "Failed",
  empty: "Empty",
  needs_ocr: "Needs OCR",
};

const STATUS_STYLES: Record<string, string> = {
  pending: "border-amber-500/30 bg-amber-500/10 text-amber-800 dark:text-amber-300",
  indexing: "border-blue-500/30 bg-blue-500/10 text-blue-800 dark:text-blue-300",
  ocr: "border-violet-500/35 bg-violet-500/10 text-violet-800 dark:text-violet-300",
  ready: "border-emerald-500/30 bg-emerald-500/10 text-emerald-800 dark:text-emerald-300",
  failed: "border-destructive/30 bg-destructive/10 text-destructive",
  empty: "border-foreground/20 bg-muted text-muted-foreground",
  needs_ocr: "border-amber-500/35 bg-amber-500/15 text-amber-900 dark:text-amber-200",
};

function fileDetailText(file: FileRecord): string {
  if (file.chunk_count > 0) {
    return `${file.chunk_count} chunks indexed`;
  }

  switch (file.status) {
    case "needs_ocr":
      return "No text extracted — use Run OCR (local Tesseract or Azure Vision)";
    case "empty":
      return "No searchable text in this file";
    case "failed":
      return "OCR or indexing failed — large PDFs are processed page-by-page; check backend logs and retry";
    case "indexing":
      return "Indexing in progress...";
    case "ocr":
      return "Running OCR (large PDFs: ~15–20 min for 100+ pages). If stuck, use Retry OCR.";
    case "pending":
      return "Waiting to index...";
    case "ready":
      return "Indexed with no searchable chunks";
    default:
      return "Not indexed yet";
  }
}

function StatusBadge({ status }: { status: FileRecord["status"] }) {
  const label = STATUS_LABELS[status] ?? status;

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border-2 px-2.5 py-1 text-xs font-semibold",
        STATUS_STYLES[status] ?? "border-foreground/15 bg-muted text-muted-foreground"
      )}
    >
      {(status === "indexing" || status === "ocr") && (
        <Loader2 className="size-3 animate-spin" />
      )}
      {label}
    </span>
  );
}

export function FilesTab({ workspaceId }: FilesTabProps) {
  const [files, setFiles] = useState<FileRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [ocrAvailable, setOcrAvailable] = useState<boolean | null>(null);
  const [ocrProvider, setOcrProvider] = useState<string | null>(null);
  const [ocrFileId, setOcrFileId] = useState<string | null>(null);
  const [watchFolder, setWatchFolder] = useState<WatchFolder | null>(null);
  const [watchLoading, setWatchLoading] = useState(true);
  const [watchSaving, setWatchSaving] = useState(false);
  const [watchMessage, setWatchMessage] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const loadFiles = useCallback(async () => {
    try {
      const data = await listFiles(workspaceId);
      setFiles(data);
      setError(null);
    } catch {
      setError("Failed to load files");
    } finally {
      setLoading(false);
    }
  }, [workspaceId]);

  const loadWatchFolder = useCallback(async () => {
    setWatchLoading(true);
    try {
      const data = await getWatchFolder(workspaceId);
      setWatchFolder(data);
      setWatchMessage(null);
    } catch {
      setWatchMessage("Failed to load folder watch settings");
    } finally {
      setWatchLoading(false);
    }
  }, [workspaceId]);

  useEffect(() => {
    setLoading(true);
    loadFiles();
    if (supportsFolderWatch()) {
      void loadWatchFolder();
    } else {
      setWatchLoading(false);
    }
  }, [loadFiles, loadWatchFolder]);

  useEffect(() => {
    checkHealth()
      .then((health) => {
        setOcrAvailable(Boolean(health.ocr_available));
        setOcrProvider(health.ocr_provider ?? null);
      })
      .catch(() => {
        setOcrAvailable(false);
        setOcrProvider(null);
      });
  }, [workspaceId]);

  useEffect(() => {
    const needsPoll = files.some(
      (file) =>
        file.status === "pending" ||
        file.status === "indexing" ||
        file.status === "ocr"
    );
    if (!needsPoll) return;

    const interval = setInterval(loadFiles, 2000);
    return () => clearInterval(interval);
  }, [files, loadFiles]);

  async function handleUpload(fileList: FileList | null) {
    if (!fileList?.length) return;

    setUploading(true);
    setError(null);
    try {
      for (const file of Array.from(fileList)) {
        await uploadFile(workspaceId, file);
      }
      await loadFiles();
    } catch {
      setError("Upload failed");
    } finally {
      setUploading(false);
    }
  }

  async function handleRunOcr(fileId: string) {
    setError(null);
    setOcrFileId(fileId);
    try {
      await runFileOcr(workspaceId, fileId);
      await loadFiles();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start OCR");
    } finally {
      setOcrFileId(null);
    }
  }

  function formatWatchTime(value: string | null) {
    if (!value) return "Never scanned";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    return date.toLocaleString();
  }

  async function handleWatchFolder() {
    if (watchSaving) return;

    setWatchSaving(true);
    setWatchMessage(null);
    try {
      const selected = await pickWatchFolder();
      if (!selected) {
        setWatchSaving(false);
        return;
      }

      const saved = await saveWatchFolder(workspaceId, selected, true);
      setWatchFolder(saved);
      setWatchMessage(`Watching ${saved.path}`);
      await loadFiles();
    } catch (err) {
      setWatchMessage(
        err instanceof Error ? err.message : "Failed to start folder watch"
      );
    } finally {
      setWatchSaving(false);
    }
  }

  async function handleStopWatchFolder() {
    if (watchSaving) return;

    setWatchSaving(true);
    setWatchMessage(null);
    try {
      await deleteWatchFolder(workspaceId);
      setWatchFolder(null);
      setWatchMessage("Folder watch stopped.");
    } catch (err) {
      setWatchMessage(
        err instanceof Error ? err.message : "Failed to stop folder watch"
      );
    } finally {
      setWatchSaving(false);
    }
  }

  async function handleDelete(fileId: string) {
    setError(null);
    try {
      await deleteFile(workspaceId, fileId);
      await loadFiles();
    } catch {
      setError("Failed to delete file");
    }
  }

  function onDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDragOver(false);
    handleUpload(e.dataTransfer.files);
  }

  return (
    <div className="flex h-full min-h-0 flex-col gap-6 overflow-y-auto">
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={onDrop}
        className={cn(
          "flex flex-col items-center justify-center rounded-2xl border-2 border-dashed px-6 py-10 text-center transition-colors",
          dragOver
            ? "border-primary bg-primary/5"
            : "border-border bg-card/40 hover:border-primary/40"
        )}
      >
        <div className="mb-4 flex size-12 items-center justify-center rounded-2xl bg-muted">
          <Upload className="size-5 text-muted-foreground" />
        </div>
        <p className="text-sm font-medium">Drop files here to upload</p>
        <p className="mt-1 text-xs text-muted-foreground">
          PDF, DOCX, Markdown, TXT, and code files
        </p>
        <Button
          type="button"
          className="mt-4"
          variant="outline"
          disabled={uploading}
          onClick={() => inputRef.current?.click()}
        >
          {uploading ? (
            <>
              <Loader2 className="size-4 animate-spin" data-icon="inline-start" />
              Uploading...
            </>
          ) : (
            "Choose files"
          )}
        </Button>
        <input
          ref={inputRef}
          type="file"
          multiple
          className="hidden"
          onChange={(e) => {
            handleUpload(e.target.files);
            e.target.value = "";
          }}
        />
      </div>

      {error && (
        <div className="rounded-xl border border-destructive/20 bg-destructive/5 px-4 py-3 text-sm text-destructive">
          {error}
        </div>
      )}

      <div className="rounded-2xl border-2 border-foreground/15 bg-card p-4 shadow-sm">
        <div className="flex items-center gap-2">
          <Eye className="size-4 text-muted-foreground" />
          <h3 className="text-sm font-semibold">Watch folder</h3>
        </div>
        {supportsFolderWatch() ? (
          <>
            <p className="mt-1 text-xs leading-5 text-muted-foreground">
              Pick a local folder. New or updated files are copied into this workspace
              and indexed automatically (about 2-5s after you save a file).
            </p>

            {watchLoading ? (
              <div className="mt-3 flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="size-4 animate-spin" />
                Loading watch settings...
              </div>
            ) : (
              <div className="mt-3 space-y-3">
                <div className="flex flex-wrap gap-2">
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    disabled={watchSaving}
                    onClick={handleWatchFolder}
                  >
                    {watchSaving ? (
                      <Loader2 className="size-4 animate-spin" />
                    ) : (
                      <FolderOpen data-icon="inline-start" className="size-4" />
                    )}
                    {watchFolder ? "Change folder" : "Watch folder"}
                  </Button>
                  {watchFolder && (
                    <Button
                      type="button"
                      size="sm"
                      variant="ghost"
                      disabled={watchSaving}
                      onClick={handleStopWatchFolder}
                    >
                      Stop watching
                    </Button>
                  )}
                </div>

                {watchFolder && (
                  <div className="rounded-xl border border-foreground/10 bg-muted/20 px-3 py-2 text-xs leading-5 text-muted-foreground">
                    <p className="font-medium text-foreground break-all">{watchFolder.path}</p>
                    <p className="mt-1">Last scan: {formatWatchTime(watchFolder.last_scan_at)}</p>
                    <p className="mt-1">
                      Synced files appear as{" "}
                      <span className="font-medium text-foreground">_watched/...</span>
                    </p>
                  </div>
                )}

                {watchMessage && (
                  <p className="text-xs text-muted-foreground">{watchMessage}</p>
                )}
              </div>
            )}
          </>
        ) : (
          <p className="mt-2 text-xs leading-5 text-muted-foreground">
            Folder watch is available in the Desktop edition. In the cloud web app, upload
            files below.
          </p>
        )}
      </div>

      <div className="rounded-2xl border-2 border-foreground/15 bg-card shadow-sm">
        <div className="border-b-2 border-foreground/10 px-4 py-3">
          <h3 className="text-sm font-semibold">Uploaded files</h3>
          <p className="text-xs text-muted-foreground">
            Status updates every 2s while indexing or OCR
          </p>
        </div>

        {loading ? (
          <div className="flex items-center gap-2 px-4 py-8 text-sm text-muted-foreground">
            <Loader2 className="size-4 animate-spin" />
            Loading files...
          </div>
        ) : files.length === 0 ? (
          <div className="px-4 py-8 text-center text-sm text-muted-foreground">
            No files yet. Upload a document to start indexing.
          </div>
        ) : (
          <ul className="divide-y divide-border">
            {files.map((file) => (
              <li
                key={file.id}
                className="flex items-center justify-between gap-4 px-4 py-3"
              >
                <div className="flex min-w-0 items-center gap-3">
                  <div className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-muted">
                    <FileText className="size-4 text-muted-foreground" />
                  </div>
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium">{file.filename}</p>
                    <p className="text-xs leading-5 text-muted-foreground">
                      {fileDetailText(file)}
                    </p>
                  </div>
                </div>

                <div className="flex shrink-0 items-center gap-2">
                  {(file.status === "needs_ocr" ||
                    file.status === "failed" ||
                    file.status === "ocr") &&
                    file.filename.toLowerCase().endsWith(".pdf") && (
                      <Button
                        type="button"
                        size="sm"
                        variant="outline"
                        disabled={ocrFileId === file.id || ocrAvailable === false}
                        onClick={() => handleRunOcr(file.id)}
                        title={
                          ocrAvailable === false
                            ? ocrProvider === "azure"
                              ? "Set AZURE_VISION_ENDPOINT and AZURE_VISION_KEY"
                              : "Install Tesseract: brew install tesseract"
                            : file.status === "ocr"
                              ? "Restart OCR if the job was interrupted"
                              : ocrProvider === "azure"
                                ? "Send PDF to Azure Computer Vision Read (cloud, F0 free tier)"
                                : "Extract text locally with Tesseract"
                        }
                      >
                        {ocrFileId === file.id ? (
                          <Loader2 className="size-3.5 animate-spin" data-icon="inline-start" />
                        ) : (
                          <ScanText data-icon="inline-start" className="size-3.5" />
                        )}
                        {file.status === "ocr" ? "Retry OCR" : "Run OCR"}
                      </Button>
                    )}
                  <StatusBadge status={file.status} />
                  <Button
                    type="button"
                    size="icon-sm"
                    variant="ghost"
                    onClick={() => handleDelete(file.id)}
                    aria-label={`Delete ${file.filename}`}
                  >
                    <Trash2 className="size-4" />
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
