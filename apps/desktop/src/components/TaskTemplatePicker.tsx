import { useCallback, useEffect, useState } from "react";
import { LayoutTemplate, Loader2, Play } from "lucide-react";

import { listTemplates, type TaskTemplate } from "@/lib/api";
import { cn } from "@/lib/utils";

type TaskTemplatePickerProps = {
  workspaceId: string;
  selectedTemplate: TaskTemplate | null;
  onSelect: (template: TaskTemplate | null) => void;
  onRunTemplate: (template: TaskTemplate) => void;
  disabled?: boolean;
};

export function TaskTemplatePicker({
  workspaceId,
  selectedTemplate,
  onSelect,
  onRunTemplate,
  disabled = false,
}: TaskTemplatePickerProps) {
  const [templates, setTemplates] = useState<TaskTemplate[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadTemplates = useCallback(async () => {
    try {
      const data = await listTemplates(workspaceId);
      setTemplates(data);
      setError(null);
    } catch {
      setError("Failed to load task templates");
    } finally {
      setLoading(false);
    }
  }, [workspaceId]);

  useEffect(() => {
    setLoading(true);
    loadTemplates();
  }, [loadTemplates]);

  function handleChipClick(template: TaskTemplate) {
    if (disabled) return;
    if (selectedTemplate?.id === template.id) {
      onSelect(null);
      return;
    }
    onSelect(template);
  }

  return (
    <div className="shrink-0 space-y-3 border-b-2 border-foreground/10 px-4 py-3">
      <div className="flex items-center gap-2">
        <LayoutTemplate className="size-4 text-muted-foreground" />
        <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Task templates
        </p>
      </div>

      {error && (
        <div className="rounded-xl border-2 border-destructive/25 bg-destructive/5 px-3 py-2 text-xs text-destructive">
          {error}
        </div>
      )}

      {loading ? (
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <Loader2 className="size-3.5 animate-spin" />
          Loading templates...
        </div>
      ) : (
        <div className="flex gap-2 overflow-x-auto pb-1">
          {templates.map((template) => {
            const isSelected = selectedTemplate?.id === template.id;
            return (
              <div key={template.id} className="flex shrink-0 items-stretch gap-1">
                <button
                  type="button"
                  disabled={disabled}
                  onClick={() => handleChipClick(template)}
                  title={template.description}
                  className={cn(
                    "rounded-xl border-2 px-3 py-2 text-left text-xs transition-colors",
                    "focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/40",
                    isSelected
                      ? "border-primary/40 bg-primary/[0.06] text-foreground shadow-sm"
                      : "border-foreground/20 bg-background text-foreground hover:border-foreground/30 hover:bg-muted/40",
                    disabled && "cursor-not-allowed opacity-50"
                  )}
                >
                  <span className="block font-semibold">{template.label}</span>
                </button>
                {isSelected && (
                  <button
                    type="button"
                    disabled={disabled}
                    onClick={() => onRunTemplate(template)}
                    title="Run template now"
                    className={cn(
                      "inline-flex items-center gap-1 rounded-xl border-2 border-primary/40 bg-primary px-2.5 text-xs font-semibold text-primary-foreground shadow-sm",
                      "focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/40",
                      disabled && "cursor-not-allowed opacity-50"
                    )}
                  >
                    <Play className="size-3.5" />
                    Run
                  </button>
                )}
              </div>
            );
          })}
        </div>
      )}

      {selectedTemplate && (
        <div className="rounded-xl border-2 border-primary/25 bg-primary/[0.03] px-3 py-2 text-xs leading-5 text-muted-foreground">
          <span className="font-semibold text-foreground">{selectedTemplate.label}</span>
          {" — "}
          {selectedTemplate.description}
          <span className="mt-1 block text-[0.7rem] text-muted-foreground">
            Add optional notes below, then Send — or click Run to send immediately.
          </span>
        </div>
      )}
    </div>
  );
}
