"use client";

import React, { useState, useMemo, createContext, useContext } from "react";
import Link from "next/link";
import { motion, AnimatePresence } from "framer-motion";
import {
  BookOpen,
  ChevronLeft,
  Copy,
  Check,
  Search,
  Clock,
  ExternalLink,
  Info,
  AlertTriangle,
  Flame,
  Lightbulb,
  ShieldAlert,
  Menu,
} from "lucide-react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Sheet, SheetContent, SheetTrigger } from "@/components/ui/sheet";

// Create context for navigation within document links
const DocsNavigationContext = createContext<{
  activeSlug: string;
  setActiveSlug: (slug: string) => void;
}>({
  activeSlug: "",
  setActiveSlug: () => {},
});

interface DocFile {
  slug: string;
  title: string;
  content: string;
  order: number;
}

interface DocsReaderProps {
  docs: DocFile[];
}

// Custom code block renderer with copy button
function CodeBlock({ code, language }: { code: string; language: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  // Simple, elegant code highlighter for presentation
  const highlightedCode = useMemo(() => {
    const lines = code.split("\n");
    return lines.map((line, idx) => {
      // Highlight comments
      if (line.trim().startsWith("#") || line.trim().startsWith("//")) {
        return (
          <span key={idx} className="text-zinc-500 italic block">
            {line}
          </span>
        );
      }
      
      // Basic highlighting for keywords, strings, etc.
      let words = line.split(/(\s+|\(|\)|\{|\}|\[|\]|\.|\,|;|:|\"|\')/);
      const keywords = new Set([
        "def", "class", "import", "from", "return", "async", "await", "function",
        "const", "let", "if", "else", "try", "except", "export", "default",
        "select", "where", "insert", "update", "delete", "as", "with", "for", "in"
      ]);

      const formattedLine = words.map((word, wIdx) => {
        if (keywords.has(word)) {
          return (
            <span key={wIdx} className="text-blue-400 font-medium">
              {word}
            </span>
          );
        }
        if (word.startsWith('"') || word.startsWith("'") || word.endsWith('"') || word.endsWith("'")) {
          return (
            <span key={wIdx} className="text-emerald-400">
              {word}
            </span>
          );
        }
        if (/^\d+$/.test(word)) {
          return (
            <span key={wIdx} className="text-amber-400">
              {word}
            </span>
          );
        }
        return word;
      });

      return (
        <span key={idx} className="block min-h-[1rem]">
          {formattedLine}
        </span>
      );
    });
  }, [code]);

  return (
    <Card className="my-6 border border-border bg-zinc-950 overflow-hidden font-mono text-sm leading-relaxed">
      <div className="flex items-center justify-between px-4 py-2 bg-zinc-900 border-b border-zinc-800">
        <span className="text-xs text-zinc-400 uppercase tracking-wider">{language || "text"}</span>
        <Button
          variant="ghost"
          size="icon"
          className="h-7 w-7 text-zinc-400 hover:text-zinc-205 hover:bg-zinc-800"
          onClick={handleCopy}
        >
          {copied ? <Check className="h-4.5 w-4.5 text-emerald-400" /> : <Copy className="h-4.5 w-4.5" />}
        </Button>
      </div>
      <ScrollArea className="max-h-[500px]">
        <pre className="p-4 overflow-x-auto text-zinc-100 selection:bg-zinc-800">
          <code>{highlightedCode}</code>
        </pre>
      </ScrollArea>
    </Card>
  );
}

// GitHub alert block renderer (theme adaptive)
function AlertBlock({ type, content }: { type: string; content: string }) {
  const alertStyles = {
    NOTE: {
      border: "border-l-4 border-blue-500",
      bg: "bg-blue-500/10",
      text: "text-blue-600 dark:text-blue-400",
      icon: Info,
      title: "Note",
    },
    TIP: {
      border: "border-l-4 border-emerald-500",
      bg: "bg-emerald-500/10",
      text: "text-emerald-600 dark:text-emerald-400",
      icon: Lightbulb,
      title: "Tip",
    },
    IMPORTANT: {
      border: "border-l-4 border-indigo-500",
      bg: "bg-indigo-500/10",
      text: "text-indigo-600 dark:text-indigo-400",
      icon: Flame,
      title: "Important",
    },
    WARNING: {
      border: "border-l-4 border-amber-500",
      bg: "bg-amber-500/10",
      text: "text-amber-600 dark:text-amber-450",
      icon: AlertTriangle,
      title: "Warning",
    },
    CAUTION: {
      border: "border-l-4 border-rose-500",
      bg: "bg-rose-500/10",
      text: "text-rose-600 dark:text-rose-450",
      icon: ShieldAlert,
      title: "Caution",
    },
  };

  const style = alertStyles[type as keyof typeof alertStyles] || alertStyles.NOTE;
  const Icon = style.icon;

  return (
    <div className={`my-5 p-4 rounded-r-lg border-y border-r border-border ${style.border} ${style.bg} flex gap-3.5`}>
      <Icon className={`h-5 w-5 ${style.text} shrink-0 mt-0.5`} />
      <div className="flex-1 text-sm text-foreground/90 leading-relaxed">
        <div className={`font-semibold mb-1 ${style.text}`}>{style.title}</div>
        <div>{content}</div>
      </div>
    </div>
  );
}

// Internal Doc Links handler
function LocalDocLink({ slug, text }: { slug: string; text: string }) {
  const { setActiveSlug } = useContext(DocsNavigationContext);
  return (
    <button
      onClick={() => setActiveSlug(slug)}
      className="text-indigo-600 dark:text-indigo-400 hover:underline underline-offset-4 font-medium transition"
    >
      {text}
    </button>
  );
}

// Parse inline markdown elements (bold, code, links)
function parseInlineElements(text: string): React.ReactNode {
  if (!text) return "";
  const parts: React.ReactNode[] = [];
  let currentText = text;

  while (currentText.length > 0) {
    const boldIndex = currentText.indexOf("**");
    const codeIndex = currentText.indexOf("`");
    const linkMatch = currentText.match(/\[([^\]]+)\]\(([^)]+)\)/);
    const linkIndex = linkMatch ? currentText.indexOf(linkMatch[0]) : -1;

    const indices = [
      { type: "bold", index: boldIndex },
      { type: "code", index: codeIndex },
      { type: "link", index: linkIndex },
    ]
      .filter((x) => x.index !== -1)
      .sort((a, b) => a.index - b.index);

    if (indices.length === 0) {
      parts.push(currentText);
      break;
    }

    const nextToken = indices[0]!;

    if (nextToken.index > 0) {
      parts.push(currentText.substring(0, nextToken.index));
    }

    if (nextToken.type === "bold") {
      const endBold = currentText.indexOf("**", nextToken.index + 2);
      if (endBold !== -1) {
        const boldText = currentText.substring(nextToken.index + 2, endBold);
        parts.push(
          <strong key={nextToken.index} className="font-semibold text-foreground">
            {boldText}
          </strong>
        );
        currentText = currentText.substring(endBold + 2);
      } else {
        parts.push("**");
        currentText = currentText.substring(nextToken.index + 2);
      }
    } else if (nextToken.type === "code") {
      const endCode = currentText.indexOf("`", nextToken.index + 1);
      if (endCode !== -1) {
        const codeText = currentText.substring(nextToken.index + 1, endCode);
        parts.push(
          <code
            key={nextToken.index}
            className="px-1.5 py-0.5 rounded bg-muted text-foreground/90 font-mono text-xs border border-border/60"
          >
            {codeText}
          </code>
        );
        currentText = currentText.substring(endCode + 1);
      } else {
        parts.push("`");
        currentText = currentText.substring(nextToken.index + 1);
      }
    } else if (nextToken.type === "link" && linkMatch) {
      const linkText = linkMatch[1]!;
      const linkUrl = linkMatch[2]!;
      const isLocalMd =
        linkUrl.endsWith(".md") &&
        !linkUrl.startsWith("http") &&
        !linkUrl.startsWith("file://");

      parts.push(
        isLocalMd ? (
          <LocalDocLink
            key={nextToken.index}
            slug={linkUrl.replace(/\.md$/, "")}
            text={linkText}
          />
        ) : (
          <a
            key={nextToken.index}
            href={linkUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="text-indigo-600 dark:text-indigo-400 hover:text-indigo-500 hover:underline underline-offset-4 inline-flex items-center gap-0.5"
          >
            {linkText} <ExternalLink className="h-3 w-3 shrink-0" />
          </a>
        )
      );
      currentText = currentText.substring(
        nextToken.index + linkMatch[0].length
      );
    }
  }

  return React.createElement(React.Fragment, {}, ...parts);
}

// Convert markdown structure to React elements
function parseMarkdownToReact(content: string): React.ReactNode[] {
  const lines = content.split("\n");
  const elements: React.ReactNode[] = [];
  
  let idx = 0;
  while (idx < lines.length) {
    const line = lines[idx];
    if (line === undefined) break;

    const trimmed = line.trim();

    // 1. Skip Empty Lines
    if (!trimmed) {
      idx++;
      continue;
    }

    // 2. Code Blocks
    if (trimmed.startsWith("```")) {
      const language = trimmed.slice(3).trim();
      const codeLines: string[] = [];
      idx++;
      while (idx < lines.length) {
        const nextLine = lines[idx];
        if (nextLine === undefined) break;
        if (nextLine.trim().startsWith("```")) {
          idx++;
          break;
        }
        codeLines.push(nextLine);
        idx++;
      }
      elements.push(
        <CodeBlock
          key={idx}
          code={codeLines.join("\n")}
          language={language}
        />
      );
      continue;
    }

    // 3. GitHub style alerts & Quotes
    if (trimmed.startsWith(">")) {
      // Accumulate quote block
      const quoteLines: string[] = [];
      while (idx < lines.length) {
        const nextLine = lines[idx];
        if (nextLine === undefined) break;
        const nextTrimmed = nextLine.trim();
        if (!nextTrimmed.startsWith(">")) {
          break;
        }
        // Extract content after >
        quoteLines.push(nextTrimmed.slice(1).trim());
        idx++;
      }

      if (quoteLines.length > 0) {
        const first = quoteLines[0] || "";
        const alertMatch = first.match(/^\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]$/i);
        if (alertMatch && alertMatch[1]) {
          const type = alertMatch[1].toUpperCase();
          const alertContent = quoteLines.slice(1).join(" ");
          elements.push(<AlertBlock key={idx} type={type} content={alertContent} />);
        } else {
          elements.push(
            <blockquote
              key={idx}
              className="my-4 border-l-4 border-muted pl-4 italic text-muted-foreground text-sm leading-relaxed"
            >
              {quoteLines.map((l, i) => (
                <p key={i}>{parseInlineElements(l)}</p>
              ))}
            </blockquote>
          );
        }
      }
      continue;
    }

    // 4. Headings
    if (trimmed.startsWith("#")) {
      const depth = trimmed.match(/^#+/)?.[0].length || 1;
      const text = trimmed.replace(/^#+\s+/, "");
      
      // Skip top H1 titles if they duplicate page main title
      if (depth === 1) {
        idx++;
        continue;
      }
      
      const parsedText = parseInlineElements(text);
      if (depth === 2) {
        elements.push(
          <h2
            key={idx}
            className="text-xl font-semibold text-foreground mt-8 mb-4 border-b border-border pb-1.5 scroll-m-20"
          >
            {parsedText}
          </h2>
        );
      } else if (depth === 3) {
        elements.push(
          <h3 key={idx} className="text-lg font-medium text-foreground mt-6 mb-3 scroll-m-20">
            {parsedText}
          </h3>
        );
      } else {
        elements.push(
          <h4 key={idx} className="text-base font-medium text-foreground/95 mt-4 mb-2 scroll-m-20">
            {parsedText}
          </h4>
        );
      }
      idx++;
      continue;
    }

    // 5. Horizontal rules
    if (trimmed === "---" || trimmed === "***") {
      elements.push(<Separator key={idx} className="my-6 border-border" />);
      idx++;
      continue;
    }

    // 6. Tables
    if (trimmed.startsWith("|")) {
      const tableLines: string[] = [];
      while (idx < lines.length) {
        const nextLine = lines[idx];
        if (nextLine === undefined) break;
        const nextTrimmed = nextLine.trim();
        if (!nextTrimmed.startsWith("|")) {
          break;
        }
        tableLines.push(nextTrimmed);
        idx++;
      }

      if (tableLines.length >= 2) {
        // Parse headers
        const headerCols = (tableLines[0] || "")
          .split("|")
          .map((x) => x.trim())
          .filter((_, i, arr) => i > 0 && i < arr.length - 1);
        
        // Skip divider rows (second line: e.g. |---|)
        const rowLines = tableLines.slice(2);
        const rows = rowLines.map((row) =>
          row
            .split("|")
            .map((x) => x.trim())
            .filter((_, i, arr) => i > 0 && i < arr.length - 1)
        );

        elements.push(
          <div key={idx} className="my-6 overflow-x-auto border border-border rounded-lg bg-card">
            <table className="w-full border-collapse text-sm text-left">
              <thead className="bg-muted/60 border-b border-border text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                <tr>
                  {headerCols.map((h, i) => (
                    <th key={i} className="px-4 py-3 font-semibold">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-border text-foreground/90">
                {rows.map((row, rIdx) => (
                  <tr key={rIdx} className="hover:bg-muted/30 transition-colors">
                    {row.map((cell, cIdx) => (
                      <td key={cIdx} className="px-4 py-3 font-mono text-xs">
                        {parseInlineElements(cell)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        );
      }
      continue;
    }

    // 7. Lists
    if (trimmed.startsWith("* ") || trimmed.startsWith("- ") || /^\d+\.\s+/.test(trimmed)) {
      const listLines: { text: string; isOrdered: boolean }[] = [];
      
      while (idx < lines.length) {
        const nextLine = lines[idx];
        if (nextLine === undefined) break;
        const nextTrimmed = nextLine.trim();
        
        const isUnordered = nextTrimmed.startsWith("* ") || nextTrimmed.startsWith("- ");
        const isOrdered = /^\d+\.\s+/.test(nextTrimmed);
        
        if (!isUnordered && !isOrdered) {
          break;
        }

        const listContent = nextTrimmed.replace(/^(\*\s+|\-\s+|\d+\.\s+)/, "");
        listLines.push({ text: listContent, isOrdered });
        idx++;
      }

      const isOrderedList = listLines[0]?.isOrdered || false;

      elements.push(
        isOrderedList ? (
          <ol key={idx} className="my-4 pl-6 list-decimal space-y-2 text-foreground/90 text-sm leading-relaxed">
            {listLines.map((item, i) => (
              <li key={i}>{parseInlineElements(item.text)}</li>
            ))}
          </ol>
        ) : (
          <ul key={idx} className="my-4 pl-6 list-disc space-y-2 text-foreground/90 text-sm leading-relaxed">
            {listLines.map((item, i) => (
              <li key={i}>{parseInlineElements(item.text)}</li>
            ))}
          </ul>
        )
      );
      continue;
    }

    // 8. Normal Paragraph
    elements.push(
      <p key={idx} className="my-4 text-foreground/90 text-sm leading-relaxed antialiased">
        {parseInlineElements(trimmed)}
      </p>
    );
    idx++;
  }

  return elements;
}

export function DocsReader({ docs }: DocsReaderProps) {
  const [activeSlug, setActiveSlug] = useState(docs[0]?.slug || "readme");
  const [searchTerm, setSearchTerm] = useState("");
  const [isMobileOpen, setIsMobileOpen] = useState(false);

  // Search filter across documents titles and contents
  const filteredDocs = useMemo(() => {
    return docs.filter((doc) => {
      const term = searchTerm.toLowerCase();
      return (
        doc.title.toLowerCase().includes(term) ||
        doc.content.toLowerCase().includes(term)
      );
    });
  }, [docs, searchTerm]);

  // Resolve current active doc
  const currentDoc = useMemo(() => {
    return docs.find((doc) => doc.slug === activeSlug) || docs[0];
  }, [docs, activeSlug]);

  // Calculate reading time based on average 200 WPM
  const readingTime = useMemo(() => {
    if (!currentDoc) return 0;
    const words = currentDoc.content.trim().split(/\s+/).length;
    return Math.ceil(words / 200);
  }, [currentDoc]);

  // Render markdown blocks
  const renderedContent = useMemo(() => {
    if (!currentDoc) return null;
    return parseMarkdownToReact(currentDoc.content);
  }, [currentDoc]);

  // Value for navigation context provider
  const navContextValue = useMemo(
    () => ({ activeSlug, setActiveSlug }),
    [activeSlug, setActiveSlug]
  );

  return (
    <DocsNavigationContext.Provider value={navContextValue}>
      <div className="flex-1 flex overflow-hidden border-t border-border/40">
        
        {/* Left Sidebar Layout - Desktop */}
        <aside className="w-68 border-r border-border bg-card/60 backdrop-blur-md hidden md:flex flex-col shrink-0">
          <div className="p-4 border-b border-border">
            <Link
              href="/dashboard"
              className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition mb-3"
            >
              <ChevronLeft className="h-3.5 w-3.5" /> Back to Dashboard
            </Link>
            <div className="relative">
              <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="Search repository docs..."
                className="pl-8.5 h-9 bg-background border-border text-xs focus-visible:ring-1 focus-visible:ring-ring"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
              />
            </div>
          </div>

          <ScrollArea className="flex-1 py-3 px-2">
            <div className="space-y-0.5">
              {filteredDocs.map((doc) => {
                const isActive = doc.slug === activeSlug;
                return (
                  <button
                    key={doc.slug}
                    onClick={() => setActiveSlug(doc.slug)}
                    className={`w-full text-left px-3 py-2 rounded-md text-xs font-medium transition-all relative flex items-center gap-2 ${
                      isActive
                        ? "bg-accent text-accent-foreground border-l-2 border-primary rounded-l-none"
                        : "text-muted-foreground hover:text-foreground hover:bg-accent/50"
                    }`}
                  >
                    <BookOpen className="h-3.5 w-3.5 shrink-0" />
                    <span className="truncate">{doc.title}</span>
                  </button>
                );
              })}
              {filteredDocs.length === 0 && (
                <div className="text-center py-8 text-xs text-muted-foreground">
                  No matching files found.
                </div>
              )}
            </div>
          </ScrollArea>
        </aside>

        {/* Mobile Navigation Sheet */}
        <Sheet open={isMobileOpen} onOpenChange={setIsMobileOpen}>
          <SheetContent side="left" className="w-68 bg-card border-r border-border p-0 flex flex-col">
            <div className="p-4 border-b border-border">
              <div className="relative">
                <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                <Input
                  placeholder="Search docs..."
                  className="pl-8.5 h-9 bg-background border-border text-xs"
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                />
              </div>
            </div>
            <ScrollArea className="flex-1 py-3 px-2">
              <div className="space-y-0.5">
                {filteredDocs.map((doc) => {
                  const isActive = doc.slug === activeSlug;
                  return (
                    <button
                      key={doc.slug}
                      onClick={() => {
                        setActiveSlug(doc.slug);
                        setIsMobileOpen(false);
                      }}
                      className={`w-full text-left px-3 py-2 rounded-md text-xs font-medium transition-all relative flex items-center gap-2 ${
                        isActive
                          ? "bg-accent text-accent-foreground border-l-2 border-primary rounded-l-none"
                          : "text-muted-foreground hover:text-foreground hover:bg-accent/50"
                      }`}
                    >
                      <BookOpen className="h-3.5 w-3.5 shrink-0" />
                      <span className="truncate">{doc.title}</span>
                    </button>
                  );
                })}
              </div>
            </ScrollArea>
          </SheetContent>
        </Sheet>

        {/* Main Content Reader Panel */}
        <main className="flex-1 bg-background-app flex flex-col min-w-0">
          {/* Header Bar */}
          <header className="h-12 border-b border-border px-6 flex items-center justify-between shrink-0 bg-card/20 backdrop-blur-md">
            <div className="flex items-center gap-3">
              <Button
                variant="ghost"
                size="icon"
                className="md:hidden h-8 w-8 text-muted-foreground"
                onClick={() => setIsMobileOpen(true)}
              >
                <Menu className="h-4.5 w-4.5" />
              </Button>
              <h1 className="text-sm font-semibold text-foreground truncate">
                {currentDoc?.title || "Documentation"}
              </h1>
            </div>
            
            {currentDoc && (
              <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                <Clock className="h-3.5 w-3.5" />
                <span>{readingTime} min read</span>
              </div>
            )}
          </header>

          {/* Reading Scroll Container */}
          <ScrollArea className="flex-1">
            <div className="max-w-3xl mx-auto px-6 py-8 md:py-12">
              <AnimatePresence mode="wait">
                <motion.div
                  key={activeSlug}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -8 }}
                  transition={{ duration: 0.18 }}
                  className="max-w-none text-foreground"
                >
                  {/* Styled H1 Title */}
                  <div className="mb-6">
                    <h1 className="text-2xl md:text-3xl font-bold tracking-tight text-foreground">
                      {currentDoc?.title}
                    </h1>
                    <div className="h-1 w-12 bg-primary rounded mt-4" />
                  </div>

                  {/* Rendered Elements List */}
                  <div className="mt-8 pb-16">{renderedContent}</div>
                </motion.div>
              </AnimatePresence>
            </div>
          </ScrollArea>
        </main>
      </div>
    </DocsNavigationContext.Provider>
  );
}
