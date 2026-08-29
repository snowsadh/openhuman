"use client";

import React, { useState, useMemo, useCallback } from "react";
import { useQueryClient, useQuery } from "@tanstack/react-query";
import {
  Search,
  ExternalLink,
  CheckCircle,
  Puzzle,
  Download,
  X,
  Code,
  Layers,
  Sparkles,
  Database,
  Mail,
  Slack as SlackIcon,
  Terminal,
  Activity,
  Globe,
  MapPin,
  Calendar,
  PhoneCall,
  Layout,
  Flame,
  Loader2,
  AlertCircle,
  Bot,
} from "lucide-react";
import { toast } from "sonner";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardHeader, CardContent, CardFooter } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { BrandLogo } from "@/components/brand-logos";
import { useOrgStore } from "@/stores/org";
import {
  useMcpListMcpConnectors,
  useMcpCreateMcpConnection,
  useMcpDeleteMcpConnection,
  useEmployeesListEmployeesRoute,
} from "@repo/api-client";

type Category = "All" | "Productivity" | "Development" | "Data & DBs" | "Communication" | "AI & Search";

interface McpServer {
  id: string;
  name: string;
  description: string;
  category: Category;
  authType: "OAuth2" | "API Key" | "PAT" | "None";
  url: string;
  icon: React.ComponentType<React.SVGProps<SVGSVGElement>>;
  iconColor: string;
  author: string;
  rating: number;
  tools: string[];
  resources: string[];
  mcpJsonConfig: string;
}

interface CatalogEntry {
  slug: string;
  name: string;
  description: string;
  category: string;
  auth_type: string;
  docs_url: string;
  is_hardcoded: boolean;
  is_installed: boolean;
}

const authTypeMap: Record<string, "OAuth2" | "API Key" | "PAT" | "None"> = {
  oauth2: "OAuth2",
  api_key: "API Key",
  api_key_header: "API Key",
  pat: "PAT",
  pat_bearer: "PAT",
  none: "None",
};

interface DisplayMeta {
  icon: React.ComponentType<React.SVGProps<SVGSVGElement>>;
  iconColor: string;
  author: string;
  rating: number;
  tools: string[];
  resources: string[];
  mcpJsonConfig: string;
}

