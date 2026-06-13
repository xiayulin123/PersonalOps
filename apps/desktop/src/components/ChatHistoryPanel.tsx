import { useEffect, useState } from "react";
import {
  ChevronDown,
  ChevronRight,
  History,
  Loader2,
  PanelLeftClose,
  PanelLeftOpen,
  Plus,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import type { ConversationRecord } from "@/lib/api";
import { cn } from "@/lib/utils";

type ChatHistoryPanelProps = {
  workspaceId: string;
  conversations: ConversationRecord[];
  activeConversationId: string | null;
  loading?: boolean;
  creating?: boolean;
  collapsed: boolean;
  onToggleCollapse: () => void;
  onNewChat: () => void;
  onSelectConversation: (conversationId: string) => void;
};

function previewTitle(title: string, max = 56): string {
  const trimmed = title.replace(/\s+/g, " ").trim();
  if (trimmed.length <= max) return trimmed;
  return `${trimmed.slice(0, max)}...`;
}

export function ChatHistoryPanel({
  workspaceId,
  conversations,
  activeConversationId,
  loading = false,
  creating = false,
  collapsed,
  onToggleCollapse,
  onNewChat,
  onSelectConversation,
}: ChatHistoryPanelProps) {
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());

  useEffect(() => {
    setExpandedIds(new Set());
  }, [workspaceId]);

  useEffect(() => {
    if (!activeConversationId) return;
    setExpandedIds((prev) => new Set([...prev, activeConversationId]));
  }, [activeConversationId]);

  function toggleExpanded(conversationId: string) {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(conversationId)) {
        next.delete(conversationId);
      } else {
        next.add(conversationId);
      }
      return next;
    });
  }

  if (collapsed) {
    return (
      <aside className="flex w-11 shrink-0 flex-col items-center border-r-2 border-foreground/10 bg-muted/20 py-2">
        <Button
          type="button"
          size="icon-sm"
          variant="ghost"
          onClick={onToggleCollapse}
          title="Show chat history"
          aria-label="Show chat history"
        >
          <PanelLeftOpen className="size-4" />
        </Button>
        <Button
          type="button"
          size="icon-sm"
          variant="ghost"
          className="mt-1"
          onClick={onNewChat}
          disabled={creating}
          title="New chat"
          aria-label="New chat"
        >
          <Plus className="size-4" />
        </Button>
      </aside>
    );
  }

  return (
    <aside className="flex w-60 shrink-0 flex-col border-r-2 border-foreground/10 bg-muted/20">
      <div className="flex items-center gap-1 border-b border-foreground/10 px-2 py-2.5">
        <History className="size-4 shrink-0 text-muted-foreground" />
        <div className="min-w-0 flex-1">
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Chat history
          </p>
          <p className="text-[10px] text-muted-foreground">
            {loading
              ? "Loading..."
              : `${conversations.length} session${conversations.length === 1 ? "" : "s"}`}
          </p>
        </div>
        <Button
          type="button"
          size="icon-sm"
          variant="ghost"
          onClick={onToggleCollapse}
          title="Hide chat history"
          aria-label="Hide chat history"
        >
          <PanelLeftClose className="size-4" />
        </Button>
      </div>

      <div className="border-b border-foreground/10 p-2">
        <Button
          type="button"
          size="sm"
          variant="outline"
          className="w-full justify-start"
          onClick={onNewChat}
          disabled={creating}
        >
          {creating ? (
            <Loader2 className="size-4 animate-spin" data-icon="inline-start" />
          ) : (
            <Plus data-icon="inline-start" className="size-4" />
          )}
          New Chat
        </Button>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto p-2">
        {loading ? (
          <div className="flex items-center justify-center py-8 text-muted-foreground">
            <Loader2 className="size-4 animate-spin" />
          </div>
        ) : conversations.length === 0 ? (
          <p className="px-2 py-4 text-xs leading-5 text-muted-foreground">
            No chats yet. Click <strong>New Chat</strong> to start.
          </p>
        ) : (
          <ul className="space-y-2">
            {conversations.map((conversation, index) => {
              const expanded = expandedIds.has(conversation.id);
              const active = conversation.id === activeConversationId;

              return (
                <li
                  key={conversation.id}
                  className={cn(
                    "rounded-lg border bg-background/70",
                    active
                      ? "border-primary/30 ring-1 ring-primary/20"
                      : "border-foreground/10"
                  )}
                >
                  <div className="flex items-start gap-1 p-1.5">
                    <Button
                      type="button"
                      size="icon-sm"
                      variant="ghost"
                      className="mt-0.5 size-6 shrink-0"
                      onClick={() => toggleExpanded(conversation.id)}
                      aria-label={expanded ? "Collapse session" : "Expand session"}
                    >
                      {expanded ? (
                        <ChevronDown className="size-3.5" />
                      ) : (
                        <ChevronRight className="size-3.5" />
                      )}
                    </Button>

                    <button
                      type="button"
                      onClick={() => onSelectConversation(conversation.id)}
                      className="min-w-0 flex-1 rounded-md px-1 py-0.5 text-left hover:bg-muted/60"
                    >
                      <p
                        className={cn(
                          "text-[10px] font-semibold uppercase tracking-wide",
                          active ? "text-primary" : "text-muted-foreground"
                        )}
                      >
                        {active ? "Current" : `Session ${conversations.length - index}`}
                      </p>
                      <p className="mt-0.5 line-clamp-2 text-xs leading-5 text-foreground">
                        {previewTitle(conversation.title)}
                      </p>
                      <p className="mt-1 text-[10px] text-muted-foreground">
                        {conversation.message_count} message
                        {conversation.message_count === 1 ? "" : "s"}
                      </p>
                    </button>
                  </div>

                  {expanded && (
                    <div className="border-t border-foreground/10 px-3 py-2 text-[11px] leading-4 text-muted-foreground">
                      {conversation.message_count === 0
                        ? "Empty chat — send a message to begin."
                        : "Open this session in the main chat area."}
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </aside>
  );
}
