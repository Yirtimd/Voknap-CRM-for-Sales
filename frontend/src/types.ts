export type Tenant = {
  id: string;
  name: string;
  slug: string;
};

export type MembershipRole = "owner" | "admin" | "sales_manager" | "sales_rep" | "viewer";

export type Permission =
  | "crm:read"
  | "crm:write"
  | "sales:manage"
  | "assignments:manage"
  | "ai:use"
  | "knowledge:write"
  | "integrations:manage"
  | "templates:manage"
  | "settings:read"
  | "audit:read"
  | "feature_flags:manage"
  | "billing:manage"
  | "data:export"
  | "members:manage"
  | "automations:manage"
  | "approvals:manage";

export type EntityType = "contacts" | "leads" | "deals" | "tasks" | "notes";

export type EntityVersion = {
  id: string;
  version: number;
};

export type Pagination = {
  page: number;
  pageSize: number;
  total: number;
  totalPages: number;
};

export type FieldChange = {
  id: string;
  entity_type: EntityType;
  entity_id: string;
  field_name: string;
  old_value: unknown | null;
  new_value: unknown | null;
  changed_by_id: string;
  entity_version: number;
  created_at: string;
};

export type LifecycleResult = EntityVersion & {
  is_archived: boolean;
  deleted_at: string | null;
};

export type BulkAction = "archive" | "unarchive" | "delete" | "restore" | "reassign";

export type BulkActionRequest = {
  action: BulkAction;
  items: EntityVersion[];
  owner_id?: string | null;
};

export type BulkActionResult = {
  affected: number;
  action: BulkAction;
};

export type MergeRequest = {
  target_version: number;
  sources: EntityVersion[];
};

export type MergeResult = {
  target_id: string;
  merged_ids: string[];
  version: number;
};

export type DuplicateCandidate = {
  id: string;
  entity_type: "contacts" | "leads" | "deals";
  record_a_id: string;
  record_b_id: string;
  score: number;
  matched_fields: string[];
  status: "open" | "dismissed" | "merged";
  version: number;
  detected_at: string;
  resolved_at: string | null;
};

export type LeadConversionRequest = {
  version: number;
  stage_id: string;
  title?: string | null;
  amount?: number | null;
  owner_id?: string | null;
};

export type Me = {
  user_id: string;
  email: string;
  full_name: string;
  tenant_id: string;
  role: MembershipRole;
  permissions: Permission[];
};

export type Membership = {
  id: string;
  user_id: string;
  email: string;
  full_name: string;
  role: MembershipRole;
  is_active: boolean;
  team_id: string | null;
  manager_membership_id: string | null;
  deactivated_at: string | null;
  created_at: string;
};

export type TeamInvitation = {
  id: string;
  email: string;
  role: MembershipRole;
  team_id: string | null;
  manager_membership_id: string | null;
  expires_at: string;
  accepted_at: string | null;
  revoked_at: string | null;
  created_at: string;
  token: string | null;
};

export type SalesTeam = {
  id: string;
  name: string;
  manager_membership_id: string | null;
  is_active: boolean;
  member_count: number;
  created_at: string;
};

export type LeadQueue = {
  id: string;
  name: string;
  team_id: string | null;
  strategy: "manual" | "round_robin";
  membership_ids: string[];
  is_active: boolean;
  created_at: string;
};

export type Territory = {
  id: string;
  name: string;
  country_code: string | null;
  region: string | null;
  industry: string | null;
  owner_membership_id: string | null;
  team_id: string | null;
  priority: number;
  is_active: boolean;
  created_at: string;
};

export type AssignmentTargetType = "member" | "team" | "queue" | "territory";

export type AssignmentRule = {
  id: string;
  name: string;
  entity_type: "lead" | "company";
  criteria: Record<string, string>;
  target_type: AssignmentTargetType;
  target_id: string;
  priority: number;
  is_active: boolean;
  created_at: string;
};

export type InvitationAcceptResponse = {
  access_token: string;
  token_type: string;
  user_id: string;
  tenant_id: string;
};

export type AuthResponse = {
  access_token: string;
  token_type: string;
  user_id: string;
  tenants: Tenant[];
};

export type Contact = {
  id: string;
  company_id: string;
  name: string;
  phone: string | null;
  email: string | null;
  company_name: string | null;
  role?: string | null;
  owner_id?: string | null;
  actions?: {
    call: boolean;
    email: boolean;
    more: boolean;
  };
  is_archived: boolean;
  deleted_at: string | null;
  version: number;
  created_at?: string;
  updated_at?: string;
};

