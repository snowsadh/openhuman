export interface Agent {
  id: string;
  name: string;
  description: string;
  image?: string;
  color: string;
}

// Stub — hardcoded until the templates API exists.

const templates: Agent[] = [
  {
    id: "marketing",
    name: "Marketing",
    description:
      "Drafts campaigns, monitors brand mentions, and analyzes market trends across every channel.",
    color: "#ef4444",
  },
  {
    id: "content",
    name: "Content",
    description:
      "Writes blog posts, documentation, newsletters, and social content in your brand voice.",
    color: "#8b5cf6",
  },
  {
    id: "support",
    name: "Support",
    description:
      "Resolves customer issues, escalates edge cases, and keeps your knowledge base up to date.",
    color: "#f59e0b",
  },
  {
    id: "engineering",
    name: "Engineering",
    description:
      "Reviews code, documents architecture decisions, and tracks technical debt across repos.",
    color: "#3b82f6",
  },
  {
    id: "hr",
    name: "HR",
    description:
      "Manages onboarding, tracks employee requests, and keeps your team handbook and policies up to date.",
    color: "#10b981",
  },
];

export async function fetchTemplates(): Promise<Agent[]> {
  return templates;
}
