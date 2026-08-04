<script setup lang="ts">
import { computed, ref, watch } from "vue";

import { api, emptyToNull, post } from "../../api";
import UiIcon from "../ui/UiIcon.vue";
import type { IconName } from "../ui/icons";
import { statusLabel } from "../../design-system/statusDictionary";
import EntityCrudDrawer from "./EntityCrudDrawer.vue";
import CadencePanel from "./CadencePanel.vue";
import CustomFieldsForm from "./CustomFieldsForm.vue";
import type { Activity, CommunicationEvent, Company, Contact, NextAction, Note, Task } from "../../types";
import { crmStore } from "../../stores/crm";
import { formatStageName } from "../../utils/stages";

const props = defineProps<{ company: Company | null; initialTab?: string; embedded?: boolean }>();
const emit = defineEmits<{ close: [] }>();
const isSaving = ref(false);
const includeGlobalKnowledge = ref(false);
const knowledgeIsLoading = ref(false);
const knowledgeError = ref("");
const knowledgeFileInput = ref<HTMLInputElement | null>(null);
const isNextActionEditorOpen = ref(false);
const nextActionForm = ref({ title: "", description: "", due_at: "", priority: "high" });
const drawerActionMode = ref<"call" | "email" | "meeting" | "task" | null>(null);
const callForm = ref({ subject: "Звонок клиенту", body: "", phone: "" });
const emailForm = ref({ subject: "Повторный контакт", body: "", recipient: "" });
const meetingActionForm = ref({ subject: "Встреча с клиентом", body: "", occurred_at: "" });
const drawerTaskForm = ref({ title: "Повторный контакт", description: "", due_at: "", priority: "high" });
const activeTab = ref("overview");
const isNotesSpaceOpen = ref(false);
const crudEntityType = ref<"contacts" | "notes" | null>(null);
const crudRecord = ref<Contact | Note | null>(null);
const crudInitialMode = ref<"view" | "edit" | "create">("view");
const notesSearch = ref("");
const taskSearch = ref("");
const taskFilter = ref<"all" | "open" | "overdue" | "done">("all");
const taskPriorityFilter = ref("all");
const tabs = [
  { code: "overview", label: "Обзор" },
  { code: "contacts", label: "Контакты" },
  { code: "sequences", label: "Sequences" },
  { code: "deals", label: "Сделки" },
  { code: "tasks", label: "Задачи" },
  { code: "files", label: "Файлы" },
  { code: "timeline", label: "Активности" },
  { code: "knowledge", label: "База знаний" },
  { code: "history", label: "История" }
];

watch(
  () => [props.company?.id, props.initialTab],
  ([companyId, tab]) => {
    if (!companyId) return;
    activeTab.value = typeof tab === "string" && tabs.some((item) => item.code === tab) ? tab : "overview";
  },
  { immediate: true }
);

const workspace = computed(() =>
  props.company && crmStore.companyWorkspace.value?.company.id === props.company.id
    ? crmStore.companyWorkspace.value
    : null
);

