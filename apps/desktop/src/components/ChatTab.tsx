import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { Loader2, Send, Square } from "lucide-react";

import { Button } from "@/components/ui/button";
import { AgentTraceLive, AssistantMeta } from "@/components/ChatAgentMeta";
import { ChatHistoryPanel } from "@/components/ChatHistoryPanel";
import { ChatMessageBody } from "@/components/ChatMessageBody";
import { TaskTemplatePicker } from "@/components/TaskTemplatePicker";
import {
  ChatStreamAbortedError,
  createConversation,
  listChatMessages,
  listConversations,
  sendChatStream,
  type AgentStep,
  type ChatMessageRecord,
  type ChatMode,
  type ChatSource,
  type ConversationRecord,
  type TaskTemplate,
  type WebSource,
} from "@/lib/api";
import { cn } from "@/lib/utils";

type ChatTabProps = {
  workspaceId: string;
  chatMode?: ChatMode;
};

type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  feedbackRating?: 1 | 5 | null;
  sources?: ChatSource[];
  webSources?: WebSource[];
  trace?: AgentStep[];
  route?: string;
  chatEngine?: string | null;
  agentLabel?: string | null;
};

function recordToChatMessage(record: ChatMessageRecord): ChatMessage {
  const rating = record.feedback_rating;
  return {
    id: record.id,
    role: record.role,
    content: record.content,
    sources: record.sources,
    webSources: record.web_sources,
    trace: record.trace,
    route: record.route ?? record.agent_label ?? undefined,
    chatEngine: record.chat_engine,
    agentLabel: record.agent_label,
    feedbackRating: rating === 1 || rating === 5 ? rating : null,
  };
}

