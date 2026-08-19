"use client";

import { useCallback, useRef, useState } from "react";
import { UploadIcon, XIcon, FileTextIcon } from "lucide-react";
import { useDocumentsUploadDocument } from "@repo/api-client";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";

interface UploadingFile {
  file: File;
  status: "pending" | "uploading" | "done" | "error";
  error?: string;
}

interface Props {
  orgId: string;
  onComplete: () => void;
  onSkip: () => void;
}

const ALLOWED_TYPES = [
  ".pdf",
  ".md",
  ".txt",
  ".csv",
  ".json",
  ".html",
  ".docx",
  ".pptx",
  ".xlsx",
  ".doc",
  ".ppt",
  ".xls",
  ".odt",
  ".rtf",
];
const MAX_SIZE_MB = 10;

function fileKey(f: File): string {
  return `${f.name}-${f.size}-${f.lastModified}`;
}

export function KnowledgeUpload({ orgId, onComplete, onSkip }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [files, setFiles] = useState<UploadingFile[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const [hasErrors, setHasErrors] = useState(false);
  const uploadMutation = useDocumentsUploadDocument();

  const addFiles = useCallback((newFiles: FileList | null) => {
    if (!newFiles) return;
    const valid: UploadingFile[] = [];
    for (const f of newFiles) {
      const ext = "." + f.name.split(".").pop()?.toLowerCase();
      if (!ALLOWED_TYPES.includes(ext)) continue;
      if (f.size > MAX_SIZE_MB * 1024 * 1024) continue;
      valid.push({ file: f, status: "pending" });
    }
    setFiles((prev) => [...prev, ...valid]);
  }, []);

  const removeFile = useCallback((index: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== index));
  }, []);

  const handleUpload = useCallback(async () => {
    setIsUploading(true);
    setHasErrors(false);
    let anyFailed = false;
    for (let i = 0; i < files.length; i++) {
      const entry = files[i];
      if (!entry) continue;
      if (entry.status === "done") continue;
      setFiles((prev) =>
        prev.map((f, idx) => (idx === i ? { ...f, status: "uploading" } : f)),
      );
      try {
        await uploadMutation.mutateAsync({
          data: {
            // orval generates `file` as `string` for binary fields; FormData.append
            // accepts File/Blob at runtime so the cast is safe.
            file: entry.file as unknown as string,
            organization_id: orgId,
          },
        });
        setFiles((prev) =>
          prev.map((f, idx) => (idx === i ? { ...f, status: "done" } : f)),
        );
      } catch {
        anyFailed = true;
        setFiles((prev) =>
          prev.map((f, idx) =>
            idx === i ? { ...f, status: "error", error: "Upload failed" } : f,
          ),
        );
      }
    }
    setIsUploading(false);
    if (!anyFailed) {
      onComplete();
    } else {
      setHasErrors(true);
    }
  }, [files, orgId, uploadMutation, onComplete]);

  const pendingCount = files.filter(
    (f) => f.status !== "done" && f.status !== "error",
  ).length;
  const errorCount = files.filter((f) => f.status === "error").length;

  return (
    <div className="space-y-4">
      <div
        onClick={() => inputRef.current?.click()}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") inputRef.current?.click();
        }}
        role="button"
        tabIndex={0}
        className="flex cursor-pointer flex-col items-center gap-2 rounded-xl border-2 border-dashed border-border p-8 text-center transition-colors hover:border-primary/40"
      >
        <UploadIcon className="size-8 text-muted-foreground/60" />
        <p className="text-sm font-medium text-foreground">
          Click to upload documents to your knowledge base
        </p>
        <p className="text-xs text-muted-foreground">
          PDF, Word, Excel, Markdown, text &middot; max {MAX_SIZE_MB}MB each
        </p>
        <input
          ref={inputRef}
          type="file"
          accept={ALLOWED_TYPES.join(",")}
          multiple
          className="hidden"
          onChange={(e) => addFiles(e.target.files)}
        />
      </div>

      {files.length > 0 && (
        <div className="space-y-2">
          {files.map((entry, i) => (
            <div
              key={fileKey(entry.file)}
              className="flex items-center gap-3 rounded-lg border border-border px-3 py-2.5"
            >
              <FileTextIcon className="size-4 shrink-0 text-muted-foreground" />
              <span className="min-w-0 flex-1 truncate text-sm">
                {entry.file.name}
              </span>
              {entry.status === "uploading" && <Spinner className="size-4" />}
              {entry.status === "done" && (
                <span className="text-xs text-emerald-600">Uploaded</span>
              )}
              {entry.status === "error" && (
                <span className="text-xs text-destructive">
                  {entry.error ?? "Error"}
                </span>
              )}
              {entry.status !== "uploading" && entry.status !== "done" && (
                <button
                  type="button"
                  onClick={() => removeFile(i)}
                  className="text-muted-foreground hover:text-foreground"
                  aria-label={`Remove ${entry.file.name}`}
                >
                  <XIcon className="size-4" />
                </button>
              )}
            </div>
          ))}
        </div>
      )}

      {hasErrors && (
        <p className="text-sm text-destructive">
          {errorCount} file{errorCount !== 1 ? "s" : ""} failed to upload. You
          can remove them and try again, or continue.
        </p>
      )}

      <div className="flex items-center justify-end gap-3">
        <Button variant="outline" onClick={onSkip} disabled={isUploading}>
          Skip
        </Button>
        {hasErrors ? (
          <Button onClick={onComplete} variant="secondary">
            Continue anyway
          </Button>
        ) : (
          <Button
            onClick={handleUpload}
            disabled={pendingCount === 0 || isUploading}
          >
            {isUploading ? "Uploading…" : "Upload & finish"}
          </Button>
        )}
      </div>
    </div>
  );
}
