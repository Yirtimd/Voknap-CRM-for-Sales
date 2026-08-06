import { computed, ref } from "vue";

import { api, apiBlob, apiErrorMessage, emptyToNull, post, setAuthRefreshHandler } from "../api";
import type {
  AgentAction,
  AgentChatResponse,
  AgentContext,
  AgentHistoryMessage,
  AnalyticsOverview,
  Activity,
  AuthResponse,
  Company,
  CompanyCopilot,
  HomeCopilot,
  CompanyWorkspace,
  CommunicationEvent,
  Contact,
  ConnectorAccount,
  ConnectorDefinition,
  ConnectorSyncRun,
  ImportPreview,
  IntegrationJob,
  PublicApiKey,
  WebhookEndpoint,
  CsvExportResponse,
  AppliedTemplate,
  CompanyTemplate,
  Deal,
  KnowledgeAskResponse,
  KnowledgeDocument,
  KnowledgeSearchResult,
  Lead,
  Me,
  Note,
  NextAction,
  Pipeline,
  AuditLog,
  FeatureFlag,
  ProductionOverview,
  Task,
  Tenant,
  TenantExport,
  TenantPlan
} from "../types";

const token = ref("");
const tenantId = ref(localStorage.getItem("cmr_tenant_id") ?? "");
const tenants = ref<Tenant[]>(JSON.parse(localStorage.getItem("cmr_tenants") ?? "[]"));
const error = ref("");
const ok = ref("");
const isLoading = ref(false);

const contacts = ref<Contact[]>([]);
const companies = ref<Company[]>([]);
const companyWorkspace = ref<CompanyWorkspace | null>(null);
const leads = ref<Lead[]>([]);
const pipelines = ref<Pipeline[]>([]);
const deals = ref<Deal[]>([]);
const tasks = ref<Task[]>([]);
const notes = ref<Note[]>([]);
const knowledgeDocuments = ref<KnowledgeDocument[]>([]);
const knowledgeSearchResults = ref<KnowledgeSearchResult[]>([]);
const knowledgeAnswer = ref<KnowledgeAskResponse | null>(null);
const agentHistory = ref<AgentHistoryMessage[]>([]);
const agentActions = ref<AgentAction[]>([]);
const agentLastResponse = ref<AgentChatResponse | null>(null);
const agentPanelOpen = ref(false);
const agentContext = ref<AgentContext>({
  type: "workspace",
  company_id: null,
  deal_id: null,
  document_id: null,
  include_global: false,
  page_path: null
});
const agentFeedback = ref<Record<string, "up" | "down">>({});
const companyCopilot = ref<CompanyCopilot | null>(null);
const homeCopilot = ref<HomeCopilot | null>(null);
const connectorDefinitions = ref<ConnectorDefinition[]>([]);
const connectorAccounts = ref<ConnectorAccount[]>([]);
const connectorRuns = ref<ConnectorSyncRun[]>([]);
const integrationJobs = ref<IntegrationJob[]>([]);
const webhookEndpoints = ref<WebhookEndpoint[]>([]);
const publicApiKeys = ref<PublicApiKey[]>([]);
const importPreview = ref<ImportPreview | null>(null);
const importFile = ref<File | null>(null);
const importIdempotencyKey = ref("");
const importStatus = ref("");
const revealedWebhookSecret = ref("");
const revealedApiKey = ref("");
const communicationEvents = ref<CommunicationEvent[]>([]);
const csvExport = ref<CsvExportResponse | null>(null);
const companyTemplates = ref<CompanyTemplate[]>([]);
const appliedTemplates = ref<AppliedTemplate[]>([]);
const productionOverview = ref<ProductionOverview | null>(null);
const auditLogs = ref<AuditLog[]>([]);
const featureFlags = ref<FeatureFlag[]>([]);
const tenantPlan = ref<TenantPlan | null>(null);
const tenantExport = ref<TenantExport | null>(null);
const activities = ref<Activity[]>([]);
const analyticsOverview = ref<AnalyticsOverview | null>(null);
const nextActions = ref<NextAction[]>([]);
const me = ref<Me | null>(null);

const registerForm = ref({
  company_name: "Demo Company",
  company_slug: `demo-${Math.floor(Math.random() * 10000)}`,
  owner_email: "owner@example.com",
  owner_full_name: "Demo Owner",
  owner_password: "Voknap-Demo-2026!"
});