const contacts = computed(() => workspace.value?.contacts ?? []);
const deals = computed(() => workspace.value?.deals ?? []);
const tasks = computed(() => workspace.value?.tasks ?? []);
const activities = computed(() => workspace.value?.activities ?? []);
const files = computed(() => workspace.value?.files ?? []);
const knowledgeDocuments = computed(() => workspace.value?.knowledge_documents ?? []);
const knowledgeSources = computed(() => {
  const indexedFileIds = new Set(knowledgeDocuments.value.map((document) => document.file_id).filter(Boolean));
  return [
    ...knowledgeDocuments.value.slice(0, 3).map((document) => ({
      id: document.id,
      title: document.title,
      type: document.source_type.toUpperCase(),
      date: document.created_at,
      meta: `${document.visibility === "deal" ? "Сделка" : "Компания"} · ${formatDate(document.created_at)}`,
      downloadable: Boolean(document.download_url)
    })),
    ...files.value.filter((file) => !indexedFileIds.has(file.id)).slice(0, 3).map((file) => ({
      id: file.id,
      title: file.name,
      type: String(file.file_type ?? file.name.split(".").pop() ?? "DOC").toUpperCase(),
      date: file.uploaded_at,
      meta: `${String(file.file_type ?? "Файл").toUpperCase()} · ${formatDate(file.uploaded_at)}`,
      downloadable: false
    }))
  ].slice(0, 5)
});
const companyKnowledgeAnswer = computed(() => {
  const answer = crmStore.knowledgeAnswer.value;
  if (!answer || !props.company || answer.company_id !== props.company.id) return null;
  const expectedScope = currentDeal.value ? "deal" : "company";
  if (answer.scope !== expectedScope) return null;
  if (expectedScope === "deal" && answer.deal_id !== currentDeal.value?.id) return null;
  return answer;
});
const knowledgeCitations = computed(() => companyKnowledgeAnswer.value?.citations ?? []);
const companyNotes = computed(() => crmStore.notes.value.filter((note) => note.company_id === props.company?.id));
const filteredCompanyNotes = computed(() => {
  const needle = notesSearch.value.trim().toLowerCase();
  if (!needle) return companyNotes.value;
  return companyNotes.value.filter((note) => note.text.toLowerCase().includes(needle));
});
const openTasks = computed(() => tasks.value.filter((task) => !isTaskCompleted(task)));
const taskStats = computed(() => ({
  open: openTasks.value.length,
  high: tasks.value.filter((task) => !isTaskCompleted(task) && (task.priority === "high" || task.priority === "urgent")).length,
  overdue: tasks.value.filter((task) => isTaskOverdue(task)).length
}));
const filteredTasks = computed(() => {
  const needle = taskSearch.value.trim().toLowerCase();
  return tasks.value.filter((task) => {
    if (taskFilter.value === "open" && isTaskCompleted(task)) return false;
    if (taskFilter.value === "done" && !isTaskCompleted(task)) return false;
    if (taskFilter.value === "overdue" && !isTaskOverdue(task)) return false;
    if (taskPriorityFilter.value !== "all" && task.priority !== taskPriorityFilter.value) return false;
    if (!needle) return true;
    return [task.title, task.description].some((value) => String(value ?? "").toLowerCase().includes(needle));
  });
});
const groupedTasks = computed(() => {
  const startOfToday = new Date();
  startOfToday.setHours(0, 0, 0, 0);
  const endOfToday = new Date(startOfToday);
  endOfToday.setDate(endOfToday.getDate() + 1);
  const endOfWeek = new Date(startOfToday);
  endOfWeek.setDate(endOfWeek.getDate() + 7);
  const overdue: Task[] = [];
  const today: Task[] = [];
  const thisWeek: Task[] = [];
  const noDueDate: Task[] = [];
  const completed: Task[] = [];
  filteredTasks.value.forEach((task) => {
    if (isTaskCompleted(task)) {
      completed.push(task);
      return;
    }
    if (!task.due_at) {
      noDueDate.push(task);
      return;
    }
    const dueDate = new Date(task.due_at);
    if (dueDate < startOfToday) {
      overdue.push(task);
    } else if (dueDate >= startOfToday && dueDate < endOfToday) {
      today.push(task);
    } else if (dueDate >= endOfToday && dueDate <= endOfWeek) {
      thisWeek.push(task);
    } else {
      noDueDate.push(task);
    }
  });
  return [
    { key: "overdue", title: "Просрочено", rows: overdue },
    { key: "today", title: "Сегодня", rows: today },
    { key: "thisWeek", title: "На неделе", rows: thisWeek },
    { key: "noDueDate", title: "Без срока", rows: noDueDate },
    { key: "completed", title: "Готово", rows: completed.slice(0, 3) }
  ].filter((group) => group.rows.length);
});
const currentDeal = computed(() => deals.value[0]);
const stages = computed(() => crmStore.allStages.value);
const currentStage = computed(() => stages.value.find((stage) => stage.id === currentDeal.value?.stage_id));
const fallbackStages = computed(() => currentStage.value ? [currentStage.value] : []);
const dealStageRows = computed(() =>
  deals.value.length
    ? deals.value.map((deal) => ({
        deal,
        stages: stages.value.length ? stages.value : fallbackStages.value,
        activeIndex: Math.max(0, (stages.value.length ? stages.value : fallbackStages.value).findIndex((stage) => stage.id === deal.stage_id))
      }))
    : []
);
const compactDealRows = computed(() =>
  dealStageRows.value.slice(0, 4).map((row) => {
    const stageCount = Math.max(1, row.stages.length);
    const activeStage = row.stages[row.activeIndex];
    const nextStage = row.stages[row.activeIndex + 1];
    return {
      ...row,
      activeStageName: formatStageName(activeStage?.name),
      nextStageName: nextStage ? formatStageName(nextStage.name) : "Финал",
      progress: Math.round(((row.activeIndex + 1) / stageCount) * 100)
    };
  })
);
const health = computed(() => workspace.value?.health.score ?? Math.min(98, 70 + contacts.value.length * 4 + deals.value.length * 6));
const healthTrendIcon = computed<IconName>(() => (workspace.value?.health.trend === "down" ? "trendDown" : workspace.value?.health.trend === "flat" ? "minus" : "trendUp"));
const healthLabel = computed(() => workspace.value?.health.label ?? "Хороший");
const pipeline = computed(() => deals.value.reduce((sum, deal) => sum + Number(deal.amount ?? 0), 0));
const pipelineBreakdown = computed(() => {
  const rows = new Map<string, { title: string; count: number; amount: number }>();
  deals.value.forEach((deal) => {
    const stageTitle = formatStageName(stages.value.find((stage) => stage.id === deal.stage_id)?.name);
    const row = rows.get(stageTitle) ?? { title: stageTitle, count: 0, amount: 0 };
    row.count += 1;
    row.amount += Number(deal.amount ?? 0);
    rows.set(stageTitle, row);
  });
  return Array.from(rows.values()).sort((left, right) => right.amount - left.amount);
});
const nextActionRecord = computed(() => workspace.value?.next_action ?? null);
const nextAction = computed(() => nextActionRecord.value?.title ?? currentDeal.value?.next_step ?? openTasks.value[0]?.title ?? (deals.value.length ? "Отправить КП" : "Создать первую сделку"));
const displayIndustry = computed(() => workspace.value?.company.industry ?? props.company?.industry ?? "Розничная торговля");
const companyType = computed(() => workspace.value?.company.company_type ?? displayIndustry.value ?? "B2B");
const clientSince = computed(() => workspace.value?.company.client_since ?? workspace.value?.company.created_at ?? props.company?.created_at);
const owner = computed(() => workspace.value?.company.owner);
const ownerName = computed(() => owner.value?.name ?? "Не назначен");
const ownerInitials = computed(() => owner.value?.initials ?? ownerName.value.slice(0, 1));
const lastContactAt = computed(() => workspace.value?.overview.last_contact_at ? relativeDate(String(workspace.value.overview.last_contact_at)) : "Нет контактов");
const lastContactPerson = computed(() => String(workspace.value?.overview.last_contact_person ?? "Не указан"));
const channelSummary = computed(() => String(workspace.value?.overview.channel_summary ?? "Нет каналов"));
const source = computed(() => workspace.value?.company.source ?? "Не указан");
const currentDealAge = computed(() => currentDeal.value?.age_days != null ? `${currentDeal.value.age_days} дней` : "Нет сделки");
const dealProbability = computed(() => currentDeal.value?.probability ?? null);
const expectedNextEvent = computed(() => currentDeal.value?.expected_next_event ?? "Ожидаем: следующего действия");
const recommendations = computed(() => workspace.value?.health.ai_recommendations ?? []);
const copilot = computed(() =>
  props.company && crmStore.companyCopilot.value?.company_id === props.company.id
    ? crmStore.companyCopilot.value
    : null
);
const copilotRecommendations = computed(() => {
  if (!copilot.value) return recommendations.value;
  return [
    {
      type: copilot.value.deal_risk.level === "high" ? "warning" : "info",
      title: "Риск сделки по оценке AI",
      description: `${copilot.value.deal_risk.level}: ${copilot.value.deal_risk.reason}`,
    },
    {
      type: "success",
      title: "Следующее лучшее действие",
      description: copilot.value.next_best_action,
    },
    {
      type: "info",
      title: "Черновик повторного контакта",
      description: copilot.value.follow_up_draft,
    },
    {
      type: "info",
      title: "Подготовка к встрече",
      description: copilot.value.meeting_prep,
    },
  ];
});
const pendingCopilotActions = computed(() => (copilot.value?.actions ?? []).filter((action) => action.status === "pending"));
const historyRows = computed(() =>
  activities.value
    .filter((activity) => Array.isArray(activity.metadata?.changes))
    .flatMap((activity) =>
      (activity.metadata.changes as Array<{ field: string; old: unknown; new: unknown }>).map((change) => ({ activity, change }))
    )
);

const timelineRows = computed(() => {
  const fallback = [
    { id: "call", when: "Сегодня\n10:30", icon: "phone", title: "Позвонили клиенту", by: "Иван П." },
    { id: "email", when: "Вчера\n15:45", icon: "mail", title: "Отправили КП", by: "Иван П." },
    { id: "meet", when: "3 дня назад\n11:20", icon: "check", title: "Встреча с клиентом", by: "Иван П." },
    { id: "contact", when: "12 дней назад\n09:15", icon: "person", title: "Первый контакт", by: "Иван П." },
    { id: "company", when: "13 дней назад", icon: "building", title: "Создана компания", by: "Система" }
  ];
  if (!activities.value.length) return fallback;
  return activities.value.slice(0, 5).map((activity) => ({
    id: activity.id,
    when: timelineWhen(activity.created_at),
    icon: activity.activity_icon,
    title: activity.title,
    by: activity.author_name ?? "Система"
  }));
});

function formatDate(value?: string | null) {
  if (!value) return "не указано";
  return new Date(value).toLocaleDateString("ru-RU");
}

