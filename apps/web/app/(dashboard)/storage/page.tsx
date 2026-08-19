"use client";

import { useCallback, useMemo, useRef, useState } from "react";
import {
  DownloadIcon,
  FileTextIcon,
  HardDriveIcon,
  SearchIcon,
  Trash2Icon,
  UploadIcon,
  UserIcon,
  Building2Icon,
  XIcon,
} from "lucide-react";
import { format } from "date-fns";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  useDocumentsListOrgDocuments,
  useDocumentsUploadDocument,
  useDocumentsDeleteDocumentRoute,
  useDocumentsGetOrgDocumentsStats,
  useEmployeesListEmployeesRoute,
  getDocumentsListOrgDocumentsQueryKey,
  getDocumentsGetOrgDocumentsStatsQueryKey,
} from "@repo/api-client";
import type { DocumentResponse } from "@repo/api-client";
import { useOrgStore } from "@/stores/org";
import { Spinner } from "@/components/ui/spinner";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function formatSize(bytes: number | null | undefined): string {
  if (bytes == null) return "—";
  if (bytes === 0) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const i = Math.min(
    Math.floor(Math.log(bytes) / Math.log(1024)),
    units.length - 1,
  );
  const size = bytes / 1024 ** i;
  return `${size.toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

async function downloadDocument(docId: string, filename: string, token: string | null) {
  const response = await fetch(`${API_URL}/api/documents/${docId}/download`, {
    headers: { Authorization: `Bearer ${token}` },
  });

  if (!response.ok) {
    throw new Error("Download failed");
  }

  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function DocumentTable({
  documents,
  downloadingId,
  onDownload,
  onDelete,
  employeeMap,
  showAgentColumn = false,
}: {
  documents: DocumentResponse[];
  downloadingId: string | null;
  onDownload: (id: string, filename: string) => void;
  onDelete: (id: string) => void;
  employeeMap: Map<string, string>;
  showAgentColumn?: boolean;
}) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead className="w-[40%]">File</TableHead>
          <TableHead className="hidden sm:table-cell">Type</TableHead>
          <TableHead className="hidden md:table-cell">Size</TableHead>
          {showAgentColumn && <TableHead>Agent</TableHead>}
          <TableHead className="hidden lg:table-cell">Uploaded</TableHead>
          <TableHead>Status</TableHead>
          <TableHead className="text-right">Actions</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {documents.map((doc) => (
          <TableRow key={doc.id}>
            <TableCell className="max-w-48">
              <div className="flex items-center gap-2">
                <FileTextIcon className="size-4 shrink-0 text-muted-foreground" />
                <span className="truncate text-sm" title={doc.filename}>
                  {doc.filename}
                </span>
              </div>
            </TableCell>
            <TableCell className="hidden text-xs text-muted-foreground sm:table-cell">
              {doc.content_type?.split("/")[1] ?? "—"}
            </TableCell>
            <TableCell className="hidden text-xs text-muted-foreground md:table-cell">
              {formatSize(doc.size_bytes)}
            </TableCell>
            {showAgentColumn && (
              <TableCell className="text-xs">
                {doc.employee_id
                  ? (employeeMap.get(doc.employee_id) ?? "Unknown")
                  : "—"}
              </TableCell>
            )}
            <TableCell className="hidden text-xs text-muted-foreground lg:table-cell">
              {format(new Date(doc.uploaded_at), "MMM d, yyyy")}
            </TableCell>
            <TableCell>
              <Badge variant="secondary" className="text-xs">
                {doc.status}
              </Badge>
            </TableCell>
            <TableCell className="text-right">
              <div className="flex items-center justify-end gap-1">
                <button
                  type="button"
                  onClick={() => onDownload(doc.id, doc.filename)}
                  disabled={downloadingId === doc.id}
                  className="rounded p-1.5 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
                  aria-label={`Download ${doc.filename}`}
                >
                  {downloadingId === doc.id ? (
                    <Spinner className="size-3.5" />
                  ) : (
                    <DownloadIcon className="size-3.5" />
                  )}
                </button>
                <button
                  type="button"
                  onClick={() => onDelete(doc.id)}
                  className="rounded p-1.5 text-muted-foreground transition-colors hover:bg-accent hover:text-destructive"
                  aria-label={`Delete ${doc.filename}`}
                >
                  <Trash2Icon className="size-3.5" />
                </button>
              </div>
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

export default function StoragePage() {
  const orgId = useOrgStore((s) => s.orgId);
  const getToken = useCallback(async () => {
    if (typeof window === "undefined") return null;
    return localStorage.getItem("oh_token");
  }, []);
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const uploadDocMutation = useDocumentsUploadDocument();
  const deleteDocMutation = useDocumentsDeleteDocumentRoute();

  const [isUploading, setIsUploading] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [deletingDocId, setDeletingDocId] = useState<string | null>(null);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [downloadingId, setDownloadingId] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [activeTab, setActiveTab] = useState("all");

  const { data: allDocuments, isLoading: docsLoading } =
    useDocumentsListOrgDocuments(
      { organization_id: orgId! },
      { query: { enabled: !!orgId } },
    );

  const { data: employees } = useEmployeesListEmployeesRoute(orgId ?? "", {
    query: { enabled: !!orgId },
  });

  const { data: stats, isLoading: statsLoading } = useDocumentsGetOrgDocumentsStats(
    { organization_id: orgId! },
    { query: { enabled: !!orgId } },
  );

  const employeeMap = useMemo(() => {
    const map = new Map<string, string>();
    if (employees) {
      for (const emp of employees) {
        map.set(emp.id, emp.name);
      }
    }
    return map;
  }, [employees]);

  const filteredDocuments = useMemo(() => {
    if (!allDocuments) return [];
    if (!searchQuery.trim()) return allDocuments;
    const q = searchQuery.toLowerCase();
    return allDocuments.filter((doc) => doc.filename.toLowerCase().includes(q));
  }, [allDocuments, searchQuery]);

  const orgDocuments = useMemo(
    () => filteredDocuments.filter((doc) => !doc.employee_id),
    [filteredDocuments],
  );

  const agentDocuments = useMemo(
    () => filteredDocuments.filter((doc) => doc.employee_id),
    [filteredDocuments],
  );

  const agentGroups = useMemo(() => {
    const groups = new Map<string, DocumentResponse[]>();
    for (const doc of agentDocuments) {
      const empId = doc.employee_id!;
      if (!groups.has(empId)) groups.set(empId, []);
      groups.get(empId)!.push(doc);
    }
    return Array.from(groups.entries()).sort(([, docsA], [, docsB]) => {
      const empIdA = docsA[0]?.employee_id ?? "";
      const empIdB = docsB[0]?.employee_id ?? "";
      const nameA = employeeMap.get(empIdA) ?? "Unknown";
      const nameB = employeeMap.get(empIdB) ?? "Unknown";
      return nameA.localeCompare(nameB);
    });
  }, [agentDocuments, employeeMap]);

  const invalidateDocs = useCallback(() => {
    if (!orgId) return;
    queryClient.invalidateQueries({
      queryKey: getDocumentsListOrgDocumentsQueryKey({
        organization_id: orgId,
      }),
    });
    queryClient.invalidateQueries({
      queryKey: getDocumentsGetOrgDocumentsStatsQueryKey({
        organization_id: orgId,
      }),
    });
  }, [orgId, queryClient]);

  const uploadFiles = useCallback(
    async (fileList: FileList | File[]) => {
      if (!orgId) return;
      setIsUploading(true);

      for (const file of Array.from(fileList)) {
        try {
          await uploadDocMutation.mutateAsync({
            data: {
              file: file as unknown as string,
              organization_id: orgId,
            },
          });
        } catch {
          toast.error(`Failed to upload ${file.name}`);
        }
      }

      invalidateDocs();
      setIsUploading(false);
    },
    [orgId, uploadDocMutation, invalidateDocs],
  );

  const handleFileChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      if (e.target.files && e.target.files.length > 0) {
        uploadFiles(e.target.files);
        e.target.value = "";
      }
    },
    [uploadFiles],
  );

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragging(false);
      if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
        uploadFiles(e.dataTransfer.files);
      }
    },
    [uploadFiles],
  );

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  }, []);

  const handleDelete = useCallback(async () => {
    if (!deletingDocId) return;
    try {
      await deleteDocMutation.mutateAsync({ docId: deletingDocId });
      toast.success("Document deleted");
      invalidateDocs();
    } catch {
      toast.error("Failed to delete document");
    } finally {
      setDeleteDialogOpen(false);
      setDeletingDocId(null);
    }
  }, [deleteDocMutation, deletingDocId, invalidateDocs]);

  const handleDownload = useCallback(
    async (docId: string, filename: string) => {
      setDownloadingId(docId);
      try {
        const token = await getToken();
        if (!token) {
          toast.error("Session expired. Please sign in again.");
          return;
        }
        await downloadDocument(docId, filename, token);
      } catch {
        toast.error("Failed to download file");
      } finally {
        setDownloadingId(null);
      }
    },
    [getToken],
  );

  const hasDocuments = allDocuments && allDocuments.length > 0;
  const allLoading = docsLoading || statsLoading;

  return (
    <div className="flex flex-col gap-6 px-6 py-6">
      {/* Header */}
      <div className="flex items-center gap-2.5">
        <HardDriveIcon className="size-5 text-muted-foreground" />
        <h1 className="text-lg font-semibold tracking-tight text-foreground">
          Storage
        </h1>
      </div>

      {/* Stat cards */}
      {!statsLoading && stats && (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <Card size="sm">
            <CardHeader className="py-2">
              <CardTitle className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
                Total Files
              </CardTitle>
            </CardHeader>
            <CardContent className="pb-2">
              <span className="text-2xl font-bold">{stats.total_files}</span>
            </CardContent>
          </Card>

          <Card size="sm">
            <CardHeader className="py-2">
              <CardTitle className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
                Total Size
              </CardTitle>
            </CardHeader>
            <CardContent className="pb-2">
              <span className="text-2xl font-bold">
                {formatSize(stats.total_size_bytes)}
              </span>
            </CardContent>
          </Card>

          <Card size="sm">
            <CardHeader className="py-2">
              <CardTitle className="flex items-center gap-1.5 text-xs font-medium uppercase tracking-wider text-muted-foreground">
                <Building2Icon className="size-3" />
                Org KB
              </CardTitle>
            </CardHeader>
            <CardContent className="pb-2">
              <span className="text-2xl font-bold">
                {stats.org_files_count}
              </span>
              <span className="ml-1.5 text-sm text-muted-foreground">
                / {formatSize(stats.org_size_bytes)}
              </span>
            </CardContent>
          </Card>

          <Card size="sm">
            <CardHeader className="py-2">
              <CardTitle className="flex items-center gap-1.5 text-xs font-medium uppercase tracking-wider text-muted-foreground">
                <UserIcon className="size-3" />
                Agent KB
              </CardTitle>
            </CardHeader>
            <CardContent className="pb-2">
              <span className="text-2xl font-bold">
                {stats.agent_files_count}
              </span>
              <span className="ml-1.5 text-sm text-muted-foreground">
                / {formatSize(stats.agent_size_bytes)}
              </span>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Upload zone */}
      <div
        onClick={() => fileInputRef.current?.click()}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") fileInputRef.current?.click();
        }}
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        role="button"
        tabIndex={0}
        className={`flex cursor-pointer flex-col items-center gap-2 rounded-xl border-2 border-dashed p-6 text-center transition-colors ${
          isDragging
            ? "border-primary/60 bg-primary/5"
            : "border-border hover:border-primary/40"
        }`}
      >
        {isUploading ? (
          <>
            <Spinner className="size-8" />
            <p className="text-sm font-medium text-foreground">Uploading…</p>
          </>
        ) : (
          <>
            <UploadIcon className="size-8 text-muted-foreground/60" />
            <p className="text-sm font-medium text-foreground">
              Drag and drop files here, or click to browse
            </p>
            <p className="text-xs text-muted-foreground">
              PDF, Word, Excel, Markdown, text, HTML &middot; no size limit
            </p>
          </>
        )}
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept=".pdf,.md,.txt,.csv,.json,.html,.docx,.pptx,.xlsx,.doc,.xls,.ppt,.odt,.rtf"
          className="hidden"
          onChange={handleFileChange}
        />
      </div>

      {/* Search */}
      {hasDocuments && (
        <div className="relative">
          <SearchIcon className="absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            placeholder="Search files…"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-8"
          />
          {searchQuery && (
            <button
              type="button"
              onClick={() => setSearchQuery("")}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 rounded p-0.5 text-muted-foreground hover:text-foreground"
              aria-label="Clear search"
            >
              <XIcon className="size-3.5" />
            </button>
          )}
        </div>
      )}

      {/* Content */}
      {allLoading ? (
        <div className="flex justify-center py-12">
          <Spinner />
        </div>
      ) : !hasDocuments ? (
        <Empty>
          <EmptyMedia variant="icon">
            <HardDriveIcon />
          </EmptyMedia>
          <EmptyHeader>
            <EmptyTitle>No files uploaded yet</EmptyTitle>
            <EmptyDescription>
              Drag and drop files above to add them to your knowledge base.
            </EmptyDescription>
          </EmptyHeader>
        </Empty>
      ) : (
        <Tabs value={activeTab} onValueChange={setActiveTab}>
          <TabsList>
            <TabsTrigger value="all">All Files</TabsTrigger>
            <TabsTrigger value="org">Organization KB</TabsTrigger>
            <TabsTrigger value="agents">Agent KB</TabsTrigger>
          </TabsList>

          <TabsContent value="all" className="mt-4">
            {filteredDocuments.length === 0 ? (
              <Empty>
                <EmptyMedia variant="icon">
                  <SearchIcon />
                </EmptyMedia>
                <EmptyHeader>
                  <EmptyTitle>No files match your search</EmptyTitle>
                  <EmptyDescription>
                    Try a different search term or clear the filter.
                  </EmptyDescription>
                </EmptyHeader>
              </Empty>
            ) : (
              <div className="overflow-hidden rounded-lg border border-border">
                <DocumentTable
                  documents={filteredDocuments}
                  downloadingId={downloadingId}
                  onDownload={handleDownload}
                  onDelete={(id) => {
                    setDeletingDocId(id);
                    setDeleteDialogOpen(true);
                  }}
                  employeeMap={employeeMap}
                  showAgentColumn
                />
              </div>
            )}
          </TabsContent>

          <TabsContent value="org" className="mt-4">
            {orgDocuments.length === 0 ? (
              <Empty>
                <EmptyMedia variant="icon">
                  <Building2Icon />
                </EmptyMedia>
                <EmptyHeader>
                  <EmptyTitle>
                    {searchQuery
                      ? "No organization files match your search"
                      : "No organization-level files"}
                  </EmptyTitle>
                  <EmptyDescription>
                    {searchQuery
                      ? "Try a different search term."
                      : "Files uploaded without assigning an agent will appear here."}
                  </EmptyDescription>
                </EmptyHeader>
              </Empty>
            ) : (
              <div className="overflow-hidden rounded-lg border border-border">
                <DocumentTable
                  documents={orgDocuments}
                  downloadingId={downloadingId}
                  onDownload={handleDownload}
                  onDelete={(id) => {
                    setDeletingDocId(id);
                    setDeleteDialogOpen(true);
                  }}
                  employeeMap={employeeMap}
                />
              </div>
            )}
          </TabsContent>

          <TabsContent value="agents" className="mt-4">
            {agentGroups.length === 0 ? (
              <Empty>
                <EmptyMedia variant="icon">
                  <UserIcon />
                </EmptyMedia>
                <EmptyHeader>
                  <EmptyTitle>
                    {searchQuery
                      ? "No agent files match your search"
                      : "No agent-specific files"}
                  </EmptyTitle>
                  <EmptyDescription>
                    {searchQuery
                      ? "Try a different search term."
                      : "Files uploaded to individual agents will appear here."}
                  </EmptyDescription>
                </EmptyHeader>
              </Empty>
            ) : (
              <div className="space-y-6">
                {agentGroups.map(([empId, docs]) => (
                  <div
                    key={empId}
                    className="overflow-hidden rounded-lg border border-border"
                  >
                    <div className="flex items-center gap-2 border-b border-border bg-muted/30 px-4 py-2.5">
                      <UserIcon className="size-4 text-muted-foreground" />
                      <span className="text-sm font-semibold">
                        {employeeMap.get(empId) ?? "Unknown Agent"}
                      </span>
                      <Badge variant="secondary" className="ml-auto text-xs">
                        {docs.length} file{docs.length !== 1 ? "s" : ""}
                      </Badge>
                    </div>
                    <DocumentTable
                      documents={docs}
                      downloadingId={downloadingId}
                      onDownload={handleDownload}
                      onDelete={(id) => {
                        setDeletingDocId(id);
                        setDeleteDialogOpen(true);
                      }}
                      employeeMap={employeeMap}
                    />
                  </div>
                ))}
              </div>
            )}
          </TabsContent>
        </Tabs>
      )}

      {/* Delete confirmation */}
      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete document?</AlertDialogTitle>
            <AlertDialogDescription>
              This document will be permanently removed from your knowledge
              base.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel onClick={() => setDeletingDocId(null)}>
              Cancel
            </AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              onClick={handleDelete}
              disabled={deleteDocMutation.isPending}
            >
              {deleteDocMutation.isPending ? "Deleting..." : "Delete"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
