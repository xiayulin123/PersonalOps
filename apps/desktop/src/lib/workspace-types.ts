import { BookOpen, Briefcase, Code2, Home, type LucideIcon } from "lucide-react";

export type WorkspaceType = "study" | "code" | "life" | "career";

export const WORKSPACE_TYPES: WorkspaceType[] = [
  "study",
  "code",
  "life",
  "career",
];

export const WORKSPACE_TYPE_META: Record<
  WorkspaceType,
  { label: string; description: string; icon: LucideIcon }
> = {
  study: {
    label: "Study",
    description: "Lectures, exams, assignments",
    icon: BookOpen,
  },
  code: {
    label: "Code",
    description: "Repos, README, CI logs",
    icon: Code2,
  },
  life: {
    label: "Life",
    description: "Notes, todos, personal docs",
    icon: Home,
  },
  career: {
    label: "Career",
    description: "Resume, JD, interview prep",
    icon: Briefcase,
  },
};

export function isWorkspaceType(value: string): value is WorkspaceType {
  return WORKSPACE_TYPES.includes(value as WorkspaceType);
}

export function getWorkspaceMeta(type: string) {
  if (isWorkspaceType(type)) {
    return WORKSPACE_TYPE_META[type];
  }
  return WORKSPACE_TYPE_META.study;
}