const loginForm = ref({ email: "owner@example.com", password: "password123" });
const mfaToken = ref("");
const mfaCode = ref("");
const pipelineForm = ref({ name: "Основная воронка", stages: "Новый, В работе, КП, Сделка" });
const contactForm = ref({ company_id: "", name: "Иван Петров", phone: "+79990000000", email: "client@example.com", company_name: "Ромашка" });
const companyForm = ref({ name: "Ромашка", website: "https://example.com", industry: "B2B", description: "Тестовая компания" });
const leadForm = ref({ company_id: "", title: "Заявка с сайта", source: "site", contact_id: "" });
const dealForm = ref({
  company_id: "",
  title: "Первая сделка",
  amount: 50000,
  discount_percent: 0,
  lead_id: "",
  stage_id: "",
  probability: 50,
  expected_close_date: "",
  expected_next_event: "Ответ клиента",
  next_step: "Позвонить клиенту",
  risk_level: "medium",
  forecast_category: "pipeline"
});
const taskForm = ref({
  company_id: "",
  title: "Позвонить клиенту",
  description: "Уточнить потребность",
  deal_id: "",
  priority: "normal",
  due_at: ""
});
const noteForm = ref({ text: "Клиент интересуется внедрением CRM" });
const knowledgeDocumentForm = ref({
  title: "Скрипт продаж",
  source_type: "text",
  text: "Компания продает CRM для отделов продаж. Основная ценность: учет лидов, сделок, задач, база знаний и AI-помощник. Первый шаг после заявки: связаться с клиентом в течение 15 минут, уточнить сферу бизнеса, количество менеджеров и текущую CRM."
});
const knowledgeSearchForm = ref({ query: "Что делать после новой заявки?", limit: 6, scope: "global", include_global: false });
const knowledgeAskForm = ref({ question: "Что делать после новой заявки?", limit: 6 });
const agentForm = ref({ message: "" });
const connectorAccountForm = ref({
  connector_code: "email",
  title: "Рабочая почта",
  email_provider: "gmail",
  host: "imap.gmail.com",
  port: 993,
  username: "",
  password: "",
  folder: "INBOX",
  use_ssl: true,
  smtp_host: "smtp.gmail.com",
  smtp_port: 465,
  smtp_use_ssl: true,
  from_email: ""
});
const emailSendForm = ref({
  account_id: "",
  recipient: "",
  subject: "",
  body: ""
});
const calendarEventForm = ref({
  account_id: "",
  title: "",
  description: "",
  starts_at: "",
  ends_at: "",
  timezone: "Europe/Moscow",
  attendees: ""
});
const webhookForm = ref({
  title: "",
  url: "",
  event_types: ["lead.created"]
});
const apiKeyForm = ref({
  title: "",
  scopes: ["leads:read", "leads:write"]
});
const importMapping = ref<Record<string, string>>({});
const csvImportForm = ref({
  account_id: "",
  csv_text: "name,phone,email,company_name,lead_title,source\nИван Петров,+79990000000,client@example.com,Ромашка,Заявка из CSV,csv"
});
const templateApplyForm = ref({
  template_code: "b2b_services",
  include_pipeline: true,
  include_knowledge: true
});
const featureFlagForm = ref({ code: "ai_agent", title: "AI агент", enabled: true });
const planForm = ref({
  plan_code: "trial",
  users_limit: 5,
  leads_limit: 500,
  documents_limit: 50,
  ai_requests_limit: 1000
});
const activityForm = ref({
  company_id: "",
  type: "COMMENT",
  title: "Комментарий",
  description: "Короткая заметка в timeline",
  contact_id: "",
  deal_id: ""
});
const communicationEventForm = ref({
  channel: "email",
  direction: "inbound",
  sender: "client@example.com",
  recipient: "sales@crmsales.app",
  subject: "Новый входящий запрос",
  body: "Клиент просит уточнить стоимость, сроки внедрения и следующий шаг.",
  company_id: "",
  contact_id: "",
  deal_id: ""
});
const nextActionForm = ref({
  company_id: "",
  deal_id: "",
  contact_id: "",
  title: "Связаться с клиентом",
  description: "",
  source: "manual",
  priority: "normal",
  due_at: ""
});

const isAuthed = computed(() => token.value.length > 0 && tenantId.value.length > 0);
const activeTenant = computed(() => tenants.value.find((tenant) => tenant.id === tenantId.value) ?? tenants.value[0]);
const allStages = computed(() => pipelines.value.flatMap((pipeline) => pipeline.stages));
const openTasks = computed(() => tasks.value.filter((task) => !task.done_at));
const totalPipeline = computed(() => deals.value.reduce((sum, deal) => sum + Number(deal.amount ?? 0), 0));
const dealsByStage = computed(() =>
  allStages.value.map((stage) => {
    const stageDeals = deals.value.filter((deal) => deal.stage_id === stage.id);
    return {
      stage,
      deals: stageDeals,
      amount: stageDeals.reduce((sum, deal) => sum + Number(deal.amount ?? 0), 0)
    };
  })
);

async function run(action: () => Promise<void>, success: string) {
  error.value = "";
  ok.value = "";
  isLoading.value = true;
  try {
    await action();
    ok.value = success;
  } catch (caught) {
    error.value = apiErrorMessage(caught);
  } finally {
    isLoading.value = false;
  }
}

function saveSession(auth: AuthResponse) {
  if (!auth.access_token) return;
  token.value = auth.access_token;
  tenants.value = auth.tenants;
  const savedTenantId = localStorage.getItem("cmr_tenant_id");
  const preferredTenant =
    auth.tenants.find((tenant) => tenant.id === savedTenantId) ??
    auth.tenants.find((tenant) => tenant.slug === "developer-test") ??
    auth.tenants[0];
  tenantId.value = preferredTenant?.id ?? "";
  localStorage.setItem("cmr_tenant_id", tenantId.value);
  localStorage.setItem("cmr_tenants", JSON.stringify(tenants.value));
}

async function registerCompany() {
  await run(async () => {
    const auth = await api<AuthResponse>("/auth/register-company", post(registerForm.value));
    saveSession(auth);
    await refreshAll();
  }, "Компания создана");
}

async function login() {
  await run(async () => {
    const auth = await api<AuthResponse>("/auth/login", post(loginForm.value));
    if (auth.status === "mfa_required") {
      mfaToken.value = auth.mfa_token ?? "";
      return;
    }
    saveSession(auth);
    await refreshAll();
  }, "Вход выполнен");
}

async function verifyMfaLogin() {
  await run(async () => {
    const auth = await api<AuthResponse>("/auth/mfa/verify-login", post({ mfa_token: mfaToken.value, code: mfaCode.value }));
    saveSession(auth);
    mfaToken.value = "";
    mfaCode.value = "";
    await refreshAll();
  }, "Вход выполнен");
}

async function refreshSession(): Promise<string | null> {
  try {
    const auth = await api<AuthResponse>("/auth/refresh", post({}));
    saveSession(auth);
    return token.value || null;
  } catch {
    clearSession();
    return null;
  }
}

