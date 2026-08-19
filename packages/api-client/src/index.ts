export { customInstance, ApiError } from "./mutator/custom-instance";

export {
  useSchedulesListSchedulesRoute,
  useSchedulesCreateScheduleRoute,
  useSchedulesUpdateScheduleRoute,
  useSchedulesDeleteScheduleRoute,
  useSchedulesRunScheduleRoute,
  schedulesListSchedulesRoute,
  schedulesCreateScheduleRoute,
  schedulesUpdateScheduleRoute,
  schedulesDeleteScheduleRoute,
  schedulesRunScheduleRoute,
  schedulesListScheduleRunsRoute,
  getSchedulesListSchedulesRouteQueryKey,
} from "./api/schedules/schedules";

// Health
export {
  useHealthHealthCheck,
  getHealthHealthCheckQueryKey,
  getHealthHealthCheckQueryOptions,
  healthHealthCheck,
} from "./api/health/health";

export type {
  HealthHealthCheckQueryResult,
  HealthHealthCheckQueryError,
} from "./api/health/health";

// Auth
export {
  useAuthMe,
  useAuthUpdateMe,
  getAuthMeQueryKey,
  getAuthMeQueryOptions,
  getAuthUpdateMeMutationOptions,
  authMe,
  authUpdateMe,
} from "./api/auth/auth";

export type {
  AuthMeQueryResult,
  AuthMeQueryError,
} from "./api/auth/auth";

// Employees
export {
  useEmployeesCreateEmployeeRoute,
  useEmployeesListEmployeesRoute,
  useEmployeesGetEmployeeRoute,
  useEmployeesUpdateEmployeeRoute,
  useEmployeesDeleteEmployeeRoute,
  useEmployeesSetDiscordToken,
  useEmployeesSetSlackToken,
  useEmployeesSetStatus,
  getEmployeesCreateEmployeeRouteMutationOptions,
  getEmployeesListEmployeesRouteQueryKey,
  getEmployeesListEmployeesRouteQueryOptions,
  getEmployeesGetEmployeeRouteQueryKey,
  getEmployeesGetEmployeeRouteQueryOptions,
  getEmployeesUpdateEmployeeRouteMutationOptions,
  getEmployeesDeleteEmployeeRouteMutationOptions,
  getEmployeesSetDiscordTokenMutationOptions,
  getEmployeesSetSlackTokenMutationOptions,
  getEmployeesSetStatusMutationOptions,
  employeesCreateEmployeeRoute,
  employeesListEmployeesRoute,
  employeesGetEmployeeRoute,
  employeesUpdateEmployeeRoute,
  employeesDeleteEmployeeRoute,
  employeesSetDiscordToken,
  employeesSetSlackToken,
  employeesSetStatus,
} from "./api/employees/employees";

export type {
  EmployeesCreateEmployeeRouteMutationResult,
  EmployeesCreateEmployeeRouteMutationBody,
  EmployeesCreateEmployeeRouteMutationError,
  EmployeesListEmployeesRouteQueryResult,
  EmployeesListEmployeesRouteQueryError,
  EmployeesGetEmployeeRouteQueryResult,
  EmployeesGetEmployeeRouteQueryError,
  EmployeesUpdateEmployeeRouteMutationResult,
  EmployeesUpdateEmployeeRouteMutationBody,
  EmployeesUpdateEmployeeRouteMutationError,
  EmployeesDeleteEmployeeRouteMutationResult,
  EmployeesDeleteEmployeeRouteMutationError,
  EmployeesSetDiscordTokenMutationResult,
  EmployeesSetDiscordTokenMutationBody,
  EmployeesSetDiscordTokenMutationError,
  EmployeesSetSlackTokenMutationResult,
  EmployeesSetSlackTokenMutationBody,
  EmployeesSetSlackTokenMutationError,
  EmployeesSetStatusMutationResult,
  EmployeesSetStatusMutationBody,
  EmployeesSetStatusMutationError,
} from "./api/employees/employees";

// Organizations
export {
  useOrganizationsListOrganizations,
  useOrganizationsCreateOrganization,
  useOrganizationsGetOrganization,
  useOrganizationsUpdateOrganization,
  useOrganizationsDeleteOrganization,
  getOrganizationsListOrganizationsQueryKey,
  getOrganizationsListOrganizationsQueryOptions,
  getOrganizationsCreateOrganizationMutationOptions,
  getOrganizationsGetOrganizationQueryKey,
  getOrganizationsGetOrganizationQueryOptions,
  getOrganizationsUpdateOrganizationMutationOptions,
  getOrganizationsDeleteOrganizationMutationOptions,
  organizationsListOrganizations,
  organizationsCreateOrganization,
  organizationsGetOrganization,
  organizationsUpdateOrganization,
  organizationsDeleteOrganization,
} from "./api/organizations/organizations";

