export type MarkdownSection = {
  title: string | null;
  body: string;
  collapsible: boolean;
  defaultOpen: boolean;
};

const COLLAPSE_TITLE_PATTERNS = [
  /原文依据/,
  /原文引用/,
  /引用原文/,
  /证据来源/,
  /原文摘录/,
  /原文片段/,
  /出处/,
  /引文/,
  /original evidence/i,
  /source excerpts?/i,
  /citations?/i,
  /quoted passages?/i,
];

const OPEN_TITLE_PATTERNS = [
  /结论/,
  /总结/,
  /摘要/,
  /answer/i,
  /summary/i,
  /conclusion/i,
];

export function isCollapsibleEvidenceTitle(title: string): boolean {
  const trimmed = title.trim();
  if (OPEN_TITLE_PATTERNS.some((pattern) => pattern.test(trimmed))) {
    return false;
  }
  if (COLLAPSE_TITLE_PATTERNS.some((pattern) => pattern.test(trimmed))) {
    return true;
  }
  return false;
}

export function splitMarkdownSections(content: string): MarkdownSection[] {
  const lines = content.split("\n");
  const sections: MarkdownSection[] = [];
  let currentTitle: string | null = null;
  let currentLines: string[] = [];

  const flush = () => {
    const body = currentLines.join("\n").trim();
    if (!body && currentTitle === null) {
      return;
    }

    const title = currentTitle;
    const collapsible = title ? isCollapsibleEvidenceTitle(title) : false;
    sections.push({
      title,
      body: title ? body : body || content.trim(),
      collapsible,
      defaultOpen: title ? !collapsible : true,
    });
    currentLines = [];
  };

  for (const line of lines) {
    const h2Match = line.match(/^##\s+(.+?)\s*$/);
    const h3Match = !h2Match ? line.match(/^###\s+(.+?)\s*$/) : null;
    const heading = h2Match?.[1] ?? h3Match?.[1];

    if (heading) {
      flush();
      currentTitle = heading.trim();
      continue;
    }

    currentLines.push(line);
  }

  flush();

  if (sections.length === 0 && content.trim()) {
    return [
      {
        title: null,
        body: content.trim(),
        collapsible: false,
        defaultOpen: true,
      },
    ];
  }

  return sections.filter((section) => section.title || section.body);
}
