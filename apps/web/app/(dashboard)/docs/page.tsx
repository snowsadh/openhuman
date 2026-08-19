import fs from "fs";
import path from "path";
import { DocsReader } from "./docs-reader";

interface DocFile {
  slug: string;
  title: string;
  content: string;
  order: number;
}

const DOC_ORDER: Record<string, number> = {
  "readme": 0,
  "overview": 1,
  "backend": 2,
  "frontend": 3,
  "agent_engine": 4,
  "memory_system": 5,
  "mcp_integration": 6,
  "bot_gateway": 7,
  "devops_deployment": 8,
};

function getDocTitle(slug: string, content: string): string {
  // Try to find the first H1 in the content
  const h1Match = content.match(/^#\s+(.+)$/m);
  if (h1Match && h1Match[1]) {
    return h1Match[1].trim();
  }

  // Fallback to slug-based formatting
  return slug
    .split(/[-_]/)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

export default async function DocsPage() {
  const docsDir = path.join(process.cwd(), "../../docs/documentation");
  let docs: DocFile[] = [];

  try {
    if (fs.existsSync(docsDir)) {
      const files = fs.readdirSync(docsDir);
      docs = files
        .filter((file) => file.endsWith(".md"))
        .map((file) => {
          const slug = file.replace(/\.md$/, "");
          const filePath = path.join(docsDir, file);
          const content = fs.readFileSync(filePath, "utf-8");
          const title = getDocTitle(slug, content);
          const order = DOC_ORDER[slug.toLowerCase()] ?? 99;
          return { slug, title, content, order };
        })
        .sort((a, b) => a.order - b.order);
    }
  } catch (error) {
    console.error("Failed to load documentation files", error);
  }

  return (
    <div className="flex-1 flex flex-col h-[calc(100vh-4rem)] overflow-hidden">
      <DocsReader docs={docs} />
    </div>
  );
}