async function logout() {
  try {
    if (token.value) await api<void>("/auth/logout", post({}), token.value);
  } catch {
    // Local cleanup must still happen if the server session already expired.
  }
  clearSession();
}

function clearSession() {
  token.value = "";
  tenantId.value = "";
  tenants.value = [];
  contacts.value = [];
  leads.value = [];
  deals.value = [];
  tasks.value = [];
  notes.value = [];
  pipelines.value = [];
  nextActions.value = [];
  homeCopilot.value = null;
  me.value = null;
  mfaToken.value = "";
  mfaCode.value = "";
  localStorage.removeItem("cmr_tenant_id");
  localStorage.removeItem("cmr_tenants");
}

setAuthRefreshHandler(refreshSession);

async function refreshMe() {
  if (!isAuthed.value) return;
  me.value = await api<Me>("/me", {}, token.value, tenantId.value);
}

function saveTenantId() {
  localStorage.setItem("cmr_tenant_id", tenantId.value);
  void refreshAll();
  void refreshMe();
  void refreshCommunication();
}

async function refreshAll() {
  if (!isAuthed.value) return;
  const [companyList, contactList, leadList, pipelineList, dealList, taskList, noteList, nextActionList] = await Promise.all([
    api<Company[]>("/sales/companies", {}, token.value, tenantId.value),
    api<Contact[]>("/sales/contacts", {}, token.value, tenantId.value),
    api<Lead[]>("/sales/leads", {}, token.value, tenantId.value),
    api<Pipeline[]>("/sales/pipelines", {}, token.value, tenantId.value),
    api<Deal[]>("/sales/deals", {}, token.value, tenantId.value),
    api<Task[]>("/sales/tasks", {}, token.value, tenantId.value),
    api<Note[]>("/sales/notes", {}, token.value, tenantId.value),
    api<NextAction[]>("/sales/next-actions", {}, token.value, tenantId.value)
  ]);
  companies.value = companyList;
  const firstCompanyId = companyList[0]?.id ?? "";
  contactForm.value.company_id ||= firstCompanyId;
  leadForm.value.company_id ||= firstCompanyId;
  dealForm.value.company_id ||= firstCompanyId;
  taskForm.value.company_id ||= firstCompanyId;
  activityForm.value.company_id ||= firstCompanyId;
  communicationEventForm.value.company_id ||= firstCompanyId;
  contacts.value = contactList;
  leads.value = leadList;
  pipelines.value = pipelineList;
  deals.value = dealList;
  tasks.value = taskList;
  notes.value = noteList;
  nextActions.value = nextActionList;
  if (!dealForm.value.stage_id && allStages.value[0]) dealForm.value.stage_id = allStages.value[0].id;
}

async function createCompany() {
  await run(async () => {
    const company = await api<Company>("/sales/companies", post(emptyToNull(companyForm.value)), token.value, tenantId.value);
    await refreshAll();
    contactForm.value.company_id = company.id;
    leadForm.value.company_id = company.id;
    dealForm.value.company_id = company.id;
    taskForm.value.company_id = company.id;
    activityForm.value.company_id = company.id;
  }, "Компания создана");
}

async function loadCompanyWorkspace(companyId: string) {
  if (!isAuthed.value) return;
  companyWorkspace.value = await api<CompanyWorkspace>(
    `/sales/companies/${companyId}`,
    {},
    token.value,
    tenantId.value
  );
}

async function refreshCommunication() {
  if (!isAuthed.value) return;
  communicationEvents.value = await api<CommunicationEvent[]>("/communication/events", {}, token.value, tenantId.value);
}

async function createCommunicationEvent() {
  await run(async () => {
    await api<CommunicationEvent>(
      "/communication/events",
      post(emptyToNull(communicationEventForm.value)),
      token.value,
      tenantId.value
    );
    await refreshCommunication();
    await refreshActivities();
  }, "Входящее событие создано");
}

async function linkCommunicationEvent(event: CommunicationEvent) {
  await run(async () => {
    await api<CommunicationEvent>(
      `/communication/events/${event.id}/link`,
      post(
        {
          company_id: event.company_id,
          contact_id: event.contact_id,
          deal_id: event.deal_id
        },
        "PATCH"
      ),
      token.value,
      tenantId.value
    );
    await refreshCommunication();
  }, "Коммуникация привязана");
}

async function createActivityFromCommunication(eventId: string) {
  await run(async () => {
    await api<CommunicationEvent>(
      `/communication/events/${eventId}/activity`,
      post({}),
      token.value,
      tenantId.value
    );
    await refreshCommunication();
    await refreshActivities();
  }, "Activity создана из коммуникации");
}

async function refreshCompanyCopilot(companyId: string) {
  if (!isAuthed.value) return;
  companyCopilot.value = await api<CompanyCopilot>(
    `/ai-agent/companies/${companyId}/copilot`,
    {},
    token.value,
    tenantId.value
  );
  await refreshAgent();
}

async function refreshHomeCopilot() {
  if (!isAuthed.value) return;
  homeCopilot.value = await api<HomeCopilot>(
    "/ai-agent/home/copilot",
    {},
    token.value,
    tenantId.value
  );
}

async function refreshKnowledge() {
  if (!isAuthed.value) return;
  knowledgeDocuments.value = await api<KnowledgeDocument[]>(
    "/knowledge/documents",
    {},
    token.value,
    tenantId.value
  );
}

async function createKnowledgeDocument() {
  await run(async () => {
    await api<KnowledgeDocument>(
      "/knowledge/documents",
      post(knowledgeDocumentForm.value),
      token.value,
      tenantId.value
    );
    await refreshKnowledge();
  }, "Документ добавлен в базу знаний");
}

