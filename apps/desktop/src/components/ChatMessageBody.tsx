import { useState } from "react";
import { Check, ChevronDown, Copy } from "lucide-react";
import type { Components } from "react-markdown";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { Button } from "@/components/ui/button";
import {
  splitMarkdownSections,
  type MarkdownSection,
} from "@/lib/chat-message-markdown";
import { cn } from "@/lib/utils";

type ChatMessageBodyProps = {
  content: string;
};

const markdownComponents: Components = {
  h1: ({ children }) => (
    <h3 className="mt-4 text-base font-semibold tracking-tight first:mt-0">
      {children}
    </h3>
  ),
  h2: ({ children }) => (
    <h4 className="mt-4 text-sm font-semibold tracking-tight first:mt-0">
      {children}
    </h4>
  ),
  h3: ({ children }) => (
    <h5 className="mt-3 text-sm font-semibold first:mt-0">{children}</h5>
  ),
  p: ({ children }) => (
    <p className="text-sm leading-6 text-foreground">{children}</p>
  ),
  strong: ({ children }) => (
    <strong className="font-semibold text-foreground">{children}</strong>
  ),
  em: ({ children }) => <em className="italic">{children}</em>,
  ul: ({ children }) => (
    <ul className="list-disc space-y-1.5 pl-5 text-sm leading-6">{children}</ul>
  ),
  ol: ({ children }) => (
    <ol className="list-decimal space-y-1.5 pl-5 text-sm leading-6">{children}</ol>
  ),
  li: ({ children }) => <li className="pl-0.5">{children}</li>,
  blockquote: ({ children }) => (
    <blockquote className="border-l-2 border-primary/30 pl-3 text-sm italic text-muted-foreground">
      {children}
    </blockquote>
  ),
  hr: () => <hr className="my-3 border-foreground/10" />,
  code: ({ className, children, ...props }) => {
    const isBlock = Boolean(className);
    if (isBlock) {
      return (
        <code
          className={cn(
            "block overflow-x-auto rounded-lg border border-foreground/10 bg-background/80 px-3 py-2 font-mono text-xs leading-5",
            className
          )}
          {...props}
        >
          {children}
        </code>
      );
    }
    return (
      <code
        className="rounded bg-background/80 px-1 py-0.5 font-mono text-[0.85em]"
        {...props}
      >
        {children}
      </code>
    );
  },
  pre: ({ children }) => (
    <pre className="my-2 overflow-x-auto rounded-lg border border-foreground/10 bg-background/80 p-3">
      {children}
    </pre>
  ),
  table: ({ children }) => (
    <div className="my-3 overflow-x-auto rounded-xl border border-foreground/15">
      <table className="w-full min-w-[280px] border-collapse text-left text-xs">
        {children}
      </table>
    </div>
  ),
  thead: ({ children }) => (
    <thead className="bg-muted/60 text-foreground">{children}</thead>
  ),
  tbody: ({ children }) => (
    <tbody className="divide-y divide-foreground/10">{children}</tbody>
  ),
  tr: ({ children }) => (
    <tr className="border-b border-foreground/10 last:border-0">{children}</tr>
  ),
  th: ({ children }) => (
    <th className="px-3 py-2 font-semibold text-foreground">{children}</th>
  ),
  td: ({ children }) => (
    <td className="px-3 py-2 align-top leading-5 text-foreground/90">{children}</td>
  ),
  a: ({ href, children }) => (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className="font-medium text-primary underline-offset-2 hover:underline"
    >
      {children}
    </a>
  ),
};

function MarkdownBlock({ markdown }: { markdown: string }) {
  if (!markdown.trim()) {
    return null;
  }

  return (
    <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
      {markdown}
    </ReactMarkdown>
  );
}

function CollapsibleSection({ section }: { section: MarkdownSection }) {
  const [open, setOpen] = useState(section.defaultOpen);
  const title = section.title ?? "Details";
  const lineCount = section.body.split("\n").filter(Boolean).length;

  return (
    <details
      open={open}
      onToggle={(event) => setOpen((event.currentTarget as HTMLDetailsElement).open)}
      className="group rounded-xl border border-foreground/15 bg-background/50"
    >
      <summary className="flex cursor-pointer list-none items-center justify-between gap-2 rounded-xl px-3 py-2.5 text-sm font-semibold text-foreground marker:content-none [&::-webkit-details-marker]:hidden">
        <span className="min-w-0 truncate">{title}</span>
        <span className="flex shrink-0 items-center gap-2 text-xs font-normal text-muted-foreground">
          <span className="hidden sm:inline">
            {lineCount} line{lineCount === 1 ? "" : "s"} · click to expand
          </span>
          <ChevronDown
            className={cn(
              "size-4 transition-transform",
              open && "rotate-180"
            )}
          />
        </span>
      </summary>
      <div className="border-t border-foreground/10 px-3 pb-3 pt-2">
        <MarkdownBlock markdown={section.body} />
      </div>
    </details>
  );
}

function TitledSection({ section }: { section: MarkdownSection }) {
  return (
    <div className="space-y-2">
      {section.title && (
        <h4 className="text-sm font-semibold tracking-tight text-foreground">
          {section.title}
        </h4>
      )}
      <MarkdownBlock markdown={section.body} />
    </div>
  );
}

function CopyMarkdownButton({ content }: { content: string }) {
  const [copied, setCopied] = useState(false);

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(content);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1800);
    } catch {
      setCopied(false);
    }
  }

  return (
    <Button
      type="button"
      size="sm"
      variant="ghost"
      onClick={handleCopy}
      className="h-7 gap-1.5 px-2 text-xs text-muted-foreground hover:text-foreground"
      aria-label="Copy message as Markdown"
    >
      {copied ? (
        <>
          <Check className="size-3.5 text-primary" />
          Copied
        </>
      ) : (
        <>
          <Copy className="size-3.5" />
          Copy Markdown
        </>
      )}
    </Button>
  );
}

export function ChatMessageBody({ content }: ChatMessageBodyProps) {
  const sections = splitMarkdownSections(content);
  const hasCollapsible = sections.some((section) => section.collapsible);

  return (
    <div className="chat-markdown space-y-3">
      <div className="flex items-start justify-end gap-2">
        {hasCollapsible && (
          <p className="mr-auto text-[10px] leading-4 text-muted-foreground">
            Long evidence sections are collapsed by default.
          </p>
        )}
        <CopyMarkdownButton content={content} />
      </div>

      {sections.map((section, index) => {
        const key = `${section.title ?? "intro"}-${index}`;

        if (section.collapsible && section.title) {
          return <CollapsibleSection key={key} section={section} />;
        }

        if (section.title) {
          return <TitledSection key={key} section={section} />;
        }

        return (
          <div key={key}>
            <MarkdownBlock markdown={section.body} />
          </div>
        );
      })}
    </div>
  );
}