const DISPLAY_META: Record<string, DisplayMeta> = {
  gmail: {
    icon: Mail, iconColor: "from-red-500 to-rose-600", author: "Google", rating: 4.9,
    tools: ["search_threads", "get_message", "create_draft", "send_message", "list_labels"],
    resources: ["gmail://threads", "gmail://drafts"],
    mcpJsonConfig: `{\n  "mcpServers": {\n    "gmail": {\n      "command": "npx",\n      "args": ["-y", "@modelcontextprotocol/server-gmail"]\n    }\n  }\n}`,
  },
  github: {
    icon: Terminal, iconColor: "from-slate-800 to-slate-900", author: "GitHub", rating: 4.8,
    tools: ["search_code", "list_repos", "get_issue", "create_pr", "get_file_contents"],
    resources: ["github://repos", "github://issues"],
    mcpJsonConfig: `{\n  "mcpServers": {\n    "github": {\n      "command": "npx",\n      "args": ["-y", "@modelcontextprotocol/server-github"]\n    }\n  }\n}`,
  },
  notion: {
    icon: Layers, iconColor: "from-zinc-700 to-black", author: "Notion", rating: 4.7,
    tools: ["search_notion", "retrieve_page", "create_page", "update_database_row"],
    resources: ["notion://pages", "notion://databases"],
    mcpJsonConfig: `{\n  "mcpServers": {\n    "notion": {\n      "command": "npx",\n      "args": ["-y", "@modelcontextprotocol/server-notion"]\n    }\n  }\n}`,
  },
  vercel: {
    icon: Code, iconColor: "from-neutral-900 to-zinc-950", author: "Vercel", rating: 4.8,
    tools: ["list_deployments", "get_project_logs", "add_env_variable", "redeploy_project"],
    resources: ["vercel://projects", "vercel://domains"],
    mcpJsonConfig: `{\n  "mcpServers": {\n    "vercel": {\n      "command": "npx",\n      "args": ["-y", "@modelcontextprotocol/server-vercel"]\n    }\n  }\n}`,
  },
  n8n: {
    icon: Puzzle, iconColor: "from-rose-500 to-fuchsia-600", author: "n8n", rating: 4.8,
    tools: ["search_workflows", "execute_workflow", "create_workflow", "update_workflow"],
    resources: ["n8n://workflows", "n8n://projects"],
    mcpJsonConfig: `{\n  "mcpServers": {\n    "n8n": {\n      "type": "http",\n      "url": "https://your-n8n-instance.com/mcp-server/http",\n      "headers": {\n        "Authorization": "Bearer YOUR_N8N_MCP_ACCESS_TOKEN"\n      }\n    }\n  }\n}`,
  },
  gamma: {
    icon: Layout, iconColor: "from-fuchsia-500 to-purple-600", author: "Gamma", rating: 4.9,
    tools: ["generate_presentation", "export_pdf", "list_templates", "get_generation_status"],
    resources: ["gamma://templates", "gamma://documents"],
    mcpJsonConfig: `{\n  "mcpServers": {\n    "gamma": {\n      "command": "npx",\n      "args": ["-y", "@modelcontextprotocol/server-gamma"]\n    }\n  }\n}`,
  },
  slack: {
    icon: SlackIcon, iconColor: "from-amber-500 via-rose-500 to-purple-700", author: "Community", rating: 4.6,
    tools: ["send_message", "list_channels", "fetch_history", "create_channel"],
    resources: ["slack://channels", "slack://users"],
    mcpJsonConfig: `{\n  "mcpServers": {\n    "slack": {\n      "command": "npx",\n      "args": ["-y", "@modelcontextprotocol/server-slack"]\n    }\n  }\n}`,
  },
  postgres: {
    icon: Database, iconColor: "from-blue-600 to-indigo-700", author: "Postgres Community", rating: 4.8,
    tools: ["execute_query", "list_tables", "get_schema", "describe_table"],
    resources: ["pg://tables", "pg://schemas"],
    mcpJsonConfig: `{\n  "mcpServers": {\n    "postgres": {\n      "command": "npx",\n      "args": ["-y", "@modelcontextprotocol/server-postgres", "--connection-string", "env:DATABASE_URL"]\n    }\n  }\n}`,
  },
  "brave-search": {
    icon: Globe, iconColor: "from-orange-500 to-red-600", author: "Brave Software", rating: 4.7,
    tools: ["web_search", "local_search", "fetch_snippets"],
    resources: ["brave://search-results"],
    mcpJsonConfig: `{\n  "mcpServers": {\n    "brave-search": {\n      "command": "npx",\n      "args": ["-y", "@modelcontextprotocol/server-brave-search"]\n    }\n  }\n}`,
  },
  huggingface: {
    icon: Sparkles, iconColor: "from-yellow-400 to-orange-500", author: "Hugging Face", rating: 4.6,
    tools: ["search_models", "list_datasets", "get_model_details", "run_inference"],
    resources: ["hf://models", "hf://datasets"],
    mcpJsonConfig: `{\n  "mcpServers": {\n    "huggingface": {\n      "command": "npx",\n      "args": ["-y", "@modelcontextprotocol/server-huggingface"]\n    }\n  }\n}`,
  },
  jira: {
    icon: Activity, iconColor: "from-blue-500 to-sky-600", author: "Atlassian", rating: 4.5,
    tools: ["create_issue", "assign_issue", "transition_issue", "get_sprint_board"],
    resources: ["jira://issues", "jira://boards"],
    mcpJsonConfig: `{\n  "mcpServers": {\n    "jira": {\n      "command": "npx",\n      "args": ["-y", "@modelcontextprotocol/server-jira"]\n    }\n  }\n}`,
  },
  linear: {
    icon: Puzzle, iconColor: "from-neutral-800 to-stone-900", author: "Linear", rating: 4.9,
    tools: ["list_issues", "create_issue", "get_teams", "update_cycles"],
    resources: ["linear://cycles", "linear://issues"],
    mcpJsonConfig: `{\n  "mcpServers": {\n    "linear": {\n      "command": "npx",\n      "args": ["-y", "@modelcontextprotocol/server-linear"]\n    }\n  }\n}`,
  },
  shopify: {
    icon: Database, iconColor: "from-green-500 to-emerald-600", author: "Community Dev", rating: 4.4,
    tools: ["get_products", "check_inventory", "list_recent_orders"],
    resources: ["shopify://products", "shopify://orders"],
    mcpJsonConfig: `{\n  "mcpServers": {\n    "shopify": {\n      "command": "npx",\n      "args": ["-y", "@modelcontextprotocol/server-shopify"]\n    }\n  }\n}`,
  },
  stripe: {
    icon: Database, iconColor: "from-violet-500 to-indigo-600", author: "Stripe", rating: 4.8,
    tools: ["list_charges", "create_customer", "retrieve_invoice", "refund_charge"],
    resources: ["stripe://charges", "stripe://customers"],
    mcpJsonConfig: `{\n  "mcpServers": {\n    "stripe": {\n      "command": "npx",\n      "args": ["-y", "@modelcontextprotocol/server-stripe"]\n    }\n  }\n}`,
  },
  airtable: {
    icon: Database, iconColor: "from-blue-400 to-indigo-500", author: "Community", rating: 4.5,
    tools: ["get_base_records", "add_row_record", "delete_record"],
    resources: ["airtable://bases"],
    mcpJsonConfig: `{\n  "mcpServers": {\n    "airtable": {\n      "command": "npx",\n      "args": ["-y", "@modelcontextprotocol/server-airtable"]\n    }\n  }\n}`,
  },
  snowflake: {
    icon: Database, iconColor: "from-sky-400 to-blue-500", author: "Snowflake", rating: 4.7,
    tools: ["run_warehouse_sql", "list_schemas", "describe_table_columns"],
    resources: ["snowflake://warehouses"],
    mcpJsonConfig: `{\n  "mcpServers": {\n    "snowflake": {\n      "command": "npx",\n      "args": ["-y", "@modelcontextprotocol/server-snowflake"]\n    }\n  }\n}`,
  },
  wikipedia: {
    icon: Globe, iconColor: "from-slate-400 to-slate-600", author: "Wikimedia Foundation", rating: 4.6,
    tools: ["search_wikipedia", "get_article_summary", "get_related_links"],
    resources: ["wikipedia://articles"],
    mcpJsonConfig: `{\n  "mcpServers": {\n    "wikipedia": {\n      "command": "npx",\n      "args": ["-y", "@modelcontextprotocol/server-wikipedia"]\n    }\n  }\n}`,
  },
  youtube: {
    icon: Mail, iconColor: "from-red-600 to-red-700", author: "Google", rating: 4.6,
    tools: ["search_videos", "get_video_transcript", "add_to_playlist"],
    resources: ["youtube://videos", "youtube://playlists"],
    mcpJsonConfig: `{\n  "mcpServers": {\n    "youtube": {\n      "command": "npx",\n      "args": ["-y", "@modelcontextprotocol/server-youtube"]\n    }\n  }\n}`,
  },
  redis: {
    icon: Database, iconColor: "from-red-500 to-orange-600", author: "Redis Inc.", rating: 4.7,
    tools: ["get_cache_key", "set_cache_key", "flush_keyspace", "monitor_pubsub"],
    resources: ["redis://keyspaces"],
    mcpJsonConfig: `{\n  "mcpServers": {\n    "redis": {\n      "command": "npx",\n      "args": ["-y", "@modelcontextprotocol/server-redis"]\n    }\n  }\n}`,
  },
  docker: {
    icon: Terminal, iconColor: "from-blue-500 to-indigo-600", author: "Docker Community", rating: 4.8,
    tools: ["list_containers", "inspect_logs", "restart_container", "prune_networks"],
    resources: ["docker://containers", "docker://images"],
    mcpJsonConfig: `{\n  "mcpServers": {\n    "docker": {\n      "command": "npx",\n      "args": ["-y", "@modelcontextprotocol/server-docker"]\n    }\n  }\n}`,
  },
  "aws-s3": {
    icon: Terminal, iconColor: "from-orange-500 to-amber-600", author: "Amazon Web Services", rating: 4.7,
    tools: ["list_s3_buckets", "get_bucket_objects", "upload_cloud_file"],
    resources: ["s3://buckets"],
    mcpJsonConfig: `{\n  "mcpServers": {\n    "aws-s3": {\n      "command": "npx",\n      "args": ["-y", "@modelcontextprotocol/server-aws-s3"]\n    }\n  }\n}`,
  },
  gitlab: {
    icon: Terminal, iconColor: "from-orange-600 to-rose-600", author: "GitLab", rating: 4.6,
    tools: ["list_pipeline_jobs", "create_merge_request", "add_comment_thread"],
    resources: ["gitlab://pipelines", "gitlab://merge-requests"],
    mcpJsonConfig: `{\n  "mcpServers": {\n    "gitlab": {\n      "command": "npx",\n      "args": ["-y", "@modelcontextprotocol/server-gitlab"]\n    }\n  }\n}`,
  },
  figma: {
    icon: Puzzle, iconColor: "from-red-500 via-purple-500 to-blue-500", author: "Figma", rating: 4.8,
    tools: ["fetch_artboards", "export_frame_asset", "get_styles_library"],
    resources: ["figma://files"],
    mcpJsonConfig: `{\n  "mcpServers": {\n    "figma": {\n      "command": "npx",\n      "args": ["-y", "@modelcontextprotocol/server-figma"]\n    }\n  }\n}`,
  },
  salesforce: {
    icon: Database, iconColor: "from-sky-500 to-indigo-500", author: "Salesforce", rating: 4.5,
    tools: ["query_leads", "update_crm_account", "list_deals_pipeline"],
    resources: ["salesforce://leads", "salesforce://opportunities"],
    mcpJsonConfig: `{\n  "mcpServers": {\n    "salesforce": {\n      "command": "npx",\n      "args": ["-y", "@modelcontextprotocol/server-salesforce"]\n    }\n  }\n}`,
  },
  hubspot: {
    icon: SlackIcon, iconColor: "from-orange-500 to-amber-600", author: "HubSpot", rating: 4.6,
    tools: ["get_contact_list", "register_deal", "log_call_interaction"],
    resources: ["hubspot://contacts"],
    mcpJsonConfig: `{\n  "mcpServers": {\n    "hubspot": {\n      "command": "npx",\n      "args": ["-y", "@modelcontextprotocol/server-hubspot"]\n    }\n  }\n}`,
  },
  zendesk: {
    icon: SlackIcon, iconColor: "from-emerald-600 to-teal-700", author: "Zendesk", rating: 4.6,
    tools: ["retrieve_tickets", "assign_agent", "add_ticket_comment"],
    resources: ["zendesk://tickets"],
    mcpJsonConfig: `{\n  "mcpServers": {\n    "zendesk": {\n      "command": "npx",\n      "args": ["-y", "@modelcontextprotocol/server-zendesk"]\n    }\n  }\n}`,
  },
  trello: {
    icon: Puzzle, iconColor: "from-blue-500 to-sky-500", author: "Atlassian", rating: 4.4,
    tools: ["create_trello_card", "move_card_list", "add_card_checklist"],
    resources: ["trello://boards"],
    mcpJsonConfig: `{\n  "mcpServers": {\n    "trello": {\n      "command": "npx",\n      "args": ["-y", "@modelcontextprotocol/server-trello"]\n    }\n  }\n}`,
  },
  "google-calendar": {
    icon: Calendar, iconColor: "from-blue-500 to-indigo-600", author: "Google", rating: 4.8,
    tools: ["list_calendar_events", "create_calendar_event", "check_availability"],
    resources: ["calendar://events"],
    mcpJsonConfig: `{\n  "mcpServers": {\n    "google-calendar": {\n      "command": "npx",\n      "args": ["-y", "@modelcontextprotocol/server-calendar"]\n    }\n  }\n}`,
  },
  twilio: {
    icon: PhoneCall, iconColor: "from-red-500 to-red-600", author: "Twilio", rating: 4.6,
    tools: ["send_sms_message", "initiate_voice_call", "verify_phone_otp"],
    resources: ["twilio://messages", "twilio://calls"],
    mcpJsonConfig: `{\n  "mcpServers": {\n    "twilio": {\n      "command": "npx",\n      "args": ["-y", "@modelcontextprotocol/server-twilio"]\n    }\n  }\n}`,
  },
  medium: {
    icon: Globe, iconColor: "from-neutral-900 to-stone-950", author: "Medium", rating: 4.3,
    tools: ["create_blog_post", "list_user_stories", "publish_draft"],
    resources: ["medium://stories"],
    mcpJsonConfig: `{\n  "mcpServers": {\n    "medium": {\n      "command": "npx",\n      "args": ["-y", "@modelcontextprotocol/server-medium"]\n    }\n  }\n}`,
  },
  discord: {
    icon: SlackIcon, iconColor: "from-indigo-500 to-blue-600", author: "Community", rating: 4.5,
    tools: ["dispatch_webhook", "list_channel_messages", "list_guild_members"],
    resources: ["discord://guilds"],
    mcpJsonConfig: `{\n  "mcpServers": {\n    "discord": {\n      "command": "npx",\n      "args": ["-y", "@modelcontextprotocol/server-discord"]\n    }\n  }\n}`,
  },
  "google-maps": {
    icon: MapPin, iconColor: "from-green-500 to-emerald-600", author: "Google", rating: 4.8,
    tools: ["resolve_geocode", "calculate_route", "search_places_nearby"],
    resources: ["maps://routes"],
    mcpJsonConfig: `{\n  "mcpServers": {\n    "google-maps": {\n      "command": "npx",\n      "args": ["-y", "@modelcontextprotocol/server-maps"]\n    }\n  }\n}`,
  },
  zoom: {
    icon: PhoneCall, iconColor: "from-blue-500 to-sky-600", author: "Zoom Inc.", rating: 4.7,
    tools: ["schedule_instant_meeting", "list_recordings", "register_webinar_user"],
    resources: ["zoom://meetings"],
    mcpJsonConfig: `{\n  "mcpServers": {\n    "zoom": {\n      "command": "npx",\n      "args": ["-y", "@modelcontextprotocol/server-zoom"]\n    }\n  }\n}`,
  },
  clickup: {
    icon: Puzzle, iconColor: "from-purple-500 to-rose-500", author: "ClickUp", rating: 4.5,
    tools: ["create_clickup_task", "update_task_status", "track_task_time"],
    resources: ["clickup://tasks"],
    mcpJsonConfig: `{\n  "mcpServers": {\n    "clickup": {\n      "command": "npx",\n      "args": ["-y", "@modelcontextprotocol/server-clickup"]\n    }\n  }\n}`,
  },
  firebase: {
    icon: Terminal, iconColor: "from-amber-400 to-orange-500", author: "Google", rating: 4.7,
    tools: ["query_firestore", "list_auth_users", "dispatch_fcm_notification"],
    resources: ["firebase://firestore", "firebase://auth"],
    mcpJsonConfig: `{\n  "mcpServers": {\n    "firebase": {\n      "command": "npx",\n      "args": ["-y", "@modelcontextprotocol/server-firebase"]\n    }\n  }\n}`,
  },
  "exa-search": {
    icon: Sparkles, iconColor: "from-teal-500 to-emerald-600", author: "Exa", rating: 4.9,
    tools: ["neural_search", "find_similar_pages", "extract_page_content"],
    resources: ["exa://results"],
    mcpJsonConfig: `{\n  "mcpServers": {\n    "exa-search": {\n      "command": "npx",\n      "args": ["-y", "@modelcontextprotocol/server-exa"]\n    }\n  }\n}`,
  },
  elasticsearch: {
    icon: Database, iconColor: "from-teal-400 to-blue-500", author: "Elasticsearch", rating: 4.6,
    tools: ["query_index_documents", "get_cluster_health", "create_search_index"],
    resources: ["elastic://indices"],
    mcpJsonConfig: `{\n  "mcpServers": {\n    "elasticsearch": {\n      "command": "npx",\n      "args": ["-y", "@modelcontextprotocol/server-elasticsearch"]\n    }\n  }\n}`,
  },
};