export type Owner = {
  id: string | null;
  name: string | null;
  avatar_url: string | null;
  initials: string | null;
};

export type Company = {
  id: string;
  name: string;
  website: string | null;
  industry: string | null;
  description: string | null;
  status: string;
  status_label?: string | null;
  company_type?: string | null;
  health_score?: number | null;
  client_since?: string | null;
  source?: string | null;
  owner?: Owner | null;
  next_action_id?: string | null;
  created_at: string;
};

export type Lead = {
  id: string;
  company_id: string;
  title: string;
  source: string | null;
  status: string;
  contact_id: string | null;
  owner_id?: string | null;
  score?: number | null;
  score_grade?: "hot" | "warm" | "cold" | null;
  score_factors?: ScoreFactor[];
  score_model_version?: string | null;
  score_updated_at?: string | null;
  qualified_at?: string | null;
  converted_at?: string | null;
  converted_deal_id?: string | null;
  disqualification_reason?: string | null;
  is_archived: boolean;
  deleted_at: string | null;
  version: number;
  created_at?: string;
  updated_at?: string;
};

export type PipelineStage = {
  id: string;
  name: string;
  sort_order: number;
  code: string;
  probability: number;
  stage_type: "open" | "won" | "lost";
  is_active: boolean;
  required_fields: string[];
};

export type Pipeline = {
  id: string;
  name: string;
  description: string | null;
  is_active: boolean;
  is_default: boolean;
  version: number;
  stages: PipelineStage[];
  created_at?: string;
  updated_at?: string;
};

export type Deal = {
  id: string;
  company_id: string;
  title: string;
  amount: number | null;
  discount_percent?: number | null;
  status: string;
  lead_id: string | null;
  stage_id: string;
  probability?: number | null;
  expected_close_date?: string | null;
  expected_next_event?: string | null;
  next_step?: string | null;
  risk_level?: string | null;
  forecast_category?: string | null;
  opportunity_score?: number | null;
  score_grade?: "hot" | "warm" | "cold" | null;
  score_factors?: ScoreFactor[];
  forecast_probability?: number | null;
  probability_source?: "scoring" | "stage_or_manual";
  score_model_version?: string | null;
  score_updated_at?: string | null;
  owner_id?: string | null;
  next_action_id?: string | null;
  age_days?: number | null;
  is_archived: boolean;
  deleted_at: string | null;
  version: number;
  created_at?: string;
  updated_at?: string;
};

export type AutomationTriggerType =
  | "lead.created"
  | "lead.score_changed"
  | "deal.created"
  | "deal.updated"
  | "deal.stage_changed"
  | "deal.score_changed"
  | "communication.created"
  | "schedule.deal_inactive";

export type ScoreFactor = {
  key: string;
  label: string;
  points: number;
  max_points: number;
  signal: string;
};

export type AutomationConditionOperator =
  | "eq"
  | "neq"
  | "gt"
  | "gte"
  | "lt"
  | "lte"
  | "in"
  | "contains"
  | "is_empty";

export type AutomationActionType =
  | "assign_owner"
  | "create_task"
  | "send_template"
  | "request_approval"
  | "update_next_action";

export type AutomationCondition = {
  field: string;
  operator: AutomationConditionOperator;
  value?: unknown;
};

export type AutomationAction = {
  type: AutomationActionType;
  config: Record<string, unknown>;
};

export type AutomationWorkflow = {
  id: string;
  name: string;
  description: string | null;
  trigger_type: AutomationTriggerType;
  conditions: AutomationCondition[];
  condition_logic: "all" | "any";
  actions: AutomationAction[];
  priority: number;
  is_active: boolean;
  version: number;
  created_by_id: string;
  updated_by_id: string;
  created_at: string;
  updated_at: string;
};

export type AutomationMessageTemplate = {
  id: string;
  name: string;
  channel: string;
  subject: string;
  body: string;
  is_active: boolean;
  created_by_id: string;
  created_at: string;
  updated_at: string;
};

export type AutomationRun = {
  id: string;
  workflow_id: string;
  event_key: string;
  trigger_type: string;
  entity_type: string;
  entity_id: string;
  actor_id: string | null;
  status: string;
  result: Array<Record<string, unknown>>;
  error: string | null;
  started_at: string;
  completed_at: string | null;
};