export function ChatTab({ workspaceId, chatMode = "langgraph" }: ChatTabProps) {
  const [conversations, setConversations] = useState<ConversationRecord[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loadingConversations, setLoadingConversations] = useState(true);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [creatingConversation, setCreatingConversation] = useState(false);
  const [input, setInput] = useState("");
  const [selectedTemplate, setSelectedTemplate] = useState<TaskTemplate | null>(null);
  const [sending, setSending] = useState(false);
  const [liveTrace, setLiveTrace] = useState<AgentStep[]>([]);
  const [liveRoute, setLiveRoute] = useState<string | undefined>();
  const [error, setError] = useState<string | null>(null);
  const [historyPanelOpen, setHistoryPanelOpen] = useState(false);
  const messagesRef = useRef<HTMLDivElement>(null);
  const isComposingRef = useRef(false);
  const abortControllerRef = useRef<AbortController | null>(null);
  const liveTraceRef = useRef<AgentStep[]>([]);
  const liveRouteRef = useRef<string | undefined>(undefined);
  const shouldAutoScrollRef = useRef(true);
  const scrollAnchorMessageIdRef = useRef<string | null>(null);

  function scrollMessageToTop(messageId: string) {
    const container = messagesRef.current;
    if (!container) return;
    const el = document.getElementById(`chat-msg-${messageId}`);
    if (!el) return;
    const containerTop = container.getBoundingClientRect().top;
    const elTop = el.getBoundingClientRect().top;
    container.scrollTop += elTop - containerTop - 16;
  }

  const handleSelectTemplate = useCallback((template: TaskTemplate | null) => {
    setSelectedTemplate(template);
  }, []);

  const loadMessagesForConversation = useCallback(
    async (targetConversationId: string | null) => {
      if (!targetConversationId) {
        setMessages([]);
        return;
      }
      setLoadingMessages(true);
      try {
        const records = await listChatMessages(workspaceId, targetConversationId);
        setMessages(records.map(recordToChatMessage));
      } catch {
        setMessages([]);
        setError("Failed to load chat messages.");
      } finally {
        setLoadingMessages(false);
      }
    },
    [workspaceId]
  );

  const refreshConversations = useCallback(
    async (preferredId?: string | null) => {
      const items = await listConversations(workspaceId);
      setConversations(items);
      if (preferredId && items.some((item) => item.id === preferredId)) {
        return preferredId;
      }
      return items[0]?.id ?? null;
    },
    [workspaceId]
  );

  useEffect(() => {
    let cancelled = false;

    setSelectedTemplate(null);
    setInput("");
    setError(null);
    setConversationId(null);
    setMessages([]);
    setConversations([]);
    setLoadingConversations(true);
    shouldAutoScrollRef.current = true;
    scrollAnchorMessageIdRef.current = null;

    async function bootstrap() {
      try {
        const items = await listConversations(workspaceId);
        if (cancelled) return;
        setConversations(items);
        const activeId = items[0]?.id ?? null;
        setConversationId(activeId);
        if (activeId) {
          const records = await listChatMessages(workspaceId, activeId);
          if (!cancelled) setMessages(records.map(recordToChatMessage));
        }
      } catch {
        if (!cancelled) {
          setConversations([]);
          setMessages([]);
          setError("Failed to load chat history.");
        }
      } finally {
        if (!cancelled) setLoadingConversations(false);
      }
    }

    void bootstrap();
    return () => {
      cancelled = true;
    };
  }, [workspaceId]);

  async function handleNewChat() {
    if (creatingConversation || sending) return;
    setCreatingConversation(true);
    setError(null);
    try {
      const created = await createConversation(workspaceId);
      setConversations((prev) => [created, ...prev]);
      setConversationId(created.id);
      setMessages([]);
      setSelectedTemplate(null);
      setInput("");
      shouldAutoScrollRef.current = true;
      scrollAnchorMessageIdRef.current = null;
    } catch {
      setError("Failed to create a new chat.");
    } finally {
      setCreatingConversation(false);
    }
  }

  async function handleSelectConversation(targetId: string) {
    if (targetId === conversationId || sending) return;
    setConversationId(targetId);
    shouldAutoScrollRef.current = true;
    scrollAnchorMessageIdRef.current = null;
    await loadMessagesForConversation(targetId);
  }

  useEffect(() => {
    const container = messagesRef.current;
    if (!container) return;

    const anchorId = scrollAnchorMessageIdRef.current;
    if (anchorId) {
      requestAnimationFrame(() => scrollMessageToTop(anchorId));
      return;
    }

    if (shouldAutoScrollRef.current) {
      container.scrollTop = container.scrollHeight;
    }
  }, [messages]);

  async function submitMessage(message: string, template: TaskTemplate | null) {
    const trimmed = message.trim();
    if ((!trimmed && !template) || sending) return;

    let activeConversationId = conversationId;
    try {
      if (!activeConversationId) {
        const created = await createConversation(workspaceId);
        activeConversationId = created.id;
        setConversationId(created.id);
        setConversations((prev) => [created, ...prev]);
      }
    } catch {
      setError("Failed to create a new chat.");
      return;
    }

    setError(null);
    setSending(true);
    setLiveTrace([]);
    liveTraceRef.current = [];
    setLiveRoute(undefined);
    liveRouteRef.current = undefined;
    setInput("");
    shouldAutoScrollRef.current = false;

    const abortController = new AbortController();
    abortControllerRef.current = abortController;

    const displayContent = template
      ? trimmed
        ? `[${template.label}] ${trimmed}`
        : `[${template.label}]`
      : trimmed;

    const pendingUserId = `pending-${crypto.randomUUID()}`;
    scrollAnchorMessageIdRef.current = pendingUserId;
    setMessages((prev) => [
      ...prev,
      { id: pendingUserId, role: "user", content: displayContent },
    ]);

    try {
      const res = await sendChatStream(
        workspaceId,
        trimmed,
        (step) => {
          liveTraceRef.current = [...liveTraceRef.current, step];
          setLiveTrace(liveTraceRef.current);
          if (step.label === "Classified request" && step.detail) {
            liveRouteRef.current = step.detail;
            setLiveRoute(step.detail);
          }
        },
        template?.id ?? null,
        abortController.signal,
        activeConversationId
      );
      setMessages((prev) => [
        ...prev,
        {
          id: res.assistant_message_id ?? `assistant-${crypto.randomUUID()}`,
          role: "assistant",
          content: res.answer,
          sources: res.sources,
          webSources: res.web_sources,
          trace: res.trace,
          route: res.route ?? res.agent_label ?? undefined,
          chatEngine: res.chat_engine,
          agentLabel: res.agent_label,
        },
      ]);
      const nextActiveId = await refreshConversations(activeConversationId);
      if (nextActiveId) setConversationId(nextActiveId);
      setSelectedTemplate(null);
    } catch (err) {
      if (err instanceof ChatStreamAbortedError) {
        setMessages((prev) => [
          ...prev,
          {
            id: `stopped-${crypto.randomUUID()}`,
            role: "assistant",
            content: "已停止生成。",
            trace: liveTraceRef.current,
            route: liveRouteRef.current,
            chatEngine: chatMode === "cursor_agent" ? "cursor_agent" : "langgraph",
          },
        ]);
      } else {
        const detail = err instanceof Error ? err.message : "Unknown error";
        setError(
          chatMode === "cursor_agent"
            ? `Chat failed: ${detail}. Check CURSOR_API_KEY and backend logs.`
            : `Chat request failed: ${detail}`
        );
        setInput(trimmed);
        setMessages((prev) => prev.slice(0, -1));
        scrollAnchorMessageIdRef.current = null;
        shouldAutoScrollRef.current = true;
      }
    } finally {
      abortControllerRef.current = null;
      setSending(false);
      setLiveTrace([]);
      liveTraceRef.current = [];
      setLiveRoute(undefined);
      liveRouteRef.current = undefined;
    }
  }

  function handleStop() {
    abortControllerRef.current?.abort();
  }

  async function handleSend(e?: FormEvent) {
    e?.preventDefault();
    await submitMessage(input, selectedTemplate);
  }

  async function handleRunTemplate(template: TaskTemplate) {
    await submitMessage(input, template);
  }

  const canSend = Boolean(input.trim() || selectedTemplate);

  return (
    <div className="flex h-full min-h-0 flex-col rounded-2xl border-2 border-foreground/15 bg-card shadow-sm">
      <TaskTemplatePicker
        workspaceId={workspaceId}
        selectedTemplate={selectedTemplate}
        onSelect={handleSelectTemplate}
        onRunTemplate={handleRunTemplate}
        disabled={sending}
      />

      <div className="flex min-h-0 flex-1">
        <ChatHistoryPanel
          workspaceId={workspaceId}
          conversations={conversations}
          activeConversationId={conversationId}
          loading={loadingConversations}
          creating={creatingConversation}
          collapsed={!historyPanelOpen}
          onToggleCollapse={() => setHistoryPanelOpen((open) => !open)}
          onNewChat={() => void handleNewChat()}
          onSelectConversation={(id) => void handleSelectConversation(id)}
        />

        <div className="flex min-w-0 flex-1 flex-col">
          <div
            ref={messagesRef}
            className="min-h-0 flex-1 space-y-4 overflow-y-auto px-4 py-4"
          >
            {!loadingConversations && !loadingMessages && messages.length === 0 && (
              <div className="flex h-full min-h-[200px] flex-col items-center justify-center rounded-2xl border-2 border-dashed border-foreground/15 bg-muted/20 px-6 text-center">
                <p className="text-sm font-medium">Ask about your workspace files</p>
                <p className="mt-1 max-w-md text-xs leading-5 text-muted-foreground">
                  {chatMode === "cursor_agent"
                    ? "Cursor Agent reads files in uploads/ directly. Ask about your documents or list workspace files."
                    : 'Pick a task template above, or type a question like "Summarize the main topics in my document."'}
                </p>
              </div>
            )}

            {(loadingConversations || loadingMessages) && (
              <div className="flex items-center justify-center gap-2 py-12 text-sm text-muted-foreground">
                <Loader2 className="size-4 animate-spin" />
                Loading chat...
              </div>
            )}

            {messages.map((message, index) => (
              <div
                key={message.id}
                id={`chat-msg-${message.id}`}
                className={cn(
                  "flex scroll-mt-4",
                  message.role === "user" ? "justify-end" : "justify-start"
                )}
              >
                <div
                  className={cn(
                    "max-w-[85%] rounded-2xl border-2 px-4 py-3 text-sm leading-6",
                    message.role === "user"
                      ? "border-primary/30 bg-primary text-primary-foreground"
                      : "border-2 border-foreground/15 bg-muted text-foreground shadow-sm",
                  )}
                >
                  {message.role === "assistant" ? (
                    <ChatMessageBody content={message.content} />
                  ) : (
                    <p className="whitespace-pre-wrap">{message.content}</p>
                  )}

                  {message.role === "assistant" && (
                    <AssistantMeta
                      trace={message.trace}
                      route={message.route}
                      chatEngine={message.chatEngine}
                      sources={message.sources}
                      webSources={message.webSources}
                      messageId={
                        message.id.startsWith("assistant-") ||
                        message.id.startsWith("stopped-")
                          ? undefined
                          : message.id
                      }
                      feedbackRating={message.feedbackRating}
                      onFeedback={(rating) => {
                        setMessages((prev) =>
                          prev.map((item, itemIndex) =>
                            itemIndex === index ? { ...item, feedbackRating: rating } : item
                          )
                        );
                      }}
                    />
                  )}
                </div>
              </div>
            ))}

            {sending && (
              <div className="flex justify-start">
                <div className="max-w-[85%] rounded-2xl border-2 border-foreground/15 bg-muted px-4 py-3 text-sm shadow-sm">
                  <div className="flex items-center justify-between gap-3">
                    <div className="flex items-center gap-2 text-muted-foreground">
                      <Loader2 className="size-4 animate-spin" />
                      Thinking...
                    </div>
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      onClick={handleStop}
                      className="h-7 shrink-0 border-destructive/30 text-destructive hover:bg-destructive/10"
                    >
                      <Square className="size-3 fill-current" />
                      Stop
                    </Button>
                  </div>
                  <AgentTraceLive
                    steps={liveTrace}
                    route={liveRoute}
                    chatEngine={chatMode === "cursor_agent" ? "cursor_agent" : "langgraph"}
                    running
                  />
                </div>
              </div>
            )}
          </div>

          {error && (
            <div className="mx-4 mb-2 shrink-0 rounded-xl border-2 border-destructive/25 bg-destructive/5 px-3 py-2 text-sm text-destructive">
              {error}
            </div>
          )}

          <form
            onSubmit={handleSend}
            className="flex shrink-0 items-end gap-2 border-t-2 border-foreground/10 px-4 py-4"
          >
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onCompositionStart={() => {
                isComposingRef.current = true;
              }}
              onCompositionEnd={() => {
                isComposingRef.current = false;
              }}
              onKeyDown={(e) => {
                if (e.key !== "Enter" || e.shiftKey) return;
                if (
                  isComposingRef.current ||
                  e.nativeEvent.isComposing ||
                  e.keyCode === 229
                ) {
                  return;
                }
                e.preventDefault();
                void handleSend();
              }}
              placeholder={
                selectedTemplate
                  ? `Optional notes for "${selectedTemplate.label}"...`
                  : "Ask a question about your files..."
              }
              rows={2}
              className="max-h-32 min-h-[44px] flex-1 resize-none rounded-xl border-2 border-foreground/20 bg-background px-3 py-2 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/30"
            />
            {sending ? (
              <Button
                type="button"
                variant="destructive"
                onClick={handleStop}
                className="shrink-0"
              >
                <Square className="size-4 fill-current" data-icon="inline-start" />
                Stop
              </Button>
            ) : (
              <Button type="submit" disabled={!canSend} className="shrink-0">
                <Send data-icon="inline-start" />
                Send
              </Button>
            )}
          </form>
        </div>
      </div>
    </div>
  );
}