function formatTaskDue(value?: string | null) {
  if (!value) return "Без срока";
  return new Date(value).toLocaleString("ru-RU", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
}

function isTaskDueToday(task: Task) {
  if (!task.due_at) return false;
  const due = new Date(task.due_at);
  const now = new Date();
  return due.toDateString() === now.toDateString();
}

function isTaskCompleted(task: Task) {
  return Boolean(task.done_at || task.status === "completed");
}

function isTaskOverdue(task: Task) {
  return Boolean(!isTaskCompleted(task) && task.due_at && new Date(task.due_at).getTime() < Date.now());
}

function taskPriorityLabel(priority: string) {
  return statusLabel(priority, "priority");
}

function taskPriorityTone(priority: string) {
  if (priority === "urgent" || priority === "high") return "high";
  if (priority === "low") return "low";
  return "medium";
}

function taskDealTitle(task: Task) {
  return deals.value.find((deal) => deal.id === task.deal_id)?.title ?? workspace.value?.company.name ?? "Компания";
}

function relativeDate(value?: string | null) {
  if (!value) return "Нет данных";
  const days = Math.max(0, Math.floor((Date.now() - new Date(value).getTime()) / 86_400_000));
  if (days === 0) return "Сегодня";
  if (days === 1) return "Вчера";
  return `${days} дней назад`;
}

function timelineWhen(value: string) {
  return `${relativeDate(value)}\n${new Date(value).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })}`;
}

function formatFileSize(value: number | null) {
  if (!value) return "";
  if (value < 1_000_000) return `${Math.round(value / 1000)} KB`;
  return `${(value / 1_000_000).toFixed(1)} MB`;
}

function close() {
  emit("close");
}

function openContactCrud(contact: Contact | null = null, mode: "view" | "edit" | "create" = contact ? "view" : "create") {
  crudEntityType.value = "contacts";
  crudRecord.value = contact;
  crudInitialMode.value = mode;
}

function openNoteCrud(note: Note | null = null, mode: "view" | "edit" | "create" = note ? "view" : "create") {
  crudEntityType.value = "notes";
  crudRecord.value = note;
  crudInitialMode.value = mode;
}

async function closeCrud(refresh = false) {
  crudEntityType.value = null;
  crudRecord.value = null;
  if (refresh) await reloadWorkspace();
}

async function reloadWorkspace() {
  if (!props.company) return;
  await crmStore.refreshAll();
  await crmStore.loadCompanyWorkspace(props.company.id);
  await crmStore.refreshCompanyCopilot(props.company.id);
}

async function runDrawerAction(action: () => Promise<void>) {
  if (!props.company) return;
  isSaving.value = true;
  crmStore.error.value = "";
  crmStore.ok.value = "";
  try {
    await action();
    await reloadWorkspace();
    crmStore.ok.value = "Данные компании обновлены";
  } catch (caught) {
    crmStore.error.value = caught instanceof Error ? caught.message : "Неизвестная ошибка";
  } finally {
    isSaving.value = false;
  }
}

async function createActivity(type: string, channel: string, title: string, description: string) {
  if (!props.company) return;
  await api<Activity>(
    "/activities",
    post({
      company_id: props.company.id,
      contact_id: contacts.value[0]?.id ?? null,
      deal_id: currentDeal.value?.id ?? null,
      type,
      channel,
      title,
      description,
      metadata: { source: "company_modal" }
    }),
    crmStore.token.value,
    crmStore.tenantId.value
  );
}

function logCall() {
  void runDrawerAction(() => createActivity("CALL", "Звонок", "Звонок завершён", `Следующий шаг: ${nextAction.value}`));
}

function logEmail() {
  void runDrawerAction(() => createActivity("EMAIL", "Email", "Письмо отправлено", `Повторный контакт с ${workspace.value?.company.name ?? "компанией"}`));
}

function logMeeting() {
  void runDrawerAction(() => createActivity("MEETING", "Встреча", "Встреча запланирована", "Встреча создана из карточки компании."));
}

function addQuickTask() {
  if (!props.company) return;
  void runDrawerAction(async () => {
    await api<Task>(
      "/sales/tasks",
      post(emptyToNull({
        company_id: props.company?.id,
        deal_id: currentDeal.value?.id ?? "",
        title: nextAction.value,
        description: "Создано быстрым действием из карточки компании.",
        priority: "high",
        due_at: ""
      })),
      crmStore.token.value,
      crmStore.tenantId.value
    );
  });
}

function logNote() {
  void runDrawerAction(() => createActivity("COMMENT", "Сообщение", "Добавлена заметка", "Быстрая заметка из карточки компании."));
}

function openDrawerAction(mode: "call" | "email" | "meeting" | "task") {
  drawerActionMode.value = mode;
  callForm.value.phone = contacts.value[0]?.phone ?? "";
  emailForm.value.recipient = contacts.value[0]?.email ?? "";
  emailForm.value.body = copilot.value?.follow_up_draft ?? `Здравствуйте! Следующий шаг: ${nextAction.value}.`;
  drawerTaskForm.value.title = nextAction.value;
}

function openContactAction(mode: "call" | "email" | "meeting", contactId: string) {
  const contact = contacts.value.find((item) => item.id === contactId);
  drawerActionMode.value = mode;
  callForm.value.phone = contact?.phone ?? "";
  emailForm.value.recipient = contact?.email ?? "";
  emailForm.value.subject = `Follow-up: ${workspace.value?.company.name ?? ""}`;
  emailForm.value.body = copilot.value?.follow_up_draft ?? `Здравствуйте, ${contact?.name ?? ""}! Следующий шаг: ${nextAction.value}.`;
  meetingActionForm.value.subject = `Встреча: ${workspace.value?.company.name ?? ""}`;
}

async function saveCompanyNote() {
  if (!currentDeal.value) {
    logNote();
    crmStore.noteForm.value.text = "";
    return;
  }
  await crmStore.createNote("deal", currentDeal.value.id);
  if (!crmStore.error.value) crmStore.noteForm.value.text = "";
}

async function saveCommunication(
  channel: string,
  subject: string,
  body: string,
  occurredAt?: string,
  recipient?: string
) {
  const event = await api<CommunicationEvent>(
    "/communication/events",
    post(emptyToNull({
      channel,
      direction: "outbound",
      sender: crmStore.me.value?.email ?? "",
      recipient: recipient ?? "",
      subject,
      body,
      occurred_at: occurredAt ?? "",
      company_id: props.company?.id,
      contact_id: contacts.value[0]?.id ?? "",
      deal_id: currentDeal.value?.id ?? "",
      metadata: { source: "company_drawer", draft: channel === "email" }
    })),
    crmStore.token.value,
    crmStore.tenantId.value
  );
  await api<CommunicationEvent>(
    `/communication/events/${event.id}/activity`,
    post({}),
    crmStore.token.value,
    crmStore.tenantId.value
  );
}

function saveCall() {
  void runDrawerAction(async () => {
    await saveCommunication("call", callForm.value.subject, callForm.value.body, undefined, callForm.value.phone);
    drawerActionMode.value = null;
  });
}

function saveEmailDraft() {
  void runDrawerAction(async () => {
    await saveCommunication("email", emailForm.value.subject, emailForm.value.body, undefined, emailForm.value.recipient);
    drawerActionMode.value = null;
  });
}

function saveMeeting() {
  void runDrawerAction(async () => {
    await saveCommunication("meeting", meetingActionForm.value.subject, meetingActionForm.value.body, meetingActionForm.value.occurred_at);
    drawerActionMode.value = null;
  });
}

function saveDrawerTask() {
  void runDrawerAction(async () => {
    await api<Task>(
      "/sales/tasks",
      post(emptyToNull({
        ...drawerTaskForm.value,
        company_id: props.company?.id,
        deal_id: currentDeal.value?.id ?? ""
      })),
      crmStore.token.value,
      crmStore.tenantId.value
    );
    drawerActionMode.value = null;
  });
}

function toggleDrawerTask(task: Task) {
  void runDrawerAction(async () => {
    await api<Task>(
      `/sales/tasks/${task.id}/done`,
      post({ is_done: !task.done_at, version: task.version }, "PATCH"),
      crmStore.token.value,
      crmStore.tenantId.value
    );
  });
}

async function askCompanyKnowledge() {
  if (!props.company) return;
  knowledgeIsLoading.value = true;
  knowledgeError.value = "";
  try {
    const succeeded = currentDeal.value
      ? await crmStore.askKnowledge({
          scope: "deal",
          company_id: props.company.id,
          deal_id: currentDeal.value.id,
          include_global: includeGlobalKnowledge.value
        })
      : await crmStore.askKnowledge({
          scope: "company",
          company_id: props.company.id,
          include_global: includeGlobalKnowledge.value
        });
    if (!succeeded) knowledgeError.value = crmStore.error.value || "Не удалось получить ответ";
  } finally {
    knowledgeIsLoading.value = false;
  }
}

function chooseCompanyKnowledgeFile() {
  knowledgeFileInput.value?.click();
}

function uploadCompanyKnowledgeFile(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  input.value = "";
  if (!file || !props.company) return;
  void runDrawerAction(async () => {
    const succeeded = await crmStore.uploadKnowledgeDocument(file, currentDeal.value
      ? {
          scope: "deal",
          company_id: props.company?.id,
          deal_id: currentDeal.value.id
        }
      : {
          scope: "company",
          company_id: props.company?.id
        });
    if (!succeeded) throw new Error(crmStore.error.value || "Не удалось загрузить файл");
  });
}

function openKnowledgeSource(sourceId: string) {
  const document = knowledgeDocuments.value.find((item) => item.id === sourceId);
  if (document?.download_url) void crmStore.downloadKnowledgeDocument(document);
}

function openCompanyAgent() {
  if (!props.company) return;
  crmStore.openAgent(currentDeal.value
    ? {
        type: "deal",
        company_id: props.company.id,
        deal_id: currentDeal.value.id
      }
    : {
        type: "company",
        company_id: props.company.id
      });
}

function askKnowledgeSource(sourceId: string) {
  const document = knowledgeDocuments.value.find((item) => item.id === sourceId);
  if (!document) return;
  crmStore.openAgent(
    {
      type: "document",
      document_id: document.id,
      company_id: document.company_id ?? null,
      deal_id: document.deal_id ?? null
    },
    `Что важно знать из документа «${document.title}»?`
  );
}

function confirmCopilotAction(actionId: string) {
  void runDrawerAction(() => crmStore.confirmAgentAction(actionId));
}

function rejectCopilotAction(actionId: string) {
  void runDrawerAction(() => crmStore.rejectAgentAction(actionId));
}

function completeNextAction() {
  if (!nextActionRecord.value) return;
  void runDrawerAction(async () => {
    await api<NextAction>(
      `/sales/next-actions/${nextActionRecord.value?.id}/done`,
      post({ is_done: true }, "PATCH"),
      crmStore.token.value,
      crmStore.tenantId.value
    );
  });
}

function openNextActionEditor() {
  nextActionForm.value = {
    title: nextActionRecord.value?.title ?? nextAction.value,
    description: nextActionRecord.value?.description ?? "",
    due_at: nextActionRecord.value?.due_at?.slice(0, 16) ?? "",
    priority: nextActionRecord.value?.priority ?? "high"
  };
  isNextActionEditorOpen.value = true;
}

function saveNextAction() {
  if (!props.company) return;
  void runDrawerAction(async () => {
    const previousActionId = nextActionRecord.value?.id;
    await api<NextAction>(
      "/sales/next-actions",
      post(emptyToNull({
        ...nextActionForm.value,
        company_id: props.company?.id,
        deal_id: currentDeal.value?.id ?? "",
        contact_id: contacts.value[0]?.id ?? "",
        source: "manual"
      })),
      crmStore.token.value,
      crmStore.tenantId.value
    );
    if (previousActionId) {
      await api<NextAction>(
        `/sales/next-actions/${previousActionId}/done`,
        post({ is_done: true }, "PATCH"),
        crmStore.token.value,
        crmStore.tenantId.value
      );
    }
    isNextActionEditorOpen.value = false;
  });
}
</script>

<template>
  <div v-if="company" :class="embedded ? 'company-workspace-host' : 'workspace-modal-backdrop'" @click.self="embedded ? undefined : close()">
    <section v-if="workspace" class="company-modal" :class="{ 'company-modal--embedded': embedded }" :role="embedded ? undefined : 'dialog'" :aria-modal="embedded ? undefined : true" aria-labelledby="company-workspace-title">
      <header class="company-modal__header">
        <div class="company-modal__heading">
          <div class="company-modal__breadcrumb">Компании / {{ workspace.company.name }}</div>
          <div class="company-modal__title-row">
            <h2 id="company-workspace-title" class="company-modal__title">{{ workspace.company.name }}</h2>
            <span class="cm-badge cm-badge--neutral">{{ companyType }}</span>
            <span class="cm-badge cm-badge--success">{{ workspace.company.status_label ?? statusLabel(workspace.company.status, "company") }}</span>
          </div>
          <div class="company-modal__meta">
            <span>{{ displayIndustry }}</span>
            <span>•</span>
            <span>Клиент с {{ formatDate(clientSince) }}</span>
            <span>•</span>
            <span class="cm-truncate">ID: {{ workspace.company.id }}</span>
          </div>
        </div>

        <div class="company-modal__header-actions">
          <button type="button" @click="openCompanyAgent"><UiIcon name="sparkles" :size="16" /> AI</button>
          <button type="button" aria-label="Дополнительные действия" :disabled="isSaving" @click="logNote">...</button>
          <button type="button" @click="openDrawerAction('task')">Изменить</button>
          <button type="button" class="is-primary" @click="activeTab = 'deals'"><UiIcon name="plus" :size="16" /> Сделка</button>
          <button type="button" :aria-label="embedded ? undefined : 'Закрыть'" @click="close"><UiIcon :name="embedded ? 'chevronLeft' : 'close'" :size="17" /><span v-if="embedded">Компании</span></button>
        </div>
      </header>

      <div class="company-modal__body">
        <main class="company-modal__main">
          <section class="company-kpi-grid">
            <article class="cm-card company-kpi">
              <div class="company-kpi__top">
                <div>
                  <div class="cm-label" title="Сводная оценка качества взаимодействия с компанией">Рейтинг отношений</div>
                  <div class="company-kpi__number">{{ health }}</div>
                </div>
                <span class="cm-badge cm-badge--success"><UiIcon :name="healthTrendIcon" :size="13" /> {{ workspace.health.success_chance_delta ?? 12 }}</span>
              </div>
              <div class="company-health-bar"><span :style="{ width: `${health}%` }"></span></div>
              <div class="company-kpi__description">{{ healthLabel }} · Основано на активности и сделках</div>
            </article>

            <article class="cm-card company-kpi company-kpi--with-visual">
              <div>
                <div class="cm-label">Сумма портфеля</div>
                <div class="company-kpi__number">{{ crmStore.money(pipeline) }}</div>
                <div class="company-kpi__description">{{ deals.length }} открытых сделок</div>
              </div>
              <div class="company-pipeline-donut" tabindex="0" aria-label="Структура портфеля">
                <span></span>
                <div class="company-pipeline-tooltip" role="tooltip">
                  <strong>{{ crmStore.money(pipeline) }}</strong>
                  <small>{{ deals.length }} открытых сделок</small>
                  <p v-for="row in pipelineBreakdown.slice(0, 4)" :key="row.title">
                    <span>{{ row.title }} · {{ row.count }}</span>
                    <b>{{ crmStore.money(row.amount) }}</b>
                  </p>
                  <p v-if="!pipelineBreakdown.length">
                    <span>Нет активных сделок</span>
                    <b>{{ crmStore.money(0) }}</b>
                  </p>
                </div>
              </div>
            </article>

            <article class="cm-card company-kpi company-kpi--with-visual">
              <div>
                <div class="cm-label">Открытые задачи</div>
                <div class="company-kpi__number">{{ openTasks.length }}</div>
                <div class="company-kpi__description">{{ tasks.filter((task) => task.priority === "high" || task.priority === "urgent").length }} важных</div>
              </div>
              <div class="company-task-preview" aria-hidden="true">
                <span v-for="task in tasks.slice(0, 3)" :key="task.id" :class="{ done: Boolean(task.done_at) }">
                  <i><UiIcon v-if="task.done_at" name="check" :size="11" /></i>
                  <b></b>
                </span>
                <span v-if="!tasks.length"><i></i><b></b></span>
                <span v-if="tasks.length < 2"><i></i><b></b></span>
                <span v-if="tasks.length < 3"><i></i><b></b></span>
              </div>
            </article>
          </section>

          <section class="cm-card company-deals">
            <div class="cm-card__header">
              <h2 class="cm-card__title">Сделки ({{ deals.length }})</h2>
              <button type="button" class="cm-card__link" @click="activeTab = 'deals'">Показать все</button>
            </div>
            <div class="company-deals__grid">
              <RouterLink
                v-for="(row, index) in compactDealRows.slice(0, 5)"
                :key="row.deal.id"
                :to="{ path: '/deals', query: { deal: row.deal.id } }"
                class="company-deal-card"
                :style="{ '--deal-accent': index === 0 ? '#16a36a' : index === 1 ? '#0b72e7' : index === 2 ? '#e99a14' : index === 3 ? '#8b5cf6' : '#f97316' }"
              >
                <div class="company-deal-card__stage">{{ row.activeStageName }}</div>
                <div class="company-deal-card__name cm-line-clamp-2">{{ row.deal.title }}</div>
                <div class="company-deal-card__bottom">
                  <span class="company-deal-card__amount">{{ crmStore.money(row.deal.amount) }}</span>
                  <span class="cm-badge" :class="row.progress >= 70 ? 'cm-badge--success' : row.progress >= 40 ? 'cm-badge--warning' : 'cm-badge--danger'">{{ row.progress }}%</span>
                </div>
                <div class="company-deal-card__owner">
                  <span class="avatar-mini">{{ ownerInitials }}</span>
                  <span class="cm-truncate">{{ ownerName }}</span>
                </div>
              </RouterLink>
              <article v-if="!compactDealRows.length" class="company-deal-card empty">
                <div class="company-deal-card__name">У компании пока нет сделок</div>
              </article>
            </div>
          </section>

      <section v-if="drawerActionMode" class="drawer-action-panel">
        <header><h2>{{ drawerActionMode === "call" ? "Звонок" : drawerActionMode === "email" ? "Черновик письма" : drawerActionMode === "meeting" ? "Встреча" : "Задача" }}</h2><button class="secondary" type="button" @click="drawerActionMode = null">Закрыть</button></header>
        <form v-if="drawerActionMode === 'call'" class="compact-form" @submit.prevent="saveCall">
          <label>Телефон<input v-model="callForm.phone" type="tel" /></label><label>Тема<input v-model="callForm.subject" /></label><label>Результат<textarea v-model="callForm.body"></textarea></label>
          <div class="button-row"><a v-if="callForm.phone" class="button-link" :href="`tel:${callForm.phone}`">Начать звонок</a><button type="submit">Сохранить результат</button></div>
        </form>
        <form v-else-if="drawerActionMode === 'email'" class="compact-form" @submit.prevent="saveEmailDraft">
          <label>Получатель<input v-model="emailForm.recipient" type="email" /></label><label>Тема<input v-model="emailForm.subject" /></label><label>Черновик AI<textarea v-model="emailForm.body" rows="7"></textarea></label><button type="submit">Сохранить черновик</button>
        </form>
        <form v-else-if="drawerActionMode === 'meeting'" class="compact-form" @submit.prevent="saveMeeting">
          <label>Название<input v-model="meetingActionForm.subject" /></label><label>Дата<input v-model="meetingActionForm.occurred_at" type="datetime-local" required /></label><label>Повестка<textarea v-model="meetingActionForm.body"></textarea></label><button type="submit">Запланировать</button>
        </form>
        <form v-else class="compact-form" @submit.prevent="saveDrawerTask">
          <label>Задача<input v-model="drawerTaskForm.title" /></label><label>Описание<textarea v-model="drawerTaskForm.description"></textarea></label><label>Срок<input v-model="drawerTaskForm.due_at" type="datetime-local" /></label><label>Приоритет<select v-model="drawerTaskForm.priority"><option value="normal">Средний</option><option value="high">Высокий</option><option value="urgent">Срочный</option></select></label><button type="submit">Создать задачу</button>
        </form>
      </section>

      <nav class="company-tabs" aria-label="Разделы компании">
        <button v-for="tab in tabs" :key="tab.code" type="button" class="company-tab" :class="{ 'is-active': activeTab === tab.code }" @click="activeTab = tab.code">{{ tab.label }}</button>
      </nav>

      <main v-if="activeTab === 'overview'" class="company-overview">
        <CustomFieldsForm v-if="company" entity-type="companies" :entity-id="company.id" :editable="crmStore.me.value?.permissions.includes('crm:write')" />
        <section class="company-overview-grid">
        <section class="cm-card company-about">
          <div class="cm-card__header"><h2 class="cm-card__title">О компании</h2></div>
          <dl class="company-details">
            <dt>Индустрия</dt><dd>{{ displayIndustry }}</dd>
            <dt>Тип клиента</dt><dd>{{ companyType }}</dd>
            <dt>Источник</dt><dd>{{ source }}</dd>
            <dt>Ответственный</dt><dd>{{ ownerName }}</dd>
            <dt>Последний контакт</dt><dd>{{ lastContactAt }}</dd>
            <dt>Каналы</dt><dd>{{ channelSummary }}</dd>
          </dl>
        </section>

        <section class="cm-card company-ai">
          <div class="cm-card__header">
            <h2 class="cm-card__title">AI Рекомендации</h2>
            <button type="button" class="cm-card__link">Все рекомендации</button>
          </div>
          <div class="company-ai__list">
            <article v-for="item in copilotRecommendations.slice(0, 3)" :key="`${item.title}-${item.description}`" class="company-ai__item">
              <div class="company-ai__icon"><UiIcon :name="item.type === 'warning' ? 'alert' : item.type === 'success' ? 'check' : 'info'" :size="15" /></div>
              <div>
                <div class="company-ai__title cm-truncate">{{ item.title }}</div>
                <div class="company-ai__text cm-line-clamp-2">{{ item.description }}</div>
              </div>
            </article>
          </div>
        </section>
        </section>

        <section class="cm-card company-activity">
          <div class="cm-card__header">
            <h2 class="cm-card__title">Недавняя активность</h2>
            <button type="button" class="cm-card__link" @click="activeTab = 'timeline'">Вся активность</button>
          </div>
          <div class="company-activity__list">
            <article v-for="row in timelineRows.slice(0, 4)" :key="row.id" class="company-activity__item">
              <span class="company-activity__date">{{ String(row.when).split('\n')[0] }}</span>
              <span class="activity-dot"></span>
              <span class="company-activity__person">{{ row.by }}</span>
              <span class="company-activity__description">{{ row.title }}</span>
              <span class="company-activity__type">{{ row.icon }}</span>
            </article>
          </div>
        </section>
      </main>

      <main v-else class="reference-tab-body">
        <section v-if="activeTab === 'timeline'" class="ref-card tab-panel">
          <h2>История</h2>
          <article v-for="row in timelineRows" :key="row.id" class="history-row"><time>{{ row.when }}</time><span class="history-node"></span><span class="ui-icon" :class="row.icon"></span><div><strong>{{ row.title }}</strong><small>{{ row.by }}</small></div></article>
        </section>

        <section v-else-if="activeTab === 'contacts'" class="ref-card tab-panel">
          <div class="tab-panel-head">
            <div>
              <h2>Контакты</h2>
              <p class="hint">Контактов: {{ contacts.length }}</p>
            </div>
            <button type="button" class="secondary" @click="openContactCrud()"><UiIcon name="plus" :size="16" /> Добавить контакт</button>
          </div>
          <section class="contact-tab-grid">
            <article v-for="contact in contacts" :key="contact.id" class="contact-tab-card">
              <header>
                <span class="contact-avatar">{{ contact.name.slice(0, 2).toUpperCase() }}</span>
                <div>
                  <strong>{{ contact.name }}</strong>
                  <small>{{ contact.role ?? contact.company_name ?? "Контакт" }}</small>
                </div>
              </header>
              <dl>
                <div><dt>Email</dt><dd>{{ contact.email ?? "не указан" }}</dd></div>
                <div><dt>Телефон</dt><dd>{{ contact.phone ?? "не указан" }}</dd></div>
              </dl>
              <footer>
                <button type="button" class="secondary" :disabled="!contact.email" @click="openContactAction('email', contact.id)">Написать</button>
                <button type="button" class="secondary" :disabled="!contact.phone" @click="openContactAction('call', contact.id)">Позвонить</button>
                <button type="button" class="secondary" @click="openContactAction('meeting', contact.id)">Встреча</button>
                <button type="button" @click="openContactCrud(contact, 'edit')">Редактировать</button>
              </footer>
            </article>
          </section>
          <section v-if="!contacts.length" class="empty-state"><strong>Контактов пока нет</strong><p>Добавьте контактное лицо компании.</p></section>
        </section>

        <section v-else-if="activeTab === 'sequences'" class="ref-card tab-panel">
          <CadencePanel :company-id="company.id" :contacts="contacts" :deals="deals" />
        </section>

        <section v-else-if="activeTab === 'deals'" class="ref-card tab-panel">
          <div class="tab-panel-head">
            <div>
              <h2>Сделки</h2>
              <p class="hint">Активных сделок: {{ deals.length }}</p>
            </div>
            <RouterLink class="secondary-link" to="/deals">Открыть воронку</RouterLink>
          </div>
          <RouterLink
            v-for="row in dealStageRows"
            :key="row.deal.id"
            class="deal-tab-card"
            :to="{ path: '/deals', query: { deal: row.deal.id } }"
          >
            <header>
              <div>
                <strong>{{ row.deal.title }}</strong>
                <small>{{ formatStageName(row.stages[row.activeIndex]?.name) }} · {{ statusLabel(row.deal.status, "deal") }}</small>
              </div>
              <b>{{ crmStore.money(row.deal.amount) }}</b>
            </header>
            <div class="deal-tab-stage-labels">
              <div
                v-for="(stage, index) in row.stages"
                :key="stage.id"
                class="deal-tab-stage-step"
                :class="{ done: index < row.activeIndex, active: index === row.activeIndex }"
              >
                <span><UiIcon v-if="index < row.activeIndex" name="check" :size="12" /><template v-else>{{ index + 1 }}</template></span>
                <strong>{{ formatStageName(stage.name) }}</strong>
              </div>
            </div>
          </RouterLink>
          <section v-if="!deals.length" class="empty-state"><strong>Сделок пока нет</strong><p>Создайте первую сделку для этой компании.</p><RouterLink class="button-link" to="/deals?create=1">Создать сделку</RouterLink></section>
        </section>

        <section v-else-if="activeTab === 'tasks'" class="company-tasks-tab" aria-label="Задачи компании">
          <section class="company-tasks-panel">
            <header class="company-tasks-header">
              <div class="company-tasks-heading">
                <h2 class="company-tasks-title">Задачи</h2>
                <div class="company-tasks-subtitle">{{ tasks.length }} задач по компании</div>
              </div>
              <section class="company-tasks-summary" aria-label="Сводка задач">
                <div class="company-tasks-summary-item">
                  <span class="company-tasks-summary-label">Открыто</span>
                  <strong class="company-tasks-summary-value">{{ taskStats.open }}</strong>
                </div>
                <div class="company-tasks-summary-item is-danger">
                  <span class="company-tasks-summary-label">Важные</span>
                  <strong class="company-tasks-summary-value">{{ taskStats.high }}</strong>
                </div>
                <div class="company-tasks-summary-item is-danger">
                  <span class="company-tasks-summary-label">Просрочено</span>
                  <strong class="company-tasks-summary-value">{{ taskStats.overdue }}</strong>
                </div>
              </section>
            </header>

            <div class="company-tasks-toolbar" aria-label="Фильтры задач">
              <div class="company-task-status-filters" role="tablist" aria-label="Статус задач">
                <button type="button" class="company-task-filter" :class="{ 'is-active': taskFilter === 'all' }" @click="taskFilter = 'all'">Все</button>
                <button type="button" class="company-task-filter" :class="{ 'is-active': taskFilter === 'open' }" @click="taskFilter = 'open'">Открытые</button>
                <button type="button" class="company-task-filter" :class="{ 'is-active': taskFilter === 'overdue' }" @click="taskFilter = 'overdue'">Просроченные</button>
                <button type="button" class="company-task-filter" :class="{ 'is-active': taskFilter === 'done' }" @click="taskFilter = 'done'">Готово</button>
              </div>
              <label class="company-task-search"><input v-model="taskSearch" type="search" placeholder="Поиск задач..." /></label>
              <select v-model="taskPriorityFilter" class="company-task-priority-select">
                <option value="all">Приоритет: Все</option>
                <option value="urgent">Срочный</option>
                <option value="high">Высокий</option>
                <option value="normal">Средний</option>
                <option value="low">Низкий</option>
              </select>
              <button type="button" class="company-task-view-button" aria-label="Дополнительные фильтры"><UiIcon name="filter" :size="17" /></button>
            </div>

            <div class="company-task-groups">
              <section v-for="group in groupedTasks" :key="group.key" class="company-task-group">
                <header class="company-task-group-header">
                  <h3 class="company-task-group-title">{{ group.title }}</h3>
                  <span class="company-task-group-count">{{ group.rows.length }}</span>
                </header>
                <div class="company-task-list">
                <article v-for="task in group.rows" :key="task.id" class="company-task-row" :class="{ 'is-completed': isTaskCompleted(task) }">
                  <button type="button" class="company-task-checkbox" :class="{ 'is-completed': isTaskCompleted(task) }" :aria-label="isTaskCompleted(task) ? 'Вернуть задачу в открытые' : 'Завершить задачу'" @click="toggleDrawerTask(task)">
                  </button>
                  <div class="company-task-content">
                    <div class="company-task-name">{{ task.title }}</div>
                    <div class="company-task-meta">
                      <span class="company-task-priority" :class="`company-task-priority--${taskPriorityTone(task.priority)}`"><UiIcon name="arrowUp" :size="13" /> {{ taskPriorityLabel(task.priority) }}</span>
                      <span v-if="task.due_at" class="company-task-meta-separator">•</span>
                      <span v-if="task.due_at" class="company-task-due">{{ formatTaskDue(task.due_at) }}</span>
                      <span class="company-task-meta-separator">•</span>
                      <span class="company-task-deal"><UiIcon name="externalLink" :size="13" /> {{ taskDealTitle(task) }}</span>
                    </div>
                  </div>
                  <div class="company-task-owner">
                    <span class="company-task-owner-avatar">{{ ownerInitials }}</span>
                    <span class="company-task-owner-name">{{ ownerName }}</span>
                  </div>
                  <button type="button" class="company-task-menu" aria-label="Действия с задачей">•••</button>
                </article>
                </div>
              </section>
              <section v-if="!groupedTasks.length" class="company-task-empty">
                <div class="company-task-empty-title">Задач не найдено</div>
                <div class="company-task-empty-text">Попробуйте изменить фильтр или поисковый запрос.</div>
              </section>
            </div>
          </section>
        </section>

        <section v-else-if="activeTab === 'files'" class="ref-card tab-panel">
          <h2>Файлы</h2>
          <article v-for="file in files" :key="file.id" class="entity-row"><div><strong>{{ file.name }}</strong><small>{{ file.file_type ?? "файл" }} · {{ formatFileSize(file.file_size) }}</small></div><a v-if="file.download_url" class="button-link secondary-link" :href="file.download_url">Открыть</a></article>
          <section v-if="!files.length" class="empty-state"><strong>Файлов пока нет</strong><p>Загрузите документ в базе знаний компании.</p></section>
        </section>

        <section v-else-if="activeTab === 'knowledge'" class="company-knowledge" aria-label="База знаний компании">
          <aside class="knowledge-card knowledge-sources">
            <header>
              <h2>База знаний компании</h2>
              <p>Область: {{ workspace.company.name }}<span v-if="currentDeal"> · {{ currentDeal.title }}</span></p>
            </header>
            <section class="knowledge-primary-doc" v-if="knowledgeDocuments[0]">
              <strong>{{ knowledgeDocuments[0].title }}</strong>
              <span>{{ knowledgeDocuments[0].visibility === "deal" ? "Сделка" : "Компания" }}</span>
            </section>
            <section class="knowledge-source-list">
              <h3>Источники контекста <span>{{ knowledgeSources.length }}</span></h3>
              <article v-for="source in knowledgeSources" :key="source.id" class="knowledge-source-card">
                <span class="knowledge-source-icon">{{ source.type.slice(0, 4) }}</span>
                <div>
                  <strong>{{ source.title }}</strong>
                  <small>{{ source.meta }}</small>
                </div>
                <button type="button" aria-label="Задать вопрос по источнику" @click="askKnowledgeSource(source.id)"><UiIcon name="sparkles" :size="16" /></button>
                <button type="button" :disabled="!source.downloadable" aria-label="Скачать источник" @click="openKnowledgeSource(source.id)"><UiIcon name="chevronRight" :size="17" /></button>
              </article>
              <p v-if="!knowledgeSources.length" class="empty">Источники пока не добавлены</p>
            </section>
            <input
              ref="knowledgeFileInput"
              hidden
              type="file"
              accept=".pdf,.docx,.txt"
              @change="uploadCompanyKnowledgeFile"
            />
            <button type="button" class="knowledge-manage-button" :disabled="isSaving" @click="chooseCompanyKnowledgeFile">
              {{ isSaving ? "Загрузка и индексация…" : "+ Загрузить PDF, DOCX или TXT" }}
            </button>
          </aside>

          <section class="knowledge-card knowledge-workspace">
            <h2>Задать вопрос</h2>
            <form class="knowledge-composer" @submit.prevent="askCompanyKnowledge">
              <label>Ваш вопрос</label>
              <div class="knowledge-question-wrap">
                <textarea
                  v-model="crmStore.knowledgeAskForm.value.question"
                  class="knowledge-question"
                  placeholder="Как квалифицировать B2B сделку?"
                  @keydown.enter.exact.prevent="askCompanyKnowledge"
                ></textarea>
                <button type="button" class="knowledge-voice" aria-label="Голосовой ввод"><UiIcon name="microphone" :size="17" /></button>
                <button type="submit" class="knowledge-submit" :disabled="knowledgeIsLoading" aria-label="Отправить вопрос"><span v-if="knowledgeIsLoading">…</span><UiIcon v-else name="send" :size="17" /></button>
              </div>
            </form>
            <section class="knowledge-controls">
              <select>
                <option>{{ currentDeal ? "Режим: сделка и компания" : "Режим: только компания" }}</option>
              </select>
              <label class="knowledge-toggle"><input v-model="includeGlobalKnowledge" type="checkbox" /><span></span>Включать общие знания</label>
              <button type="button"><UiIcon name="refresh" :size="15" /> История запросов</button>
            </section>
            <section class="knowledge-answer-head">
              <div><strong>Ответ</strong><span v-if="knowledgeCitations.length">На основе {{ knowledgeCitations.length }} источников</span></div>
              <time v-if="companyKnowledgeAnswer">2 мин. назад</time>
            </section>
            <section v-if="knowledgeIsLoading" class="knowledge-answer-card knowledge-loading" aria-live="polite">
              <div class="knowledge-answer-summary"><strong>Ищу информацию в {{ knowledgeSources.length || 1 }} источниках...</strong><p class="knowledge-answer-text">Собираю контекст по компании и активной сделке.</p></div>
            </section>
            <p v-else-if="knowledgeError" class="knowledge-alert" role="alert">{{ knowledgeError }}</p>
            <section v-else-if="companyKnowledgeAnswer" class="knowledge-answer-card" aria-live="polite">
              <article class="knowledge-answer-summary">
                <header><UiIcon name="sparkles" :size="17" /><strong>Краткий ответ</strong><div><button type="button" aria-label="Копировать"><UiIcon name="copy" :size="15" /></button><button type="button" aria-label="Полезный ответ"><UiIcon name="heart" :size="15" /></button><button type="button" aria-label="Действия AI"><UiIcon name="sparkles" :size="15" /></button></div></header>
                <p class="knowledge-answer-text">{{ companyKnowledgeAnswer.answer }}</p>
              </article>
              <article class="knowledge-evidence">
                <h3>Детали из контекста</h3>
                <ul>
                  <li v-for="citation in knowledgeCitations.slice(0, 3)" :key="citation.chunk_id">
                    <span>{{ citation.document_title }}</span>
                    <em>{{ citation.document_scope }}</em>
                  </li>
                </ul>
              </article>
            </section>
            <section v-else class="knowledge-empty">
              <h3>Задайте вопрос о компании</h3>
              <p>Ответ будет сформирован по сделкам, заметкам, письмам и файлам.</p>
            </section>
            <section class="knowledge-suggestions">
              <h3>Похожие вопросы</h3>
              <button type="button" class="knowledge-suggestion" @click="crmStore.knowledgeAskForm.value.question = 'Какие следующие шаги по сделке?'"><UiIcon name="search" :size="15" /> Какие следующие шаги по сделке?</button>
              <button type="button" class="knowledge-suggestion" @click="crmStore.knowledgeAskForm.value.question = 'Какой уровень риска у сделки?'"><UiIcon name="search" :size="15" /> Какой уровень риска у сделки?</button>
              <button type="button" class="knowledge-suggestion" @click="crmStore.knowledgeAskForm.value.question = 'Какая сумма в коммерческом предложении?'"><UiIcon name="search" :size="15" /> Какая сумма в коммерческом предложении?</button>
            </section>
            <p class="knowledge-footnote"><UiIcon name="info" :size="15" /> Ответ сформирован на основе данных компании и конкретной сделки.</p>
          </section>
        </section>

        <section v-else class="ref-card tab-panel">
          <h2>История изменений</h2>
          <article v-for="row in historyRows" :key="`${row.activity.id}-${row.change.field}`" class="history-change-row"><span>{{ row.change.field.replace(/_/g, " ") }}</span><div><strong>{{ row.change.old ?? "пусто" }}</strong><small>изменено на</small><strong>{{ row.change.new ?? "пусто" }}</strong></div><small>{{ new Date(row.activity.created_at).toLocaleString("ru-RU") }}</small></article>
          <p v-if="!historyRows.length" class="empty">Отслеживаемых изменений пока нет</p>
        </section>
      </main>
        </main>

      <aside class="company-modal__rail">
        <section class="cm-card company-manager-notes" role="button" tabindex="0" @click="isNotesSpaceOpen = true" @keydown.enter="isNotesSpaceOpen = true">
          <div class="cm-card__header"><h2 class="cm-card__title">Заметки менеджера</h2><button type="button" class="cm-card__link">Открыть</button></div>
          <form class="company-note-form" @click.stop @submit.prevent="saveCompanyNote">
            <input v-model="crmStore.noteForm.value.text" class="company-note-input" placeholder="Добавить заметку..." />
            <button type="submit" class="company-note-submit" :disabled="crmStore.isLoading.value">Добавить</button>
          </form>
          <article v-for="note in companyNotes.slice(0, 2)" :key="note.id" class="company-note">
            <div class="company-note__header">
              <span class="company-note__avatar avatar-mini">{{ ownerInitials }}</span>
              <span class="company-note__author">{{ ownerName }}</span>
              <time class="company-note__date">{{ note.created_at ? new Date(note.created_at).toLocaleString("ru-RU") : "Сегодня" }}</time>
            </div>
            <p class="company-note__text">{{ note.text }}</p>
          </article>
          <article v-if="!companyNotes.length" class="company-note">
            <div class="company-note__header">
              <span class="company-note__avatar avatar-mini">{{ ownerInitials }}</span>
              <span class="company-note__author">{{ ownerName }}</span>
              <time class="company-note__date">Сегодня</time>
            </div>
            <p class="company-note__text">Добавьте важный контекст по клиенту, чтобы команда видела следующий шаг.</p>
          </article>
        </section>

        <section class="cm-card company-rail-card company-rail-tasks">
          <div class="cm-card__header"><h2 class="cm-card__title">Открытые задачи ({{ openTasks.length }})</h2><button type="button" class="cm-card__link" @click="activeTab = 'tasks'">Показать все</button></div>
          <form class="company-quick-task" @submit.prevent="saveDrawerTask">
            <input v-model="drawerTaskForm.title" placeholder="Добавить задачу..." />
            <button type="submit" :disabled="isSaving || !drawerTaskForm.title.trim()">+</button>
          </form>
          <div class="company-rail-list">
            <label v-for="task in openTasks.slice(0, 5)" :key="task.id" class="company-task">
              <input class="company-task__checkbox" type="checkbox" :checked="Boolean(task.done_at)" @change="toggleDrawerTask(task)" />
              <span><span class="company-task__title">{{ task.title }}</span><span class="company-task__date">{{ task.due_at ? formatDate(task.due_at) : "Сегодня" }}</span></span>
              <span class="cm-badge" :class="task.priority === 'high' || task.priority === 'urgent' ? 'cm-badge--danger' : 'cm-badge--neutral'">{{ statusLabel(task.priority, "priority") }}</span>
            </label>
            <article v-if="!openTasks.length" class="company-task">
              <span class="task-circle"></span>
              <span><span class="company-task__title">Открытых задач нет</span><span class="company-task__date">Все закрыто</span></span>
            </article>
          </div>
        </section>
      </aside>
      </div>

      <div v-if="isNotesSpaceOpen" class="notes-drawer-overlay" @click="isNotesSpaceOpen = false"></div>
      <aside
        v-if="isNotesSpaceOpen"
        class="notes-drawer"
        role="dialog"
        aria-modal="true"
        aria-labelledby="company-notes-title"
      >
        <header class="notes-drawer__header">
          <h2 id="company-notes-title" class="notes-drawer__title">Заметки по компании</h2>
          <button class="notes-drawer__close" type="button" aria-label="Закрыть заметки" @click="isNotesSpaceOpen = false"><UiIcon name="close" :size="20" /></button>
        </header>

        <nav class="notes-drawer__tabs" aria-label="Фильтр заметок">
          <button class="notes-drawer__tab is-active" type="button">Все заметки</button>
          <button class="notes-drawer__tab" type="button">Мои заметки</button>
        </nav>

        <section class="notes-drawer__composer">
          <form class="notes-drawer__composer-row" @submit.prevent="saveCompanyNote">
            <textarea v-model="crmStore.noteForm.value.text" class="notes-drawer__input" rows="1" placeholder="Добавить заметку..."></textarea>
            <button class="notes-drawer__submit" type="submit" :disabled="crmStore.isLoading.value">Добавить</button>
          </form>
          <button v-if="currentDeal" class="secondary" type="button" @click="openNoteCrud()">Расширенный редактор заметки</button>
        </section>

        <section class="notes-drawer__filters">
          <input v-model="notesSearch" class="notes-drawer__search" type="search" placeholder="Поиск по заметкам..." />
          <select class="notes-drawer__select" defaultValue="all">
            <option value="all">Все авторы</option>
            <option value="me">Только мои</option>
          </select>
          <button class="notes-drawer__filter-button" type="button" aria-label="Дополнительные фильтры"><UiIcon name="filter" :size="17" /></button>
        </section>

        <div class="notes-drawer__content">
          <article
            v-for="(note, index) in filteredCompanyNotes.slice(0, 5)"
            :key="note.id"
            class="notes-drawer__note"
            :class="{ 'is-pinned': index === 0 }"
          >
            <header class="notes-drawer__note-header">
              <div class="notes-drawer__avatar avatar-mini">{{ ownerInitials }}</div>
              <span class="notes-drawer__author">{{ ownerName }}</span>
              <time class="notes-drawer__date">{{ note.created_at ? new Date(note.created_at).toLocaleString("ru-RU", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" }) : "Сегодня" }}</time>
              <button class="notes-drawer__menu" type="button" aria-label="Действия с заметкой" @click="openNoteCrud(note)">•••</button>
            </header>
            <p class="notes-drawer__note-body">{{ note.text }}</p>
            <footer v-if="index === 0" class="notes-drawer__note-actions">
              <button class="notes-drawer__note-action" type="button" @click="openNoteCrud(note, 'edit')">Редактировать</button>
              <button class="notes-drawer__note-action" type="button">Открепить</button>
            </footer>
          </article>
          <section v-if="!filteredCompanyNotes.length" class="notes-drawer__empty">
            <div>
              <div class="notes-drawer__empty-title">Заметок пока нет</div>
              <div class="notes-drawer__empty-text">Добавьте первый контекст по компании.</div>
            </div>
          </section>
        </div>

        <footer class="notes-drawer__footer">
          <span class="notes-drawer__count">Показано {{ Math.min(filteredCompanyNotes.length, 5) }} из {{ companyNotes.length }} заметок</span>
          <button class="notes-drawer__load-more" type="button">Загрузить ещё</button>
        </footer>
      </aside>
      <EntityCrudDrawer
        v-if="crudEntityType"
        :entity-type="crudEntityType"
        :record="crudRecord"
        :initial-mode="crudInitialMode"
        :initial-values="crudEntityType === 'contacts' ? { company_id: company.id } : { company_id: company.id, deal_id: currentDeal?.id ?? '' }"
        @saved="closeCrud(true)"
        @removed="closeCrud(true)"
        @close="closeCrud()"
      />
    </section>

    <section v-else class="company-workspace-modal company-workspace-loading" role="dialog" aria-modal="true">
      <button class="secondary modal-close" type="button" @click="close">Закрыть</button>
      <p class="eyebrow">Рабочее пространство</p>
      <h2>{{ company.name }}</h2>
      <p class="hint">Загружаю рабочее пространство компании...</p>
    </section>
  </div>
</template>