async function uploadKnowledgeDocument(
  file: File,
  context: {
    title?: string;
    scope?: "global" | "company" | "deal";
    company_id?: string;
    deal_id?: string;
  } = {}
): Promise<boolean> {
  const form = new FormData();
  form.append("file", file);
  form.append("scope", context.scope ?? "global");
  if (context.title?.trim()) form.append("title", context.title.trim());
  if (context.company_id) form.append("company_id", context.company_id);
  if (context.deal_id) form.append("deal_id", context.deal_id);
  let succeeded = false;
  await run(async () => {
    await api<KnowledgeDocument>(
      "/knowledge/documents/upload",
      { method: "POST", body: form },
      token.value,
      tenantId.value
    );
    if ((context.scope ?? "global") === "global") await refreshKnowledge();
    succeeded = true;
  }, "Файл загружен и добавлен в базу знаний");
  return succeeded;
}

async function downloadKnowledgeDocument(document: Pick<KnowledgeDocument, "title" | "download_url">) {
  if (!document.download_url) return;
  await run(async () => {
    const blob = await apiBlob(document.download_url ?? "", token.value, tenantId.value);
    const url = URL.createObjectURL(blob);
    const anchor = window.document.createElement("a");
    anchor.href = url;
    anchor.download = document.title;
    anchor.click();
    URL.revokeObjectURL(url);
  }, "Файл скачан");
}

async function searchKnowledge() {
  await run(async () => {
    knowledgeSearchResults.value = await api<KnowledgeSearchResult[]>(
      "/knowledge/search",
      post(knowledgeSearchForm.value),
      token.value,
      tenantId.value
    );
  }, "Поиск выполнен");
}

async function askKnowledge(context: {
  scope?: "global" | "company" | "deal";
  company_id?: string;
  deal_id?: string;
  document_id?: string;
  include_global?: boolean;
} = {}): Promise<boolean> {
  knowledgeAnswer.value = null;
  const scope = context.scope ?? "global";
  const response = await sendAgentMessage(
    knowledgeAskForm.value.question,
    {
      type: context.document_id ? "document" : scope === "deal" ? "deal" : scope === "company" ? "company" : "knowledge",
      company_id: context.company_id ?? null,
      deal_id: context.deal_id ?? null,
      document_id: context.document_id ?? null,
      include_global: context.include_global ?? false,
      page_path: window.location.pathname + window.location.search
    }
  );
  if (!response?.query_id) return false;
  knowledgeAnswer.value = {
    query_id: response.query_id,
    answer: response.answer,
    citations: response.sources,
    scope,
    company_id: context.company_id ?? null,
    deal_id: context.deal_id ?? null,
    document_id: context.document_id ?? null,
    include_global: context.include_global ?? false,
    retrieval_mode: "hybrid"
  };
  return true;
}

async function refreshAgent() {
  if (!isAuthed.value) return;
  const [history, actions] = await Promise.all([
    api<AgentHistoryMessage[]>("/ai-agent/history", {}, token.value, tenantId.value),
    api<AgentAction[]>("/ai-agent/actions", {}, token.value, tenantId.value)
  ]);
  agentHistory.value = history.reverse();
  agentActions.value = actions;
}

function setAgentContext(context: Partial<AgentContext>) {
  agentContext.value = {
    type: context.type ?? "workspace",
    company_id: context.company_id ?? null,
    deal_id: context.deal_id ?? null,
    document_id: context.document_id ?? null,
    include_global: context.include_global ?? false,
    page_path: context.page_path ?? window.location.pathname + window.location.search
  };
}

function openAgent(context: Partial<AgentContext> = {}, message = "") {
  setAgentContext(context);
  if (message) agentForm.value.message = message;
  agentPanelOpen.value = true;
}

function closeAgent() {
  agentPanelOpen.value = false;
}

async function sendAgentMessage(
  message = agentForm.value.message,
  context?: Partial<AgentContext>
): Promise<AgentChatResponse | null> {
  if (!message.trim()) return null;
  if (context) setAgentContext(context);
  const payload = emptyToNull({
    message,
    context_type: agentContext.value.type,
    company_id: agentContext.value.company_id,
    deal_id: agentContext.value.deal_id,
    document_id: agentContext.value.document_id,
    include_global: agentContext.value.include_global,
    page_path: agentContext.value.page_path
  });
  let response: AgentChatResponse | null = null;
  await run(async () => {
    response = await api<AgentChatResponse>(
      "/ai-agent/chat",
      post(payload),
      token.value,
      tenantId.value
    );
    agentLastResponse.value = response;
    await refreshAgent();
  }, "AI агент ответил");
  return response;
}

async function sendAgentFeedback(queryId: string, rating: "up" | "down") {
  await run(async () => {
    await api(
      `/knowledge/queries/${queryId}/feedback`,
      post({ rating }),
      token.value,
      tenantId.value
    );
    agentFeedback.value = { ...agentFeedback.value, [queryId]: rating };
  }, "Оценка ответа сохранена");
}

async function downloadAgentSource(source: { document_title: string; download_url: string | null }) {
  if (!source.download_url) return;
  await run(async () => {
    const blob = await apiBlob(source.download_url ?? "", token.value, tenantId.value);
    const url = URL.createObjectURL(blob);
    const anchor = window.document.createElement("a");
    anchor.href = url;
    anchor.download = source.document_title;
    anchor.click();
    URL.revokeObjectURL(url);
  }, "Источник скачан");
}