export type ApprovalRequest = {
  id: string;
  workflow_id: string;
  run_id: string;
  entity_type: string;
  entity_id: string;
  title: string;
  reason: string | null;
  requested_by_id: string | null;
  assigned_to_id: string | null;
  status: string;
  priority: "low" | "normal" | "high" | "critical";
  due_at: string | null;
  version: number;
  decision_comment: string | null;
  decided_by_id: string | null;
  decided_at: string | null;
  created_at: string;
  updated_at: string;
};

export type ApprovalHistory = {
  id: string;
  approval_id: string;
  action: string;
  from_status: string | null;
  to_status: string | null;
  actor_id: string | null;
  comment: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
};

export type AutomationOutboxItem = {
  id: string;
  run_id: string;
  template_id: string;
  entity_type: string;
  entity_id: string;
  channel: string;
  recipient: string;
  subject: string;
  body: string;
  status: string;
  attempts: number;
  available_at: string;
  sent_at: string | null;
  last_error: string | null;
  created_at: string;
};

export type ScheduledAutomationResult = {
  evaluated: number;
  matched_runs: number;
};

export type LeadConversionResponse = {
  lead: Lead;
  deal: Deal;
};

export type Task = {
  id: string;
  company_id: string;
  title: string;
  description: string | null;
  deal_id: string | null;
  assigned_to_id: string;
  status: string;
  priority: string;
  due_at: string | null;
  done_at: string | null;
  is_archived: boolean;
  deleted_at: string | null;
  version: number;
  created_at?: string;
  updated_at?: string;
};

export type Note = {
  id: string;
  company_id: string;
  text: string;
  lead_id: string | null;
  deal_id: string | null;
  author_id?: string;
  is_archived: boolean;
  deleted_at: string | null;
  version: number;
  created_at?: string;
  updated_at?: string;
};

export type KnowledgeDocument = {
  id: string;
  company_id?: string | null;
  deal_id?: string | null;
  file_id?: string | null;
  title: string;
  source_type: string;
  visibility?: string;
  status: string;
  created_at: string;
  chunks_count: number;
  download_url?: string | null;
  extraction_method?: string;
  source_pages?: number | null;
};

export type KnowledgeSearchResult = {
  chunk_id: string;
  document_id: string;
  document_title: string;
  document_scope?: string;
  company_id?: string | null;
  deal_id?: string | null;
  page_number?: number | null;
  text: string;
  score: number;
  chunk_index: number;
  retrieval_method?: "hybrid" | "semantic" | "lexical";
};

export type KnowledgeAskResponse = {
  query_id: string;
  answer: string;
  citations: KnowledgeSearchResult[];
  scope: "global" | "company" | "deal";
  company_id: string | null;
  deal_id: string | null;
  document_id: string | null;
  include_global: boolean;
  retrieval_mode: string;
};

export type AgentContext = {
  type: "workspace" | "knowledge" | "company" | "deal" | "document";
  company_id: string | null;
  deal_id: string | null;
  document_id: string | null;
  include_global: boolean;
  page_path?: string | null;
};

export type AgentSource = {
  document_id: string;
  document_title: string;
  document_scope: string;
  company_id: string | null;
  deal_id: string | null;
  chunk_id: string;
  chunk_index: number;
  page_number: number | null;
  score: number;
  text: string;
  retrieval_method: "hybrid" | "semantic" | "lexical";
  download_url: string | null;
};

export type AgentAction = {
  id: string;
  action_type: string;
  status: string;
  payload: Record<string, unknown>;
  result: Record<string, unknown> | null;
  created_at: string;
  confirmed_at: string | null;
};

export type AgentChatResponse = {
  message_id: string;
  query_id: string | null;
  answer: string;
  actions: AgentAction[];
  sources: AgentSource[];
  intent: string;
  context: AgentContext;
};

export type CompanyCopilot = {
  company_id: string;
  summary: string;
  next_best_action: string;
  deal_risk: {
    level: string;
    score: number;
    reason: string;
  };
  follow_up_draft: string;
  meeting_prep: string;
  insight: Record<string, unknown>;
  actions: AgentAction[];
};

export type HomeCopilot = {
  generated_at: string;
  source: "backend_copilot";
  title: string;
  rationale: string;
  company_id: string | null;
  company_name: string | null;
  deal_id: string | null;
  deal_title: string | null;
  amount: number;
  confidence: number;
  risk_score: number;
  risk_level: string;
  action_label: string;
  primary_url: string;
  details_url: string;
  signals: string[];
  focus_deals: Array<{
    deal_id: string;
    company_id: string;
    company_name: string;
    deal_title: string;
    amount: number;
    stage_name: string;
    confidence: number;
    risk_score: number;
    risk_level: string;
    next_action: string;
  }>;
};

