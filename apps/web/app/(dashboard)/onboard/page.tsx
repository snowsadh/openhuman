"use client";

import { useCallback, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeftIcon,
  BotIcon,
  CheckCircle2Icon,
  FileTextIcon,
  Loader2Icon,
  PlusIcon,
  ShieldCheckIcon,
  HeadphonesIcon,
  TrendingUpIcon,
  SparklesIcon,
  ScaleIcon,
  UploadIcon,
  XIcon,
} from "lucide-react";

import {
  ApiError,
  useEmployeesCreateEmployeeRoute,
  useEmployeesListEmployeesRoute,
  useEmployeesUpdateEmployeeRoute,
  getEmployeesListEmployeesRouteQueryKey,
  useDocumentsUploadDocument,
} from "@repo/api-client";
import { useOrgStore } from "@/stores/org";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Spinner } from "@/components/ui/spinner";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { BrandLogo } from "@/components/brand-logos";
import { cn } from "@/lib/utils";
import { toast } from "sonner";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// ── Fixed bot definitions ────────────────────────────────────────────────

interface FixedBot {
  name: string;
  role: string;
  employee_type: string;
  description: string;
  icon: React.ElementType;
  gradient: string;
  accentColor: string;
}

const FIXED_BOTS: FixedBot[] = [
  {
    name: "Alison",
    role: "HR Specialist",
    employee_type: "hr",
    description: "Manages onboarding, benefits, policies, and employee questions",
    icon: ShieldCheckIcon,
    gradient: "from-rose-500/10 to-pink-500/10",
    accentColor: "text-rose-500",
  },
  {
    name: "Alex",
    role: "Customer Support",
    employee_type: "support",
    description: "Handles customer inquiries, support tickets, and troubleshooting",
    icon: HeadphonesIcon,
    gradient: "from-blue-500/10 to-cyan-500/10",
    accentColor: "text-blue-500",
  },
  {
    name: "Marcus",
    role: "Sales Representative",
    employee_type: "sales",
    description: "Qualifies leads, researches prospects, and tracks pipeline metrics",
    icon: TrendingUpIcon,
    gradient: "from-emerald-500/10 to-green-500/10",
    accentColor: "text-emerald-500",
  },
  {
    name: "Jordan",
    role: "General Assistant",
    employee_type: "general",
    description: "Versatile assistant for research, calculations, and general tasks",
    icon: SparklesIcon,
    gradient: "from-violet-500/10 to-purple-500/10",
    accentColor: "text-violet-500",
  },
  {
    name: "Taylor",
    role: "Legal & Compliance",
    employee_type: "legal-compliance",
    description: "Reviews contracts, policies, and regulatory documents",
    icon: ScaleIcon,
    gradient: "from-amber-500/10 to-orange-500/10",
    accentColor: "text-amber-500",
  },
];

type UploadEntry = {
  file: File;
  status: "pending" | "uploading" | "done" | "error";
  error?: string;
};