async function confirmAgentAction(actionId: string) {
  await run(async () => {
    await api<AgentAction>(
      `/ai-agent/actions/${actionId}/confirm`,
      post({}),
      token.value,
      tenantId.value
    );
    await refreshAll();
    await refreshAgent();
  }, "Действие выполнено");
}

async function rejectAgentAction(actionId: string) {
  await run(async () => {
    await api<AgentAction>(
      `/ai-agent/actions/${actionId}/reject`,
      post({}),
      token.value,
      tenantId.value
    );
    await refreshAgent();
  }, "Действие отклонено");
}

async function refreshConnectors() {
  if (!isAuthed.value) return;
  const results = await Promise.allSettled([
    api<ConnectorDefinition[]>("/connectors/definitions", {}, token.value, tenantId.value),
    api<ConnectorAccount[]>("/connectors/accounts", {}, token.value, tenantId.value),
    api<ConnectorSyncRun[]>("/connectors/runs", {}, token.value, tenantId.value),
    api<IntegrationJob[]>("/connectors/jobs", {}, token.value, tenantId.value),
    api<WebhookEndpoint[]>("/connectors/webhooks", {}, token.value, tenantId.value),
    api<PublicApiKey[]>("/connectors/api-keys", {}, token.value, tenantId.value)
  ]);
  const [definitions, accounts, runs, jobs, webhooks, apiKeys] = results;
  if (definitions.status === "fulfilled") connectorDefinitions.value = definitions.value;
  if (accounts.status === "fulfilled") connectorAccounts.value = accounts.value;
  if (runs.status === "fulfilled") connectorRuns.value = runs.value;
  if (jobs.status === "fulfilled") integrationJobs.value = jobs.value;
  if (webhooks.status === "fulfilled") webhookEndpoints.value = webhooks.value;
  if (apiKeys.status === "fulfilled") publicApiKeys.value = apiKeys.value;
  if (!csvImportForm.value.account_id) {
    const csvAccount = connectorAccounts.value.find((account) => account.connector_code === "csv");
    csvImportForm.value.account_id = csvAccount?.id ?? "";
  }
  const rejected = results.find((result) => result.status === "rejected");
  if (rejected?.status === "rejected") throw rejected.reason;
}

async function createConnectorAccount() {
  await run(async () => {
    const isEmail = connectorAccountForm.value.connector_code === "email";
    await api<ConnectorAccount>(
      "/connectors/accounts",
      post({
        connector_code: connectorAccountForm.value.connector_code,
        title: connectorAccountForm.value.title,
        credentials: isEmail
          ? {
              username: connectorAccountForm.value.username,
              password: connectorAccountForm.value.password
            }
          : {},
        settings: isEmail
          ? {
              host: connectorAccountForm.value.host,
              port: connectorAccountForm.value.port,
              folder: connectorAccountForm.value.folder,
              use_ssl: connectorAccountForm.value.use_ssl,
              starttls: !connectorAccountForm.value.use_ssl,
              smtp_host: connectorAccountForm.value.smtp_host,
              smtp_port: connectorAccountForm.value.smtp_port,
              smtp_use_ssl: connectorAccountForm.value.smtp_use_ssl,
              smtp_starttls: !connectorAccountForm.value.smtp_use_ssl,
              from_email: connectorAccountForm.value.from_email || connectorAccountForm.value.username,
              sync_limit: 100
            }
          : {}
      }),
      token.value,
      tenantId.value
    );
    connectorAccountForm.value.password = "";
    await refreshConnectors();
  }, "Коннектор подключен");
}

async function syncConnectorAccount(accountId: string) {
  await run(async () => {
    await api<IntegrationJob>(
      `/connectors/accounts/${accountId}/sync`,
      post({ payload: {} }),
      token.value,
      tenantId.value
    );
    await refreshConnectors();
  }, "Задание синхронизации добавлено в очередь");
}

async function startConnectorOAuth(accountId: string) {
  await run(async () => {
    const result = await api<{ authorization_url: string }>(
      `/connectors/accounts/${accountId}/oauth/start`,
      post({}),
      token.value,
      tenantId.value
    );
    window.location.assign(result.authorization_url);
  }, "Переход к OAuth-провайдеру");
}

async function disconnectConnectorAccount(accountId: string) {
  await run(async () => {
    await api<void>(
      `/connectors/accounts/${accountId}`,
      { method: "DELETE" },
      token.value,
      tenantId.value
    );
    await refreshConnectors();
  }, "Интеграция отключена");
}

async function sendIntegrationEmail() {
  await run(async () => {
    await api<IntegrationJob>(
      `/connectors/accounts/${emailSendForm.value.account_id}/email/send`,
      post({
        recipient: emailSendForm.value.recipient,
        subject: emailSendForm.value.subject,
        body: emailSendForm.value.body,
        idempotency_key: crypto.randomUUID()
      }),
      token.value,
      tenantId.value
    );
    await refreshConnectors();
  }, "Письмо добавлено в очередь");
}

async function createIntegrationCalendarEvent() {
  await run(async () => {
    await api<IntegrationJob>(
      `/connectors/accounts/${calendarEventForm.value.account_id}/calendar/events`,
      post({
        ...calendarEventForm.value,
        starts_at: new Date(calendarEventForm.value.starts_at).toISOString(),
        ends_at: new Date(calendarEventForm.value.ends_at).toISOString(),
        attendees: calendarEventForm.value.attendees.split(",").map((item) => item.trim()).filter(Boolean),
        idempotency_key: crypto.randomUUID()
      }),
      token.value,
      tenantId.value
    );
    await refreshConnectors();
  }, "Событие добавлено в очередь");
}