export type AgentHistoryMessage = {
  id: string;
  role: string;
  content: string;
  intent: string;
  context: AgentContext;
  sources: AgentSource[];
  query_id: string | null;
  created_at: string;
};

export type ConnectorDefinition = {
  code: string;
  title: string;
  description: string;
  status: string;
  reason: string | null;
};

export type ConnectorAccount = {
  id: string;
  connector_code: string;
  title: string;
  status: string;
  credentials_encrypted: boolean;
  settings: Record<string, unknown>;
  sync_cursor: string | null;
  last_sync_at: string | null;
  created_at: string;
};

export type ConnectorSyncRun = {
  id: string;
  account_id: string;
  direction: string;
  status: string;
  job_type: string;
  attempt: number;
  max_attempts: number;
  next_retry_at: string | null;
  started_at: string | null;
  finished_at: string | null;
  created_count: number;
  updated_count: number;
  failed_count: number;
  message: string | null;
  error_code: string | null;
  error_details: Record<string, unknown>;
  created_at: string;
};

export type IntegrationJob = {
  id: string;
  account_id: string | null;
  job_type: string;
  idempotency_key: string;
  status: "pending" | "running" | "retry" | "succeeded" | "dead";
  attempt: number;
  max_attempts: number;
  available_at: string;
  completed_at: string | null;
  result: Record<string, unknown>;
  last_error: string | null;
  error_log: Array<Record<string, unknown>>;
  created_at: string;
};

export type WebhookEndpoint = {
  id: string;
  title: string;
  url: string;
  event_types: string[];
  is_active: boolean;
  signing_secret: string | null;
  created_at: string;
};

export type PublicApiKey = {
  id: string;
  title: string;
  key_prefix: string;
  scopes: string[];
  is_active: boolean;
  expires_at: string | null;
  last_used_at: string | null;
  created_at: string;
  api_key: string | null;
};

export type ImportPreview = {
  filename: string;
  headers: string[];
  rows: Array<Record<string, string>>;
  suggested_mapping: Record<string, string>;
  total_rows: number;
};

export type CommunicationEvent = {
  id: string;
  tenant_id: string;
  company_id: string | null;
  contact_id: string | null;
  deal_id: string | null;
  activity_id: string | null;
  connector_account_id: string | null;
  channel: string;
  direction: string;
  status: string;
  external_id: string | null;
  sender: string | null;
  recipient: string | null;
  occurred_at: string;
  subject: string;
  body: string | null;
  metadata: Record<string, unknown>;
  created_by: string | null;
  created_at: string;
  updated_at: string;
};

export type CsvExportResponse = {
  filename: string;
  csv_text: string;
};

export type CompanyTemplate = {
  code: string;
  title: string;
  description: string;
  pipeline_name: string;
  stages: string[];
  lead_sources: string[];
  ai_instruction: string;
};

export type AppliedTemplate = {
  id: string;
  template_code: string;
  template_title: string;
  status: string;
  result: Record<string, unknown>;
  created_at: string;
};

export type ProductionOverview = {
  tenant_id: string;
  counts: Record<string, number>;
  plan: Record<string, unknown>;
  flags: Record<string, unknown>[];
};

export type AuditLog = {
  id: string;
  user_id: string | null;
  action: string;
  entity_type: string | null;
  entity_id: string | null;
  payload: Record<string, unknown>;
  created_at: string;
};

export type FeatureFlag = {
  id: string;
  code: string;
  title: string;
  enabled: boolean;
  created_at: string;
};

export type TenantPlan = {
  id: string;
  plan_code: string;
  users_limit: number;
  leads_limit: number;
  documents_limit: number;
  ai_requests_limit: number;
  created_at: string;
};

export type TenantExport = {
  filename: string;
  data: Record<string, unknown>;
};