export default function OnboardPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const orgId = useOrgStore((s) => s.orgId);
  const createMutation = useEmployeesCreateEmployeeRoute();
  const updateMutation = useEmployeesUpdateEmployeeRoute();
  const uploadDocMutation = useDocumentsUploadDocument();

  const [addingType, setAddingType] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Created employee
  const [createdEmpId, setCreatedEmpId] = useState<string | null>(null);
  const [createdBot, setCreatedBot] = useState<FixedBot | null>(null);

  // Dialog visibility states
  const [showDiscordDialog, setShowDiscordDialog] = useState(false);
  const [showClickupDialog, setShowClickupDialog] = useState(false);

  // Input states for dialogs
  const [discordToken, setDiscordToken] = useState("");
  const [discordClientId, setDiscordClientId] = useState("");
  const [clickupToken, setClickupToken] = useState("");

  // Connection status states
  const [discordConnected, setDiscordConnected] = useState(false);
  const [clickupConnected, setClickupConnected] = useState(false);

  // Duties
  const [duties, setDuties] = useState<string[]>([]);
  const [dutyInput, setDutyInput] = useState("");
  const [savingDuties, setSavingDuties] = useState(false);

  // File upload
  const uploadInputRef = useRef<HTMLInputElement>(null);
  const [uploadingFiles, setUploadingFiles] = useState<UploadEntry[]>([]);
  const [isUploading, setIsUploading] = useState(false);

  const { data: existingEmployees } = useEmployeesListEmployeesRoute(
    orgId ?? "",
    { query: { enabled: !!orgId } },
  );

  const takenTypes = useMemo(() => {
    if (!existingEmployees) return new Set<string>();
    return new Set(
      existingEmployees
        .map((e) => e.employee_type)
        .filter((t): t is string => t != null),
    );
  }, [existingEmployees]);

  const isCreated = createdEmpId !== null;

  // ── Pick bot → create employee ──────────────────────────────────────────

  const handleAddBot = useCallback(
    async (bot: FixedBot) => {
      if (!orgId || addingType) return;
      setAddingType(bot.employee_type);
      setError(null);
      try {
        const result = await createMutation.mutateAsync({
          orgId,
          data: { name: bot.name, employee_type: bot.employee_type, role: bot.role },
        });
        queryClient.invalidateQueries({ queryKey: getEmployeesListEmployeesRouteQueryKey(orgId) });
        setCreatedEmpId(result.id);
        setCreatedBot(bot);
        setAddingType(null);
      } catch (err) {
        setAddingType(null);
        if (err instanceof ApiError && err.status === 409) {
          setError(`${bot.name} is already deployed. Each bot type can only be added once.`);
        } else if (err instanceof Error) {
          setError(err.message);
        } else {
          setError("Failed to add bot. Please try again.");
        }
      }
    },
    [orgId, addingType, createMutation, queryClient],
  );

  // ── Duties ──────────────────────────────────────────────────────────────

  const handleAddDuty = useCallback(() => {
    const trimmed = dutyInput.trim();
    if (!trimmed) return;
    setDuties((prev) => [...prev, trimmed]);
    setDutyInput("");
  }, [dutyInput]);

  const handleRemoveDuty = useCallback((index: number) => {
    setDuties((prev) => prev.filter((_, i) => i !== index));
  }, []);

  const saveDuties = useCallback(async () => {
    if (!orgId || !createdEmpId || duties.length === 0) return;
    setSavingDuties(true);
    try {
      await updateMutation.mutateAsync({ orgId, empId: createdEmpId, data: { duties } });
    } catch {
      // non-blocking
    } finally {
      setSavingDuties(false);
    }
  }, [orgId, createdEmpId, duties, updateMutation]);

  // ── File upload ─────────────────────────────────────────────────────────

  const addUploadFiles = useCallback((newFiles: FileList | null) => {
    if (!newFiles) return;
    setUploadingFiles((prev) => [
      ...prev,
      ...Array.from(newFiles).map((file) => ({ file, status: "pending" as const })),
    ]);
  }, []);

  const removeUploadFile = useCallback((index: number) => {
    setUploadingFiles((prev) => prev.filter((_, i) => i !== index));
  }, []);

  const fileKey = (f: File) => `${f.name}-${f.size}-${f.lastModified}`;

  const errorUploadCount = uploadingFiles.filter((f) => f.status === "error").length;

  // ── Connection Helpers ──────────────────────────────────────────────────

  const saveDutiesAndUploadFiles = useCallback(async () => {
    if (!orgId || !createdEmpId) return false;
    try {
      if (duties.length > 0) await saveDuties();

      const pending = uploadingFiles.filter((f) => f.status !== "done");
      if (pending.length > 0) {
        setIsUploading(true);
        for (let i = 0; i < uploadingFiles.length; i++) {
          const entry = uploadingFiles[i];
          if (!entry || entry.status === "done") continue;
          setUploadingFiles((prev) => prev.map((f, idx) => (idx === i ? { ...f, status: "uploading" } : f)));
          try {
            await uploadDocMutation.mutateAsync({
              data: {
                file: entry.file as unknown as string,
                organization_id: orgId,
                employee_id: createdEmpId as unknown as string,
              },
            });
            setUploadingFiles((prev) => prev.map((f, idx) => (idx === i ? { ...f, status: "done" } : f)));
          } catch {
            setUploadingFiles((prev) =>
              prev.map((f, idx) => (idx === i ? { ...f, status: "error", error: "Upload failed" } : f)),
            );
          }
        }
        setIsUploading(false);
      }
      return true;
    } catch {
      setIsUploading(false);
      return false;
    }
  }, [orgId, createdEmpId, duties, uploadingFiles, saveDuties, uploadDocMutation]);

  const handleConnectSlack = useCallback(async () => {
    if (!orgId || !createdEmpId) return;
    const success = await saveDutiesAndUploadFiles();
    if (!success) return;

    // Always bounce back to whichever domain the user is actually on
    // (e.g. the Railway-generated domain vs. a custom domain), instead of
    // relying on the API's static FRONTEND_URL fallback.
    const redirectTo = `${window.location.origin}/dashboard/${createdEmpId}`;
    const installUrl = `${API_URL}/api/slack/install?employee_id=${encodeURIComponent(createdEmpId)}&org_id=${encodeURIComponent(orgId)}&redirect_to=${encodeURIComponent(redirectTo)}`;
    window.location.href = installUrl;
  }, [orgId, createdEmpId, saveDutiesAndUploadFiles]);

  const handleConnectDiscord = useCallback(async () => {
    if (!createdEmpId) return;
    if (!discordToken.trim()) {
      toast.error("Please enter a Discord Bot Token");
      return;
    }
    const success = await saveDutiesAndUploadFiles();
    if (!success) return;

    localStorage.setItem(`openhuman_discord_connected_${createdEmpId}`, "true");
    localStorage.setItem(`openhuman_discord_token_${createdEmpId}`, discordToken);
    if (discordClientId.trim()) {
      localStorage.setItem(`openhuman_discord_client_id_${createdEmpId}`, discordClientId);
    }
    setDiscordConnected(true);
    setShowDiscordDialog(false);
    toast.success("Discord bot connected successfully!");
  }, [createdEmpId, discordToken, discordClientId, saveDutiesAndUploadFiles]);

  const handleDisconnectDiscord = useCallback(() => {
    if (!createdEmpId) return;
    localStorage.removeItem(`openhuman_discord_connected_${createdEmpId}`);
    localStorage.removeItem(`openhuman_discord_token_${createdEmpId}`);
    localStorage.removeItem(`openhuman_discord_client_id_${createdEmpId}`);
    setDiscordConnected(false);
    toast.success("Discord bot disconnected.");
  }, [createdEmpId]);

  const handleConnectClickup = useCallback(async () => {
    if (!createdEmpId) return;
    if (!clickupToken.trim()) {
      toast.error("Please enter a ClickUp Personal API Token");
      return;
    }
    const success = await saveDutiesAndUploadFiles();
    if (!success) return;

    localStorage.setItem(`openhuman_clickup_connected_${createdEmpId}`, "true");
    localStorage.setItem(`openhuman_clickup_token_${createdEmpId}`, clickupToken);
    setClickupConnected(true);
    setShowClickupDialog(false);
    toast.success("ClickUp workspace connected successfully!");
  }, [createdEmpId, clickupToken, saveDutiesAndUploadFiles]);

  const handleDisconnectClickup = useCallback(() => {
    if (!createdEmpId) return;
    localStorage.removeItem(`openhuman_clickup_connected_${createdEmpId}`);
    localStorage.removeItem(`openhuman_clickup_token_${createdEmpId}`);
    setClickupConnected(false);
    toast.success("ClickUp workspace disconnected.");
  }, [createdEmpId]);

  const handleSkipToDashboard = useCallback(async () => {
    await saveDutiesAndUploadFiles();
    router.push("/dashboard");
  }, [saveDutiesAndUploadFiles, router]);

  const handleReset = useCallback(() => {
    setCreatedEmpId(null);
    setCreatedBot(null);
    setDuties([]);
    setDutyInput("");
    setUploadingFiles([]);
    setDiscordConnected(false);
    setClickupConnected(false);
    setDiscordToken("");
    setDiscordClientId("");
    setClickupToken("");
  }, []);

  // ── Render ──────────────────────────────────────────────────────────────

  return (
    <div className="flex flex-1 flex-col gap-8 px-6 py-6">
      <div className="flex items-center gap-4">
        <Button variant="ghost" size="sm" className="w-fit" onClick={() => router.push("/dashboard")}>
          <ArrowLeftIcon />
          Back to Team
        </Button>
      </div>

      <div className="mx-auto flex w-full max-w-3xl flex-col gap-8">
        {/* Header */}
        <div className="flex flex-col gap-3 text-center">
          <h1 className="text-2xl font-semibold tracking-tight text-foreground">
            Add an AI employee to your team
          </h1>
          <p className="text-base text-muted-foreground">
            Pick a bot to add to your Slack workspace. Each bot has a fixed identity
            and specialization.
          </p>
        </div>

        {/* Error banner */}
        {error && (
          <div className="rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
            {error}
          </div>
        )}

        {/* Bot grid */}
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {FIXED_BOTS.map((bot) => {
            const isTaken = takenTypes.has(bot.employee_type);
            const isAdding = addingType === bot.employee_type;
            const isDisabled = isTaken || !!addingType || isCreated;
            const Icon = bot.icon;

            return (
              <button
                key={bot.employee_type}
                type="button"
                disabled={isDisabled}
                onClick={() => handleAddBot(bot)}
                className={`group relative flex flex-col gap-4 rounded-2xl border-2 p-5 text-left transition-colors ${
                  isTaken
                    ? "cursor-default border-border/50 bg-muted/20 opacity-60"
                    : isAdding
                      ? "border-primary bg-primary/5"
                      : isDisabled
                        ? "cursor-not-allowed border-border/50 opacity-50"
                        : "border-border hover:border-primary/50"
                }`}
              >
                <div className="flex items-start gap-3">
                  <div className={`flex size-10 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br ${bot.gradient}`}>
                    <Icon className={`size-5 ${bot.accentColor}`} />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="text-base font-semibold text-foreground">{bot.name}</span>
                      {isTaken && <CheckCircle2Icon className="size-4 text-emerald-500" />}
                    </div>
                    <span className="text-sm text-muted-foreground">{bot.role}</span>
                  </div>
                </div>
                <p className="text-sm leading-relaxed text-muted-foreground">{bot.description}</p>
                <div className="mt-auto pt-1">
                  {isTaken ? (
                    <span className="inline-flex items-center gap-1.5 text-xs font-medium text-emerald-600 dark:text-emerald-400">
                      <CheckCircle2Icon className="size-3.5" />
                      Active in your workspace
                    </span>
                  ) : isAdding ? (
                    <span className="inline-flex items-center gap-1.5 text-xs font-medium text-primary">
                      <Loader2Icon className="size-3.5 animate-spin" />
                      Creating
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1.5 text-xs font-medium text-muted-foreground/70">
                      <BotIcon className="size-3.5" />
                      Click to add to Slack
                    </span>
                  )}
                </div>
              </button>
            );
          })}
        </div>

        {/* ── Configuration section (shown after employee is created) ────── */}
        {isCreated && createdBot && (
          <>
            <div className="border-t border-border" />

            <div className="flex flex-col gap-3 text-center">
              <h2 className="text-xl font-semibold tracking-tight text-foreground">
                Configure {createdBot.name}
              </h2>
              <p className="text-sm text-muted-foreground">
                {createdBot.role} &mdash; set responsibilities and upload knowledge before
                connecting to your channels. You can always change these later.
              </p>
            </div>

            {/* Duties */}
            <div className="flex flex-col gap-3">
              <div className="flex flex-col gap-1">
                <h3 className="text-sm font-medium text-foreground">Duties</h3>
                <p className="text-sm text-muted-foreground">
                  What should {createdBot.name} be responsible for?
                </p>
              </div>
              {duties.length > 0 && (
                <div className="flex flex-col gap-2">
                  {duties.map((duty, i) => (
                    <div
                      key={i}
                      className="flex items-start gap-2 rounded-lg border border-border bg-muted/30 px-3 py-2.5"
                    >
                      <span className="min-w-0 flex-1 text-sm text-foreground">{duty}</span>
                      <button
                        type="button"
                        onClick={() => handleRemoveDuty(i)}
                        className="mt-0.5 shrink-0 rounded-sm text-muted-foreground hover:text-foreground"
                        aria-label={`Remove duty: ${duty}`}
                      >
                        <XIcon className="size-4" />
                      </button>
                    </div>
                  ))}
                </div>
              )}
              <div className="flex flex-col gap-2">
                <Textarea
                  placeholder="e.g. Read all PDFs shared in #legal and review for compliance risks"
                  value={dutyInput}
                  onChange={(e) => setDutyInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                      e.preventDefault();
                      handleAddDuty();
                    }
                  }}
                  rows={3}
                />
                <Button type="button" variant="outline" onClick={handleAddDuty} className="shrink-0 w-fit">
                  <PlusIcon />
                  Add duty
                </Button>
              </div>
            </div>

            {/* Knowledge upload */}
            <div className="flex flex-col gap-3">
              <div className="flex flex-col gap-1">
                <h3 className="text-sm font-medium text-foreground">Knowledge files</h3>
                <p className="text-sm text-muted-foreground">
                  Upload PDFs, documents, or markdown files {createdBot.name} should know about.
                </p>
              </div>

              <div
                onClick={() => uploadInputRef.current?.click()}
                onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") uploadInputRef.current?.click(); }}
                role="button"
                tabIndex={0}
                className="flex cursor-pointer flex-col items-center gap-2 rounded-xl border-2 border-dashed border-border p-6 text-center transition-colors hover:border-primary/40"
              >
                <UploadIcon className="size-6 text-muted-foreground/60" />
                <p className="text-sm font-medium text-foreground">Click to upload files</p>
                <p className="text-xs text-muted-foreground">
                  PDF, Word, Excel, Markdown, text, HTML &middot; no size limit
                </p>
                <input
                  ref={uploadInputRef}
                  type="file"
                  accept=".pdf,.md,.txt,.csv,.json,.html,.docx,.pptx,.xlsx,.doc,.xls,.ppt,.odt,.rtf"
                  multiple
                  className="hidden"
                  onChange={(e) => addUploadFiles(e.target.files)}
                />
              </div>

              {uploadingFiles.length > 0 && (
                <div className="space-y-2">
                  {uploadingFiles.map((entry, i) => (
                    <div key={fileKey(entry.file)} className="flex items-center gap-3 rounded-lg border border-border px-3 py-2.5">
                      <FileTextIcon className="size-4 shrink-0 text-muted-foreground" />
                      <span className="min-w-0 flex-1 truncate text-sm">{entry.file.name}</span>
                      {entry.status === "uploading" && <Spinner className="size-4" />}
                      {entry.status === "done" && (
                        <span className="text-xs text-emerald-600">Uploaded</span>
                      )}
                      {entry.status === "error" && (
                        <span className="text-xs text-destructive">{entry.error ?? "Error"}</span>
                      )}
                      {entry.status !== "uploading" && entry.status !== "done" && (
                        <button
                          type="button"
                          onClick={() => removeUploadFile(i)}
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

              {errorUploadCount > 0 && (
                <p className="text-sm text-destructive">
                  {errorUploadCount} file{errorUploadCount !== 1 ? "s" : ""} failed to upload.
                </p>
              )}
            </div>

            {/* Connection Channels */}
            <div className="flex flex-col gap-3">
              <div className="flex flex-col gap-1">
                <h3 className="text-sm font-medium text-foreground">Connection channels</h3>
                <p className="text-sm text-muted-foreground">
                  Connect {createdBot.name} to the channels where your team communicates and works.
                </p>
              </div>

              <div className="grid gap-4 sm:grid-cols-3">
                {/* Slack Card */}
                <div className="flex flex-col justify-between rounded-xl border p-5 text-left bg-muted/10 border-border hover:border-primary/30 transition-colors">
                  <div className="flex items-center gap-2 mb-2">
                    <BrandLogo slug="slack" className="size-5" />
                    <span className="font-semibold text-sm">Slack</span>
                  </div>
                  <p className="text-xs text-muted-foreground leading-relaxed mb-4">
                    Install {createdBot.name} to your Slack workspace so it can respond to mentions.
                  </p>
                  <Button
                    size="sm"
                    variant="outline"
                    className="w-full text-xs"
                    onClick={handleConnectSlack}
                    disabled={isUploading || savingDuties}
                  >
                    Connect Slack
                  </Button>
                </div>

                {/* Discord Card */}
                <div className={cn(
                  "flex flex-col justify-between rounded-xl border p-5 text-left bg-muted/10 transition-colors",
                  discordConnected ? "border-green-500/20 bg-green-500/5" : "border-border hover:border-primary/30"
                )}>
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <BrandLogo slug="discord" className="size-5" />
                      <span className="font-semibold text-sm">Discord</span>
                    </div>
                    {discordConnected && (
                      <span className="text-[10px] bg-green-500/10 text-green-700 font-semibold px-2 py-0.5 rounded-full">
                        Connected
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-muted-foreground leading-relaxed mb-4">
                    Configure a Discord bot token to respond to messages in your servers.
                  </p>
                  {discordConnected ? (
                    <Button
                      size="sm"
                      variant="outline"
                      className="w-full text-xs text-destructive hover:bg-destructive/10 hover:text-destructive"
                      onClick={handleDisconnectDiscord}
                    >
                      Disconnect
                    </Button>
                  ) : (
                    <Button
                      size="sm"
                      variant="outline"
                      className="w-full text-xs"
                      onClick={() => setShowDiscordDialog(true)}
                    >
                      Connect Discord
                    </Button>
                  )}
                </div>

                {/* ClickUp Card */}
                <div className={cn(
                  "flex flex-col justify-between rounded-xl border p-5 text-left bg-muted/10 transition-colors",
                  clickupConnected ? "border-green-500/20 bg-green-500/5" : "border-border hover:border-primary/30"
                )}>
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <BrandLogo slug="clickup" className="size-5" />
                      <span className="font-semibold text-sm">ClickUp</span>
                    </div>
                    {clickupConnected && (
                      <span className="text-[10px] bg-green-500/10 text-green-700 font-semibold px-2 py-0.5 rounded-full">
                        Connected
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-muted-foreground leading-relaxed mb-4">
                    Sync tasks and manage tickets within your ClickUp lists.
                  </p>
                  {clickupConnected ? (
                    <Button
                      size="sm"
                      variant="outline"
                      className="w-full text-xs text-destructive hover:bg-destructive/10 hover:text-destructive"
                      onClick={handleDisconnectClickup}
                    >
                      Disconnect
                    </Button>
                  ) : (
                    <Button
                      size="sm"
                      variant="outline"
                      className="w-full text-xs"
                      onClick={() => setShowClickupDialog(true)}
                    >
                      Connect ClickUp
                    </Button>
                  )}
                </div>
              </div>
            </div>

            {/* Actions */}
            <div className="flex items-center justify-end gap-3 border-t border-border pt-6">
              <Button
                variant="ghost"
                size="lg"
                onClick={handleReset}
                disabled={isUploading || savingDuties}
              >
                Choose a different bot
              </Button>
              <Button
                size="lg"
                onClick={handleSkipToDashboard}
                disabled={isUploading || savingDuties}
              >
                {isUploading ? (
                  <>
                    <Loader2Icon className="size-4 animate-spin" />
                    Uploading
                  </>
                ) : savingDuties ? (
                  <>
                    <Loader2Icon className="size-4 animate-spin" />
                    Saving
                  </>
                ) : (
                  "Go to Dashboard"
                )}
              </Button>
            </div>
          </>
        )}

        {/* Footer hint */}
        {!isCreated && (
          <p className="text-center text-xs text-muted-foreground/60">
            Each bot will appear in your Slack workspace with its own identity. Manage
            them from your{" "}
            <Link href="/dashboard" className="underline">
              dashboard
            </Link>{" "}
            at any time.
          </p>
        )}
      </div>

      {/* Discord Connection Dialog */}
      <Dialog open={showDiscordDialog} onOpenChange={setShowDiscordDialog}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Connect Discord Bot</DialogTitle>
            <DialogDescription>
              Provide the credentials for your Discord Application Bot to allow {createdBot?.name} to connect.
            </DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-4 py-4">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="discord-token">Discord Bot Token</Label>
              <Input
                id="discord-token"
                type="password"
                placeholder="MTg0Nj..."
                value={discordToken}
                onChange={(e) => setDiscordToken(e.target.value)}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="discord-client-id">Application / Client ID (Optional)</Label>
              <Input
                id="discord-client-id"
                placeholder="1029..."
                value={discordClientId}
                onChange={(e) => setDiscordClientId(e.target.value)}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setShowDiscordDialog(false)}>
              Cancel
            </Button>
            <Button onClick={handleConnectDiscord}>
              Confirm Connection
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ClickUp Connection Dialog */}
      <Dialog open={showClickupDialog} onOpenChange={setShowClickupDialog}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Connect ClickUp Workspace</DialogTitle>
            <DialogDescription>
              Enter your Personal API Token to allow {createdBot?.name} to manage and sync tasks.
            </DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-4 py-4">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="clickup-token">Personal API Token</Label>
              <Input
                id="clickup-token"
                type="password"
                placeholder="pk_..."
                value={clickupToken}
                onChange={(e) => setClickupToken(e.target.value)}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setShowClickupDialog(false)}>
              Cancel
            </Button>
            <Button onClick={handleConnectClickup}>
              Confirm Connection
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