async function replayIntegrationJob(jobId: string) {
  await run(async () => {
    await api<IntegrationJob>(
      `/connectors/jobs/${jobId}/replay`,
      post({}),
      token.value,
      tenantId.value
    );
    await refreshConnectors();
  }, "Задание возвращено из DLQ");
}

async function previewIntegrationImport(file: File) {
  await run(async () => {
    const body = new FormData();
    body.append("file", file);
    importPreview.value = await api<ImportPreview>(
      "/connectors/imports/preview",
      { method: "POST", body },
      token.value,
      tenantId.value
    );
    importFile.value = file;
    importIdempotencyKey.value = crypto.randomUUID();
    importStatus.value = "";
    importMapping.value = { ...importPreview.value.suggested_mapping };
  }, "Preview готов");
}

async function enqueueIntegrationImport() {
  if (!importFile.value) return;
  await run(async () => {
    const body = new FormData();
    body.append("file", importFile.value as File);
    body.append("mapping_json", JSON.stringify(importMapping.value));
    importIdempotencyKey.value ||= crypto.randomUUID();
    body.append("idempotency_key", importIdempotencyKey.value);
    const response = await api<{ job: IntegrationJob }>(
      "/connectors/imports",
      { method: "POST", body },
      token.value,
      tenantId.value
    );
    importStatus.value = "Задание ожидает background worker…";
    for (let attempt = 0; attempt < 20; attempt += 1) {
      const jobs = await api<IntegrationJob[]>(
        "/connectors/jobs",
        {},
        token.value,
        tenantId.value
      );
      integrationJobs.value = jobs;
      const job = jobs.find((item) => item.id === response.job.id);
      if (job?.status === "succeeded") {
        const created = Number(job.result.created ?? 0);
        const failed = Number(job.result.failed ?? 0);
        importStatus.value = `Импорт завершён: создано ${created}, ошибок ${failed}.`;
        await refreshAll();
        importPreview.value = null;
        importFile.value = null;
        return;
      }
      if (job?.status === "dead") {
        throw new Error(job.last_error || "Импорт завершился с ошибкой");
      }
      importStatus.value = job?.status === "running"
        ? "Импорт выполняется…"
        : "Задание ожидает background worker…";
      await new Promise((resolve) => window.setTimeout(resolve, 500));
    }
    importStatus.value = "Импорт продолжает выполняться в фоне. Статус доступен в журнале заданий.";
  }, "Импорт добавлен в очередь");
}

async function createWebhookEndpoint() {
  await run(async () => {
    const endpoint = await api<WebhookEndpoint>(
      "/connectors/webhooks",
      post(webhookForm.value),
      token.value,
      tenantId.value
    );
    revealedWebhookSecret.value = endpoint.signing_secret ?? "";
    await refreshConnectors();
  }, "Webhook создан. Сохраните секрет.");
}

async function testWebhookEndpoint(endpointId: string) {
  await run(async () => {
    await api<IntegrationJob>(
      `/connectors/webhooks/${endpointId}/test`,
      post({ idempotency_key: crypto.randomUUID() }),
      token.value,
      tenantId.value
    );
    await refreshConnectors();
  }, "Тест webhook добавлен в очередь");
}

async function disableWebhookEndpoint(endpointId: string) {
  await run(async () => {
    await api<void>(
      `/connectors/webhooks/${endpointId}`,
      { method: "DELETE" },
      token.value,
      tenantId.value
    );
    await refreshConnectors();
  }, "Webhook отключен");
}

async function issuePublicApiKey() {
  await run(async () => {
    const key = await api<PublicApiKey>(
      "/connectors/api-keys",
      post(apiKeyForm.value),
      token.value,
      tenantId.value
    );
    revealedApiKey.value = key.api_key ?? "";
    await refreshConnectors();
  }, "API-ключ создан. Сохраните его.");
}

async function revokePublicApiKey(keyId: string) {
  await run(async () => {
    await api<void>(
      `/connectors/api-keys/${keyId}`,
      { method: "DELETE" },
      token.value,
      tenantId.value
    );
    await refreshConnectors();
  }, "API-ключ отозван");
}

async function retryConnectorRun(runId: string) {
  await run(async () => {
    await api<ConnectorSyncRun>(
      `/connectors/runs/${runId}/retry`,
      post({}),
      token.value,
      tenantId.value
    );
    await refreshAll();
    await refreshConnectors();
  }, "Retry выполнен");
}

async function importCsv() {
  await run(async () => {
    await api<ConnectorSyncRun>(
      `/connectors/accounts/${csvImportForm.value.account_id}/csv/import`,
      post({ csv_text: csvImportForm.value.csv_text }),
      token.value,
      tenantId.value
    );
    await refreshAll();
    await refreshConnectors();
  }, "CSV импорт выполнен");
}

async function exportCsv() {
  await run(async () => {
    csvExport.value = await api<CsvExportResponse>("/connectors/csv/export", {}, token.value, tenantId.value);
  }, "CSV экспорт готов");
}

async function refreshTemplates() {
  if (!isAuthed.value) return;
  const [templates, applied] = await Promise.all([
    api<CompanyTemplate[]>("/templates", {}, token.value, tenantId.value),
    api<AppliedTemplate[]>("/templates/applied", {}, token.value, tenantId.value)
  ]);
  companyTemplates.value = templates;
  appliedTemplates.value = applied;
  if (!templates.some((template) => template.code === templateApplyForm.value.template_code)) {
    templateApplyForm.value.template_code = templates[0]?.code ?? "";
  }
}

async function applyCompanyTemplate() {
  await run(async () => {
    await api<AppliedTemplate>(
      "/templates/apply",
      post(templateApplyForm.value),
      token.value,
      tenantId.value
    );
    await refreshAll();
    await refreshKnowledge();
    await refreshTemplates();
  }, "Шаблон применен");
}