export type AnalyticsOverview = {
  generated_at: string;
  forecast: {
    currency: string;
    period_days: number;
    open_pipeline: number;
    due_in_period: number;
    weighted_revenue: number;
    commit_revenue: number;
    best_case_revenue: number;
    pipeline_revenue: number;
    overdue_revenue: number;
      won_revenue: number;
      open_deals: number;
      scoring_coverage_rate: number;
  };
  forecast_by_owner: Array<{
    scope_id: string | null;
    scope_name: string;
    open_deals: number;
    open_pipeline: number;
    due_in_period: number;
    weighted_revenue: number;
    commit_revenue: number;
    overdue_revenue: number;
  }>;
  forecast_by_team: Array<{
    scope_id: string | null;
    scope_name: string;
    open_deals: number;
    open_pipeline: number;
    due_in_period: number;
    weighted_revenue: number;
    commit_revenue: number;
    overdue_revenue: number;
  }>;
  forecast_quality: {
    completeness_rate: number;
    missing_owner: number;
    missing_close_date: number;
    missing_probability: number;
    missing_forecast_category: number;
    missing_opportunity_score: number;
  };
  stage_conversion: Array<{
    pipeline_id: string;
    pipeline_name: string;
    stage_id: string;
    stage_name: string;
    sort_order: number;
    deal_count: number;
    reached_count: number;
    amount: number;
    weighted_amount: number;
    conversion_from_first: number;
    conversion_from_previous: number;
    stuck_count: number;
  }>;
  stuck_deals: Array<{
    deal_id: string;
    title: string;
    company_id: string;
    company_name: string;
    stage_name: string;
    owner_name: string | null;
    amount: number;
    weighted_amount: number;
    days_in_stage: number;
    last_activity_at: string | null;
    risk_level: string;
  }>;
  task_sla: {
    total: number;
    open: number;
    completed: number;
    overdue: number;
    completed_on_time: number;
    completion_rate: number;
    sla_rate: number;
    average_resolution_hours: number | null;
    by_owner: Array<{
      owner_id: string;
      owner_name: string;
      total: number;
      completed: number;
      overdue: number;
      sla_rate: number;
    }>;
  };
  manager_activity: Array<{
    manager_id: string;
    manager_name: string;
    activities: number;
    calls: number;
    emails: number;
    meetings: number;
    notes: number;
    tasks_completed: number;
    tasks_overdue: number;
    open_deals: number;
    pipeline_amount: number;
    weighted_revenue: number;
  }>;
  company_health: Array<{
    company_id: string;
    company_name: string;
    score: number;
    label: string;
    trend: string | null;
    open_deals: number;
    pipeline_amount: number;
    overdue_tasks: number;
    days_since_activity: number | null;
    risk_level: string;
    reasons: string[];
  }>;
  risk_map: {
    high: number;
    medium: number;
    low: number;
    revenue_at_risk: number;
    deals: Array<{
      deal_id: string;
      title: string;
      company_id: string;
      company_name: string;
      stage_name: string;
      owner_name: string | null;
      amount: number;
      weighted_amount: number;
      score: number;
      level: string;
      reasons: string[];
    }>;
  };
};

export type Activity = {
  id: string;
  tenant_id: string;
  company_id: string | null;
  contact_id: string | null;
  deal_id: string | null;
  type: string;
  channel: string | null;
  title: string;
  description: string | null;
  created_by: string | null;
  created_at: string;
  metadata: Record<string, unknown>;
};

export type CompanyHealth = {
  score: number | null;
  label: string | null;
  trend: string | null;
  risk_level: string | null;
  success_chance: number | null;
  success_chance_delta: number | null;
  ai_recommendations: Array<{
    type?: string;
    title: string;
    description?: string;
  }>;
};

export type CompanyFile = {
  id: string;
  name: string;
  file_type: string | null;
  mime_type: string | null;
  file_size: number | null;
  uploaded_at: string;
  download_url: string;
};

export type WorkspaceKnowledgeDocument = {
  id: string;
  title: string;
  source_type: string;
  visibility: string;
  company_id: string | null;
  deal_id: string | null;
  file_id: string | null;
  created_at: string;
  chunks_count: number;
  download_url?: string | null;
  extraction_method?: string;
  source_pages?: number | null;
};

export type WorkspaceActivity = {
  id: string;
  type: string;
  activity_type: string;
  activity_icon: string;
  channel: string | null;
  title: string;
  description: string | null;
  author_name: string | null;
  created_at: string;
  metadata: Record<string, unknown>;
};

export type NextAction = {
  id: string;
  company_id: string;
  deal_id: string | null;
  contact_id: string | null;
  assigned_to_id: string | null;
  title: string;
  description: string | null;
  source: string;
  status: string;
  priority: string;
  due_at: string | null;
  completed_at: string | null;
  created_at: string;
};

export type CompanyWorkspace = {
  company: Company;
  overview: Record<string, number | string | null>;
  health: CompanyHealth;
  next_action: NextAction | null;
  contacts: Contact[];
  deals: Deal[];
  tasks: Task[];
  activities: WorkspaceActivity[];
  files: CompanyFile[];
  knowledge_documents: WorkspaceKnowledgeDocument[];
  ai_summary: string;
  ai_insights: string[];
};