const getErrorMessage = (err: unknown): string => {
  if (typeof err === "object" && err !== null) {
    const maybeResponse = (err as { response?: { data?: { detail?: string } } }).response;
    if (typeof maybeResponse?.data?.detail === "string") {
      return maybeResponse.data.detail;
    }
    const maybeMessage = (err as { message?: string }).message;
    if (typeof maybeMessage === "string") {
      return maybeMessage;
    }
  }
  return "";
};

export default function McpMarketplacePage() {
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedCategory, setSelectedCategory] = useState<Category>("All");
  const [selectedServer, setSelectedServer] = useState<McpServer | null>(null);
  const [connectingSlugs, setConnectingSlugs] = useState<Set<string>>(new Set());
  const [credentialServer, setCredentialServer] = useState<McpServer | null>(null);
  const [credentialValue, setCredentialValue] = useState("");
  const [credentialServerUrl, setCredentialServerUrl] = useState("");

  const orgId = useOrgStore((s) => s.orgId);

  const { data: connectors } = useMcpListMcpConnectors(orgId ?? "", {
    query: { enabled: !!orgId },
  });

  const { data: employees } = useEmployeesListEmployeesRoute(orgId ?? "", {
    query: { enabled: !!orgId },
  });

  const {
    data: catalog,
    isLoading: catalogLoading,
    isError: catalogError,
    isFetching: catalogFetching,
    refetch: refetchCatalog,
  } = useQuery({
    queryKey: [`/api/organizations/${orgId}/mcp-catalog`],
    queryFn: async () => {
      const token = localStorage.getItem("oh_token");
      const baseUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
      const res = await fetch(`${baseUrl}/api/organizations/${orgId}/mcp-catalog`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw new Error(`Failed to fetch catalog (HTTP ${res.status})`);
      return res.json() as Promise<{ entries: CatalogEntry[] }>;
    },
    enabled: !!orgId,
  });

  const empId = employees?.[0]?.id;

  const connectedSlugs = useMemo(() => {
    const slugs = new Set<string>();
    if (connectors) {
      for (const c of connectors) {
        if (c.is_connected) slugs.add(c.slug);
      }
    }
    return slugs;
  }, [connectors]);

  const queryClient = useQueryClient();
  const createMutation = useMcpCreateMcpConnection();
  const deleteMutation = useMcpDeleteMcpConnection();

  const invalidate = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: [`/api/organizations/${orgId}/mcp-connectors`] });
    queryClient.invalidateQueries({ queryKey: [`/api/organizations/${orgId}/mcp-catalog`] });
  }, [queryClient, orgId]);

  const handleInstallToggle = async (e: React.MouseEvent, server: McpServer) => {
    e.stopPropagation();
    if (!orgId || !empId) {
      toast.error("Organization or employee not loaded.");
      return;
    }

    const connectorInfo = connectors?.find((c) => c.slug === server.id);
    const isCurrentlyInstalled = connectedSlugs.has(server.id);

    if (!isCurrentlyInstalled && connectorInfo) {
      const authTypes = connectorInfo.auth_types ?? [connectorInfo.auth_type ?? ""];
      const supportsPaste = authTypes.some((t) => t === "pat_bearer" || t === "api_key_header");
      if (supportsPaste || connectorInfo.auth_type === "none") {
        setCredentialServer(server);
        setCredentialValue("");
        setCredentialServerUrl("");
        return;
      }
    }

    setConnectingSlugs((prev) => new Set(prev).add(server.id));

    try {
      if (isCurrentlyInstalled) {
        await deleteMutation.mutateAsync({
          orgId,
          empId,
          slug: server.id,
        });
        await invalidate();
        toast.success(`Revoked access to ${server.name}.`);
      } else if (connectorInfo?.auth_type === "oauth2") {
        const token = typeof window !== "undefined" ? localStorage.getItem("oh_token") : null;
        const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
        const url = `${apiUrl}/api/organizations/${orgId}/employees/${empId}/mcp-connections/${server.id}/install?token=${encodeURIComponent(token ?? "")}&redirect_to=${encodeURIComponent(window.location.href)}`;
        window.location.assign(url);
        return;
      }
    } catch (err: unknown) {
      toast.error(`Failed to ${isCurrentlyInstalled ? "disconnect" : "connect"} ${server.name}. ${getErrorMessage(err)}`);
    } finally {
      setConnectingSlugs((prev) => {
        const next = new Set(prev);
        next.delete(server.id);
        return next;
      });
    }
  };

  const handleCredentialConnect = useCallback(async () => {
    if (!orgId || !empId || !credentialServer) {
      return;
    }

    const connectorInfo = connectors?.find((c) => c.slug === credentialServer.id);
    const authTypes = connectorInfo?.auth_types ?? [connectorInfo?.auth_type ?? ""];
    const selectedAuthType = authTypes.find((t) => t === "pat_bearer" || t === "api_key_header") ?? undefined;
    const requiresCustomServerUrl = connectorInfo?.requires_custom_server_url === true;

    if (!credentialValue.trim()) {
      toast.error("Please enter a credential.");
      return;
    }
    if (requiresCustomServerUrl && !credentialServerUrl.trim()) {
      toast.error("Please enter the MCP server URL.");
      return;
    }

    setConnectingSlugs((prev) => new Set(prev).add(credentialServer.id));
    try {
      await createMutation.mutateAsync({
        orgId,
        empId,
        slug: credentialServer.id,
        data: {
          credential: credentialValue.trim(),
          auth_type: selectedAuthType,
          server_url: requiresCustomServerUrl ? credentialServerUrl.trim() : undefined,
          scopes: [],
          org_wide: false,
        },
      });
      await invalidate();
      toast.success(`Successfully installed and authorized ${credentialServer.name}!`);
      setCredentialServer(null);
      setCredentialValue("");
      setCredentialServerUrl("");
    } catch (err: unknown) {
      toast.error(`Failed to connect ${credentialServer.name}. ${getErrorMessage(err)}`);
    } finally {
      setConnectingSlugs((prev) => {
        const next = new Set(prev);
        next.delete(credentialServer.id);
        return next;
      });
    }
  }, [orgId, empId, credentialServer, credentialValue, credentialServerUrl, connectors, createMutation, invalidate]);

  const servers = useMemo((): McpServer[] => {
    if (!catalog?.entries) return [];
    return catalog.entries.map((entry) => {
      const meta = DISPLAY_META[entry.slug];
      const fallbackIcon = Puzzle;
      return {
        id: entry.slug,
        name: entry.name,
        description: entry.description,
        category: entry.category as Category,
        authType: authTypeMap[entry.auth_type] ?? "API Key",
        url: entry.docs_url,
        icon: meta?.icon ?? fallbackIcon,
        iconColor: meta?.iconColor ?? "from-gray-400 to-gray-500",
        author: meta?.author ?? "Community",
        rating: meta?.rating ?? 4.0,
        tools: meta?.tools ?? [],
        resources: meta?.resources ?? [],
        mcpJsonConfig: meta?.mcpJsonConfig ?? `{\n  "mcpServers": {\n    "${entry.slug}": {\n      "command": "npx",\n      "args": ["-y", "@modelcontextprotocol/server-${entry.slug}"]\n    }\n  }\n}`,
      };
    });
  }, [catalog]);

  const filteredServers = useMemo(() => {
    return servers.filter((server) => {
      const matchesSearch =
        server.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        server.description.toLowerCase().includes(searchQuery.toLowerCase()) ||
        server.author.toLowerCase().includes(searchQuery.toLowerCase());
      const matchesCategory = selectedCategory === "All" || server.category === selectedCategory;
      return matchesSearch && matchesCategory;
    });
  }, [servers, searchQuery, selectedCategory]);

  const categories: Category[] = ["All", "Productivity", "Development", "Data & DBs", "Communication", "AI & Search"];

  return (
    <div className="flex flex-col gap-8 p-8 max-w-7xl mx-auto">
      {/* Header Section */}
      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div className="flex flex-col gap-1.5">
          <div className="flex items-center gap-2">
            <Badge className="bg-primary/10 text-primary border-primary/20 flex items-center gap-1">
              <Flame className="size-3.5 fill-current" />
              Model Context Protocol
            </Badge>
          </div>
          <h1 className="text-3xl font-extrabold tracking-tight text-foreground bg-gradient-to-r from-foreground via-foreground/90 to-foreground/75 bg-clip-text">
            MCP Integration Directory & Marketplace
          </h1>
          <p className="text-muted-foreground text-sm max-w-2xl">
            Explore, preview, and test 30+ official and community MCP servers to extend the resource capabilities and execution tools of your AI agent team.
          </p>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <div className="flex flex-col gap-4 md:flex-row md:items-center justify-between bg-muted/20 p-4 rounded-xl backdrop-blur-sm">
        <div className="relative flex-1 max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-muted-foreground" />
          <Input
            placeholder="Search MCP servers (e.g., GitHub, Slack, Postgres)..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-9 bg-background/50 border-muted"
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery("")}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
            >
              <X className="size-4" />
            </button>
          )}
        </div>

        {/* Categories Carousel / Tabs */}
        <div className="flex flex-wrap gap-1.5">
          {categories.map((category) => (
            <button
              key={category}
              onClick={() => setSelectedCategory(category)}
              className={`px-3 py-1.5 text-xs font-semibold rounded-lg transition-all ${
                selectedCategory === category
                  ? "bg-primary text-primary-foreground shadow-sm"
                  : "bg-muted text-muted-foreground hover:text-foreground hover:bg-muted/80"
              }`}
            >
              {category}
            </button>
          ))}
        </div>
      </div>

      {/* Grid count summary */}
      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <span>Showing {filteredServers.length} of {servers.length} MCP servers</span>
      </div>

      {!catalogLoading && !catalogError && !empId ? (
        <div className="flex items-start gap-3 rounded-xl border border-amber-500/25 bg-amber-500/5 p-4 text-sm">
          <Bot className="mt-0.5 size-5 shrink-0 text-amber-600 dark:text-amber-400" />
          <div>
            <p className="font-semibold text-foreground">Browse first, connect after creating an AI employee</p>
            <p className="mt-1 text-xs text-muted-foreground">
              The complete MCP directory is available now. Create an employee before connecting a server so OpenHuman knows which coworker should receive its tools.
            </p>
          </div>
        </div>
      ) : null}

      {/* MCP Servers Grid */}
      {catalogLoading ? (
        <div className="flex items-center justify-center p-16">
          <Loader2 className="size-8 animate-spin text-muted-foreground" />
        </div>
      ) : catalogError ? (
        <div className="flex flex-col items-center justify-center p-16 text-center border border-dashed border-destructive/40 rounded-xl bg-destructive/5">
          <AlertCircle className="size-12 text-destructive/70 mb-3" />
          <h3 className="font-semibold text-lg text-foreground">MCP directory could not be loaded</h3>
          <p className="text-sm text-muted-foreground max-w-md mt-1">
            The marketplace service did not return its catalog. Retry the request instead of treating this as an empty directory.
          </p>
          <Button variant="outline" size="sm" onClick={() => refetchCatalog()} disabled={catalogFetching} className="mt-4">
            {catalogFetching ? <Loader2 className="mr-2 size-3.5 animate-spin" /> : null}
            Retry loading
          </Button>
        </div>
      ) : filteredServers.length > 0 ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {filteredServers.map((server) => {
            const isInstalled = connectedSlugs.has(server.id);
            const isLoading = connectingSlugs.has(server.id);

            return (
              <Card
                key={server.id}
                onClick={() => setSelectedServer(server)}
                className="group relative flex flex-col justify-between overflow-hidden border border-border/60 bg-card hover:border-primary/40 hover:shadow-[0_8px_30px_rgb(0,0,0,0.04)] dark:hover:shadow-[0_8px_30px_rgba(0,0,0,0.2)] transition-all duration-300 rounded-xl cursor-pointer"
              >
                <div className="absolute inset-0 bg-gradient-to-r from-primary/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300 pointer-events-none" />

                <CardHeader className="flex flex-row items-start gap-4 p-5 pb-3">
                  <div className="flex size-12 shrink-0 items-center justify-center rounded-xl bg-muted/20 border border-border/80 shadow-sm overflow-hidden p-2">
                    <BrandLogo slug={server.id} className="size-full" />
                  </div>

                  <div className="flex flex-col gap-1 min-w-0">
                    <div className="flex items-center gap-1.5">
                      <span className="font-semibold text-foreground truncate group-hover:text-primary transition-colors">
                        {server.name}
                      </span>
                    </div>
                    <span className="text-[10px] text-muted-foreground/80 font-medium">
                      by {server.author} • Rating: {server.rating}
                    </span>
                  </div>
                </CardHeader>

                <CardContent className="px-5 py-2 flex-1">
                  <p className="text-xs text-muted-foreground line-clamp-3 leading-relaxed">
                    {server.description}
                  </p>
                </CardContent>

                <CardFooter className="flex items-center justify-between border-t border-muted/30 p-4 bg-muted/10 group-hover:bg-muted/20 transition-colors">
                  <div className="flex gap-1">
                    <Badge variant="secondary" className="text-[9px] px-1.5 py-0.5 border border-muted/50 bg-background/50 font-medium">
                      {server.category}
                    </Badge>
                    <Badge variant="outline" className="text-[9px] px-1.5 py-0.5 border border-muted-foreground/20 font-medium text-muted-foreground">
                      {server.authType}
                    </Badge>
                  </div>

                  <Button
                    size="sm"
                    variant={isInstalled ? "outline" : "default"}
                    disabled={isLoading || !empId}
                    onClick={(e) => handleInstallToggle(e, server)}
                    title={!empId ? "Create an AI employee before connecting MCP tools" : undefined}
                    className={`h-7 px-3 text-[10px] font-bold transition-all rounded-md shrink-0 flex items-center gap-1 ${
                      isInstalled
                        ? "border-emerald-500/20 text-emerald-600 bg-emerald-500/5 hover:bg-emerald-500/10 hover:text-emerald-700 dark:text-emerald-400 dark:bg-emerald-500/10"
                        : ""
                    }`}
                  >
                    {isLoading ? (
                      <>
                        <Loader2 className="size-3 animate-spin" />
                        {isInstalled ? "Revoking..." : "Connecting..."}
                      </>
                    ) : isInstalled ? (
                      <>
                        <CheckCircle className="size-3.5 fill-current" />
                        Connected
                      </>
                    ) : (
                      <>
                        {empId ? <Download className="size-3" /> : <Bot className="size-3" />}
                        {empId ? "Connect" : "Create employee first"}
                      </>
                    )}
                  </Button>
                </CardFooter>
              </Card>
            );
          })}
        </div>
      ) : (
        <div className="flex flex-col items-center justify-center p-16 text-center border border-dashed border-border rounded-xl bg-muted/10">
          <Puzzle className="size-12 text-muted-foreground/40 mb-3 animate-pulse" />
          <h3 className="font-semibold text-lg text-foreground">No MCP servers found</h3>
          <p className="text-sm text-muted-foreground max-w-sm mt-1">
            We could not find any MCP servers matching <code>{searchQuery}</code> under the category {selectedCategory}. Try revising your terms.
          </p>
          <Button variant="outline" size="sm" onClick={() => { setSearchQuery(""); setSelectedCategory("All"); }} className="mt-4">
            Reset Filters
          </Button>
        </div>
      )}

      <Dialog open={credentialServer !== null} onOpenChange={(open) => { if (!open) { setCredentialServer(null); setCredentialValue(""); setCredentialServerUrl(""); } }}>
        {credentialServer ? (
          <DialogContent className="sm:max-w-md">
            <DialogHeader>
              <DialogTitle>Connect {credentialServer.name}</DialogTitle>
              <DialogDescription>
                {connectors?.find((c) => c.slug === credentialServer.id)?.requires_custom_server_url
                  ? "Paste your MCP server URL and access token to connect this integration."
                  : "Paste your access token or API key to connect this integration."}
              </DialogDescription>
            </DialogHeader>
            <div className="flex flex-col gap-4 py-4">
              {connectors?.find((c) => c.slug === credentialServer.id)?.requires_custom_server_url ? (
                <div className="flex flex-col gap-1.5">
                  <span className="text-sm font-medium">MCP Server URL</span>
                  <Input
                    type="url"
                    placeholder="https://your-n8n-instance.com/mcp-server/http"
                    value={credentialServerUrl}
                    onChange={(e) => setCredentialServerUrl(e.target.value)}
                  />
                </div>
              ) : null}
              <div className="flex flex-col gap-1.5">
                <span className="text-sm font-medium">Credential</span>
                <Input
                  type="password"
                  placeholder={credentialServer.id === "n8n" ? "n8n_pat_..." : "Enter token…"}
                  value={credentialValue}
                  onChange={(e) => setCredentialValue(e.target.value)}
                />
              </div>
            </div>
            <DialogFooter>
              <Button variant="ghost" onClick={() => { setCredentialServer(null); setCredentialValue(""); setCredentialServerUrl(""); }}>
                Cancel
              </Button>
              <Button onClick={handleCredentialConnect} disabled={credentialServer ? connectingSlugs.has(credentialServer.id) : false}>
                {credentialServer && connectingSlugs.has(credentialServer.id) ? "Connecting..." : "Connect"}
              </Button>
            </DialogFooter>
          </DialogContent>
        ) : null}
      </Dialog>

      {/* MCP Server Inspector Dialog Modal */}
      <Dialog open={selectedServer !== null} onOpenChange={(open) => !open && setSelectedServer(null)}>
        {selectedServer && (
          <DialogContent className="max-w-2xl overflow-hidden rounded-xl border border-border bg-card">
            <DialogHeader className="flex flex-row items-center gap-4 border-b border-muted/50 pb-4">
              <div className="flex size-14 items-center justify-center rounded-xl bg-muted/25 border border-border shadow-md overflow-hidden p-2.5">
                <BrandLogo slug={selectedServer.id} className="size-full" />
              </div>
              <div className="flex flex-col gap-1 min-w-0">
                <DialogTitle className="text-xl font-bold text-foreground">
                  {selectedServer.name}
                </DialogTitle>
                <DialogDescription className="text-xs text-muted-foreground">
                  Official MCP Server by {selectedServer.author} • Rating: {selectedServer.rating}/5.0
                </DialogDescription>
              </div>
            </DialogHeader>

            <div className="flex flex-col gap-5 py-4 max-h-[60vh] overflow-y-auto pr-1">
              <div className="flex flex-col gap-1.5">
                <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground/80">Description</h4>
                <p className="text-sm text-foreground leading-relaxed">
                  {selectedServer.description}
                </p>
              </div>

              <div className="grid grid-cols-2 gap-4 bg-muted/30 border border-border p-3 rounded-lg text-xs">
                <div className="flex flex-col gap-1">
                  <span className="font-medium text-muted-foreground">Endpoint Base URL</span>
                  <code className="text-[11px] font-mono text-primary select-all truncate">
                    {selectedServer.url}
                  </code>
                </div>
                <div className="flex flex-col gap-1">
                  <span className="font-medium text-muted-foreground">Authentication Protocol</span>
                  <span className="font-semibold text-foreground flex items-center gap-1.5">
                    <Badge variant="outline" className="text-[10px] py-0.5 px-1.5">
                      {selectedServer.authType}
                    </Badge>
                  </span>
                </div>
              </div>

              <div className="flex flex-col gap-2">
                <div className="flex items-center gap-1.5">
                  <Code className="size-4 text-primary" />
                  <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground/80">Exposed Server Tools ({selectedServer.tools.length})</h4>
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {selectedServer.tools.map((tool) => (
                    <Badge key={tool} variant="secondary" className="font-mono text-[10px] px-2 py-0.5 border border-muted">
                      {tool}
                    </Badge>
                  ))}
                </div>
              </div>

              <div className="flex flex-col gap-2">
                <div className="flex items-center gap-1.5">
                  <Layers className="size-4 text-primary" />
                  <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground/80">Exposed Resource Schemas</h4>
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {selectedServer.resources.map((res) => (
                    <Badge key={res} variant="outline" className="font-mono text-[10px] px-2 py-0.5 border-dashed border-primary/20 text-primary bg-primary/5">
                      {res}
                    </Badge>
                  ))}
                </div>
              </div>

              <div className="flex flex-col gap-2">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-1.5">
                    <Terminal className="size-4 text-primary" />
                    <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground/80">mcp.json Configuration block</h4>
                  </div>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => {
                      navigator.clipboard.writeText(selectedServer.mcpJsonConfig);
                      toast.success("Configuration copied to clipboard!");
                    }}
                    className="h-6 px-2 text-[10px] text-muted-foreground hover:text-foreground"
                  >
                    Copy code
                  </Button>
                </div>
                <pre className="p-3 bg-neutral-900 dark:bg-black border border-neutral-800 dark:border-neutral-900 rounded-lg overflow-x-auto text-[10px] font-mono text-zinc-300">
                  {selectedServer.mcpJsonConfig}
                </pre>
              </div>
            </div>

            <DialogFooter className="border-t border-muted/50 pt-4 flex sm:justify-between items-center">
              <span className="text-[10px] text-muted-foreground hidden sm:inline">
                Learn more at <a href="https://modelcontextprotocol.io" target="_blank" rel="noreferrer" className="text-primary hover:underline inline-flex items-center gap-0.5">modelcontextprotocol.io <ExternalLink className="size-2.5" /></a>
              </span>
              <div className="flex gap-2 w-full sm:w-auto">
                <Button variant="outline" size="sm" onClick={() => setSelectedServer(null)} className="flex-1 sm:flex-none">
                  Close
                </Button>
                <Button
                  size="sm"
                  disabled={connectingSlugs.has(selectedServer.id) || !empId}
                  title={!empId ? "Create an AI employee before connecting MCP tools" : undefined}
                  onClick={(e) => {
                    handleInstallToggle(e, selectedServer);
                    setSelectedServer(null);
                  }}
                  className={`flex-1 sm:flex-none ${
                    connectedSlugs.has(selectedServer.id) ? "bg-emerald-600 hover:bg-emerald-700" : ""
                  }`}
                >
                  {connectingSlugs.has(selectedServer.id) ? (
                    <><Loader2 className="size-3 animate-spin mr-1" />Working...</>
                  ) : connectedSlugs.has(selectedServer.id) ? (
                    "Disconnect"
                  ) : (
                    empId ? "Connect Server" : "Create employee first"
                  )}
                </Button>
              </div>
            </DialogFooter>
          </DialogContent>
        )}
      </Dialog>
    </div>
  );
}