async function refreshProduction() {
  if (!isAuthed.value) return;
  const [overview, audit, flags, plan] = await Promise.all([
    api<ProductionOverview>("/production/overview", {}, token.value, tenantId.value),
    api<AuditLog[]>("/production/audit", {}, token.value, tenantId.value),
    api<FeatureFlag[]>("/production/flags", {}, token.value, tenantId.value),
    api<TenantPlan>("/production/plan", {}, token.value, tenantId.value)
  ]);
  productionOverview.value = overview;
  auditLogs.value = audit;
  featureFlags.value = flags;
  tenantPlan.value = plan;
  planForm.value = {
    plan_code: plan.plan_code,
    users_limit: plan.users_limit,
    leads_limit: plan.leads_limit,
    documents_limit: plan.documents_limit,
    ai_requests_limit: plan.ai_requests_limit
  };
}

async function createFeatureFlag() {
  await run(async () => {
    await api<FeatureFlag>("/production/flags", post(featureFlagForm.value), token.value, tenantId.value);
    await refreshProduction();
  }, "Feature flag сохранен");
}

async function toggleFeatureFlag(flag: FeatureFlag) {
  await run(async () => {
    await api<FeatureFlag>(
      `/production/flags/${flag.id}`,
      post({ enabled: !flag.enabled }, "PATCH"),
      token.value,
      tenantId.value
    );
    await refreshProduction();
  }, "Feature flag обновлен");
}

async function updateTenantPlan() {
  await run(async () => {
    tenantPlan.value = await api<TenantPlan>(
      "/production/plan",
      post(planForm.value, "PUT"),
      token.value,
      tenantId.value
    );
    await refreshProduction();
  }, "Тариф обновлен");
}

async function createAuditMarker() {
  await run(async () => {
    await api<AuditLog>("/production/audit", post({}), token.value, tenantId.value);
    await refreshProduction();
  }, "Audit marker создан");
}

async function exportTenantData() {
  await run(async () => {
    tenantExport.value = await api<TenantExport>("/production/export", {}, token.value, tenantId.value);
    await refreshProduction();
  }, "Экспорт готов");
}

async function refreshActivities() {
  if (!isAuthed.value) return;
  activities.value = await api<Activity[]>("/activities", {}, token.value, tenantId.value);
}

async function refreshAnalytics() {
  if (!isAuthed.value) return;
  analyticsOverview.value = await api<AnalyticsOverview>(
    "/analytics/overview?forecast_days=90&stuck_days=14&activity_days=30",
    {},
    token.value,
    tenantId.value
  );
}

async function createActivity() {
  await run(async () => {
    await api<Activity>(
      "/activities",
      post({
        type: activityForm.value.type,
        title: activityForm.value.title,
        description: activityForm.value.description,
        company_id: activityForm.value.company_id,
        contact_id: activityForm.value.contact_id || null,
        deal_id: activityForm.value.deal_id || null,
        metadata: { source: "timeline_page" }
      }),
      token.value,
      tenantId.value
    );
    await refreshActivities();
  }, "Activity создана");
}

async function createPipeline() {
  await run(async () => {
    await api<Pipeline>(
      "/sales/pipelines",
      post({
        name: pipelineForm.value.name,
        stages: pipelineForm.value.stages.split(",").map((stage) => stage.trim()).filter(Boolean)
      }),
      token.value,
      tenantId.value
    );
    await refreshAll();
  }, "Воронка создана");
}

async function savePipeline(payload: {
  id?: string;
  version?: number;
  name: string;
  description?: string | null;
  is_active?: boolean;
  is_default?: boolean;
  stages: Array<{
    id?: string;
    name: string;
    code?: string;
    probability: number;
    stage_type: "open" | "won" | "lost";
    required_fields: string[];
  }>;
}) {
  const message = payload.id ? "Воронка обновлена" : "Воронка создана";
  await run(async () => {
    const { id, version, ...values } = payload;
    await api<Pipeline>(
      id ? `/sales/pipelines/${id}` : "/sales/pipelines",
      post(id ? { version, ...values } : values, id ? "PATCH" : "POST"),
      token.value,
      tenantId.value
    );
    await refreshAll();
  }, message);
}

async function createContact() {
  await run(async () => {
    await api<Contact>("/sales/contacts", post(emptyToNull(contactForm.value)), token.value, tenantId.value);
    await refreshAll();
  }, "Контакт создан");
}

async function createLead() {
  await run(async () => {
    await api<Lead>("/sales/leads", post(emptyToNull(leadForm.value)), token.value, tenantId.value);
    await refreshAll();
  }, "Лид создан");
}

async function createDeal() {
  await run(async () => {
    await api<Deal>("/sales/deals", post(emptyToNull(dealForm.value)), token.value, tenantId.value);
    await refreshAll();
  }, "Сделка создана");
}

async function moveDeal(deal: Deal, stageId: string) {
  await run(async () => {
    await api<Deal>(
      `/sales/deals/${deal.id}/move`,
      post({ stage_id: stageId, version: deal.version }, "PATCH"),
      token.value,
      tenantId.value
    );
    await refreshAll();
  }, "Сделка перемещена");
}

async function createTask() {
  await run(async () => {
    await api<Task>("/sales/tasks", post(emptyToNull(taskForm.value)), token.value, tenantId.value);
    await refreshAll();
  }, "Задача создана");
}

async function createNextAction(payload: Partial<typeof nextActionForm.value> = {}) {
  await run(async () => {
    const source = { ...nextActionForm.value, ...payload };
    await api<NextAction>(
      "/sales/next-actions",
      post(emptyToNull(source)),
      token.value,
      tenantId.value
    );
    await refreshAll();
    if (source.company_id) await loadCompanyWorkspace(source.company_id);
  }, "Следующее действие сохранено");
}