export type {
  OrganizationsListOrganizationsQueryResult,
  OrganizationsListOrganizationsQueryError,
  OrganizationsCreateOrganizationMutationResult,
  OrganizationsCreateOrganizationMutationBody,
  OrganizationsCreateOrganizationMutationError,
  OrganizationsGetOrganizationQueryResult,
  OrganizationsGetOrganizationQueryError,
  OrganizationsUpdateOrganizationMutationResult,
  OrganizationsUpdateOrganizationMutationBody,
  OrganizationsUpdateOrganizationMutationError,
  OrganizationsDeleteOrganizationMutationResult,
  OrganizationsDeleteOrganizationMutationError,
} from "./api/organizations/organizations";

// Documents
export {
  useDocumentsUploadDocument,
  useDocumentsListOrgDocuments,
  useDocumentsGetDocumentRoute,
  useDocumentsDeleteDocumentRoute,
  useDocumentsDownloadDocument,
  useDocumentsGetOrgDocumentsStats,
  getDocumentsUploadDocumentMutationOptions,
  getDocumentsListOrgDocumentsQueryKey,
  getDocumentsListOrgDocumentsQueryOptions,
  getDocumentsGetDocumentRouteQueryKey,
  getDocumentsGetDocumentRouteQueryOptions,
  getDocumentsDeleteDocumentRouteMutationOptions,
  getDocumentsDownloadDocumentQueryKey,
  getDocumentsDownloadDocumentQueryOptions,
  getDocumentsGetOrgDocumentsStatsQueryKey,
  getDocumentsGetOrgDocumentsStatsQueryOptions,
  documentsUploadDocument,
  documentsListOrgDocuments,
  documentsGetDocumentRoute,
  documentsDeleteDocumentRoute,
  documentsDownloadDocument,
  documentsGetOrgDocumentsStats,
} from "./api/documents/documents";

export type {
  DocumentsUploadDocumentMutationResult,
  DocumentsUploadDocumentMutationBody,
  DocumentsUploadDocumentMutationError,
  DocumentsListOrgDocumentsQueryResult,
  DocumentsListOrgDocumentsQueryError,
  DocumentsGetDocumentRouteQueryResult,
  DocumentsGetDocumentRouteQueryError,
  DocumentsDeleteDocumentRouteMutationResult,
  DocumentsDeleteDocumentRouteMutationError,
  DocumentsDownloadDocumentQueryResult,
  DocumentsDownloadDocumentQueryError,
  DocumentsGetOrgDocumentsStatsQueryResult,
  DocumentsGetOrgDocumentsStatsQueryError,
} from "./api/documents/documents";

// MCP
export {
  useMcpListMcpConnectors,
  useMcpListEmployeeMcpConnections,
  useMcpCreateMcpConnection,
  useMcpDeleteMcpConnection,
  useMcpMcpOauthInstall,
  useMcpMcpOauthCallback,
  getMcpListMcpConnectorsQueryKey,
  getMcpListEmployeeMcpConnectionsQueryKey,
  getMcpMcpOauthInstallQueryKey,
  getMcpMcpOauthCallbackQueryKey,
  mcpListMcpConnectors,
  mcpListEmployeeMcpConnections,
  mcpCreateMcpConnection,
  mcpDeleteMcpConnection,
  mcpMcpOauthInstall,
  mcpMcpOauthCallback,
} from "./api/mcp/mcp";

export type {
  McpListMcpConnectorsQueryResult,
  McpListMcpConnectorsQueryError,
  McpListEmployeeMcpConnectionsQueryResult,
  McpListEmployeeMcpConnectionsQueryError,
  McpCreateMcpConnectionMutationResult,
  McpCreateMcpConnectionMutationBody,
  McpCreateMcpConnectionMutationError,
  McpDeleteMcpConnectionMutationResult,
  McpDeleteMcpConnectionMutationError,
  McpMcpOauthInstallQueryResult,
  McpMcpOauthInstallQueryError,
  McpMcpOauthCallbackQueryResult,
  McpMcpOauthCallbackQueryError,
} from "./api/mcp/mcp";

// Schemas
export type {
  HealthResponse,
  UpdateUserRequest,
  UserResponse,
  HTTPValidationError,
  EmployeeResponse,
  CreateEmployeeRequest,
  UpdateEmployeeRequest,
  StatusRequest,
  DiscordTokenRequest,
  SlackTokenRequest,
  OrganizationResponse,
  CreateOrganizationRequest,
  UpdateOrganizationRequest,
  BodyDocumentsUploadDocument,
  DocumentResponse,
  DocumentsGetOrgDocumentsStatsParams,
  DocumentsListOrgDocumentsParams,
  DocumentsStatsResponse,
  ConnectorStatus,
  McpConnectionRead,
  McpConnectionCreate,
  McpConnectionList,
  McpMcpOauthCallbackParams,
  McpMcpOauthInstallParams,
  ScheduleCreate,
  ScheduleUpdate,
  ScheduleResponse,
  ScheduleRunResponse,
} from "./schemas";