async function toggleNextAction(action: NextAction, isDone = action.status !== "done") {
  await run(async () => {
    await api<NextAction>(
      `/sales/next-actions/${action.id}/done`,
      post({ is_done: isDone }, "PATCH"),
      token.value,
      tenantId.value
    );
    await refreshAll();
    await loadCompanyWorkspace(action.company_id);
  }, isDone ? "Следующее действие выполнено" : "Следующее действие открыто");
}

async function toggleTask(task: Task) {
  await run(async () => {
    await api<Task>(
      `/sales/tasks/${task.id}/done`,
      post({ is_done: task.done_at === null, version: task.version }, "PATCH"),
      token.value,
      tenantId.value
    );
    await refreshAll();
  }, "Задача обновлена");
}

async function createNote(target: "lead" | "deal", id: string) {
  await run(async () => {
    const companyId =
      target === "lead"
        ? leads.value.find((lead) => lead.id === id)?.company_id
        : deals.value.find((deal) => deal.id === id)?.company_id;
    await api<Note>(
      "/sales/notes",
      post({
        company_id: companyId,
        text: noteForm.value.text,
        lead_id: target === "lead" ? id : null,
        deal_id: target === "deal" ? id : null
      }),
      token.value,
      tenantId.value
    );
    await refreshAll();
  }, "Заметка создана");
}

async function recalculateScore(entityType: "lead" | "deal", entityId: string) {
  await run(async () => {
    await api(
      `/sales/scoring/${entityType}/${entityId}/recalculate`,
      post({}),
      token.value,
      tenantId.value
    );
    await refreshAll();
    await refreshAnalytics();
  }, entityType === "lead" ? "Оценка лида обновлена" : "Оценка сделки обновлена");
}

function money(value: number | null | undefined) {
  return new Intl.NumberFormat("ru-RU", {
    style: "currency",
    currency: "RUB",
    maximumFractionDigits: 0
  }).format(value ?? 0);
}

export const crmStore = {
  token,
  tenantId,
  tenants,
  error,
  ok,
  isLoading,
  contacts,
  companies,
  companyWorkspace,
  leads,
  pipelines,
  deals,
  tasks,
  notes,
  knowledgeDocuments,
  knowledgeSearchResults,
  knowledgeAnswer,
  agentHistory,
  agentActions,
  agentLastResponse,
  agentPanelOpen,
  agentContext,
  agentFeedback,
  companyCopilot,
  homeCopilot,
  connectorDefinitions,
  connectorAccounts,
  connectorRuns,
  integrationJobs,
  webhookEndpoints,
  publicApiKeys,
  importPreview,
  importStatus,
  importMapping,
  revealedWebhookSecret,
  revealedApiKey,
  communicationEvents,
  csvExport,
  companyTemplates,
  appliedTemplates,
  productionOverview,
  auditLogs,
  featureFlags,
  tenantPlan,
  tenantExport,
  activities,
  analyticsOverview,
  nextActions,
  me,
  registerForm,
  loginForm,
  mfaToken,
  mfaCode,
  pipelineForm,
  contactForm,
  companyForm,
  leadForm,
  dealForm,
  taskForm,
  noteForm,
  knowledgeDocumentForm,
  knowledgeSearchForm,
  knowledgeAskForm,
  agentForm,
  connectorAccountForm,
  emailSendForm,
  calendarEventForm,
  webhookForm,
  apiKeyForm,
  csvImportForm,
  templateApplyForm,
  featureFlagForm,
  planForm,
  activityForm,
  communicationEventForm,
  nextActionForm,
  isAuthed,
  activeTenant,
  allStages,
  openTasks,
  totalPipeline,
  dealsByStage,
  registerCompany,
  login,
  verifyMfaLogin,
  refreshSession,
  logout,
  saveTenantId,
  refreshMe,
  refreshAll,
  createCompany,
  loadCompanyWorkspace,
  refreshCompanyCopilot,
  refreshHomeCopilot,
  refreshKnowledge,
  refreshAgent,
  refreshConnectors,
  refreshCommunication,
  refreshTemplates,
  refreshProduction,
  refreshActivities,
  refreshAnalytics,
  createPipeline,
  savePipeline,
  createContact,
  createLead,
  createDeal,
  moveDeal,
  createTask,
  createNextAction,
  toggleNextAction,
  toggleTask,
  createNote,
  recalculateScore,
  createKnowledgeDocument,
  uploadKnowledgeDocument,
  downloadKnowledgeDocument,
  searchKnowledge,
  askKnowledge,
  setAgentContext,
  openAgent,
  closeAgent,
  sendAgentMessage,
  sendAgentFeedback,
  downloadAgentSource,
  confirmAgentAction,
  rejectAgentAction,
  createConnectorAccount,
  syncConnectorAccount,
  startConnectorOAuth,
  disconnectConnectorAccount,
  sendIntegrationEmail,
  createIntegrationCalendarEvent,
  replayIntegrationJob,
  previewIntegrationImport,
  enqueueIntegrationImport,
  createWebhookEndpoint,
  testWebhookEndpoint,
  disableWebhookEndpoint,
  issuePublicApiKey,
  revokePublicApiKey,
  retryConnectorRun,
  createCommunicationEvent,
  linkCommunicationEvent,
  createActivityFromCommunication,
  importCsv,
  exportCsv,
  applyCompanyTemplate,
  createFeatureFlag,
  toggleFeatureFlag,
  updateTenantPlan,
  createAuditMarker,
  exportTenantData,
  createActivity,
  money
};
