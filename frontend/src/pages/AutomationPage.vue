<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";

import UiIcon from "../components/ui/UiIcon.vue";
import { statusLabel } from "../design-system/statusDictionary";
import { automationStore } from "../stores/automation";
import { crmStore } from "../stores/crm";
import type {
  AutomationActionType,
  AutomationConditionOperator,
  AutomationMessageTemplate,
  AutomationTriggerType,
  AutomationWorkflow
} from "../types";

type Tab = "workflows" | "templates" | "runs" | "approvals" | "outbox";
type ConditionDraft = { field: string; operator: AutomationConditionOperator; value: string };
type ActionConfigDraft = {
  assignee: "owner" | "owner_manager" | "actor";
  user_id: string;
  title: string;
  description: string;
  due_in_days: number;
  due_in_hours: number;
  priority: "low" | "normal" | "high" | "critical";
  template_id: string;
  recipient: string;
  reason: string;
};
type ActionDraft = { type: AutomationActionType; config: ActionConfigDraft };

const tabs: Array<{ id: Tab; label: string }> = [
  { id: "workflows", label: "Сценарии" },
  { id: "templates", label: "Шаблоны" },
  { id: "runs", label: "Запуски" },
  { id: "approvals", label: "Согласования" },
  { id: "outbox", label: "Outbox" }
];
const triggers: Array<{ value: AutomationTriggerType; label: string }> = [
  { value: "lead.created", label: "Создан лид" },
  { value: "lead.score_changed", label: "Изменилась оценка лида" },
  { value: "deal.created", label: "Создана сделка" },
  { value: "deal.updated", label: "Изменена сделка" },
  { value: "deal.stage_changed", label: "Изменён этап сделки" },
  { value: "deal.score_changed", label: "Изменилась оценка сделки" },
  { value: "communication.created", label: "Создана коммуникация" },
  { value: "schedule.deal_inactive", label: "Сделка без активности" }
];
const triggerFields: Record<AutomationTriggerType, string[]> = {
  "lead.created": ["source", "status", "owner_id", "company_id", "title", "score", "score_grade"],
  "lead.score_changed": ["old_score", "new_score", "score_delta", "score_grade", "source", "status", "owner_id", "company_id", "title"],
  "deal.created": ["amount", "discount_percent", "status", "stage_id", "stage_name", "owner_id", "company_id", "opportunity_score", "score_grade", "forecast_probability"],
  "deal.updated": ["amount", "discount_percent", "status", "stage_id", "stage_name", "owner_id", "company_id", "changed_fields", "opportunity_score", "score_grade", "forecast_probability"],
  "deal.stage_changed": ["amount", "discount_percent", "status", "old_stage_id", "stage_id", "stage_name", "owner_id", "company_id", "opportunity_score", "score_grade", "forecast_probability"],
  "deal.score_changed": ["old_score", "new_score", "score_delta", "score_grade", "forecast_probability", "amount", "status", "stage_id", "stage_name", "owner_id", "company_id", "title"],
  "communication.created": ["channel", "direction", "status", "sender", "recipient", "company_id", "contact_id", "deal_id", "subject"],
  "schedule.deal_inactive": ["inactive_days", "amount", "discount_percent", "status", "stage_id", "stage_name", "owner_id", "company_id", "opportunity_score", "score_grade", "forecast_probability"]
};
const operators: AutomationConditionOperator[] = ["eq", "neq", "gt", "gte", "lt", "lte", "in", "contains", "is_empty"];
const actionTypes: Array<{ value: AutomationActionType; label: string; description: string }> = [
  { value: "assign_owner", label: "Назначить владельца", description: "Передать запись ответственному." },
  { value: "create_task", label: "Создать задачу", description: "Поставить задачу со сроком и приоритетом." },
  { value: "send_template", label: "Отправить шаблон", description: "Подготовить сообщение по активному шаблону." },
  { value: "request_approval", label: "Запросить согласование", description: "Остановить сценарий до решения." },
  { value: "update_next_action", label: "Обновить следующий шаг", description: "Создать новый next action." }
];

const activeTab = ref<Tab>("workflows");
const profileError = ref("");
const localError = ref("");
const scheduledSummary = ref("");
const runFilter = ref("");
const approvalFilter = ref("");
const outboxFilter = ref("");
const approvalComments = reactive<Record<string, string>>({});
const approvalAssignees = reactive<Record<string, string>>({});
const approvalCancelComments = reactive<Record<string, string>>({});
const openApprovalHistory = reactive<Record<string, boolean>>({});
const outboxErrors = reactive<Record<string, string>>({});
const editingWorkflowId = ref("");
const editingTemplateId = ref("");

const workflowForm = reactive({
  name: "",
  description: "",
  trigger_type: "lead.created" as AutomationTriggerType,
  condition_logic: "all" as "all" | "any",
  priority: 100,
  is_active: true,
  conditions: [] as ConditionDraft[],
  actions: [newAction("create_task")] as ActionDraft[]
});
const templateForm = reactive({ name: "", channel: "email", subject: "", body: "", is_active: true });

const editingWorkflow = computed(() =>
  automationStore.workflows.value.find((item) => item.id === editingWorkflowId.value)
);

watch(() => workflowForm.trigger_type, (trigger) => {
  for (const condition of workflowForm.conditions) {
    if (!triggerFields[trigger].includes(condition.field)) condition.field = "";
  }
});
const denied = computed(() => !automationStore.canOpen.value && !profileError.value);

onMounted(async () => {
  try {
    await crmStore.refreshMe();
  } catch {
    profileError.value = "Не удалось загрузить /me. Войдите заново или проверьте актуальность API.";
  }
  await automationStore.refreshAll();
  if (!automationStore.canManageAutomations.value && automationStore.canManageApprovals.value) activeTab.value = "approvals";
});

function newAction(type: AutomationActionType): ActionDraft {
  return {
    type,
    config: {
      assignee: type === "request_approval" ? "owner_manager" : "owner",
      user_id: "",
      title: type === "request_approval" ? "Согласовать {{title}}" : type === "create_task" ? "Связаться по {{title}}" : "Позвонить клиенту",
      description: "",
      due_in_days: 1,
      due_in_hours: 24,
      priority: "normal",
      template_id: "",
      recipient: "",
      reason: ""
    }
  };
}

function addCondition() {
  workflowForm.conditions.push({ field: "", operator: "eq", value: "" });
}

function addAction() {
  workflowForm.actions.push(newAction("create_task"));
}

function changeActionType(action: ActionDraft) {
  action.config = newAction(action.type).config;
}

function parseConditionValue(condition: ConditionDraft) {
  if (condition.operator === "is_empty") return undefined;
  const value = condition.value.trim();
  if (!value) return "";
  try {
    return JSON.parse(value) as unknown;
  } catch {
    return value;
  }
}

function workflowPayload() {
  return {
    name: workflowForm.name,
    description: workflowForm.description || null,
    trigger_type: workflowForm.trigger_type,
    condition_logic: workflowForm.condition_logic,
    priority: workflowForm.priority,
    is_active: workflowForm.is_active,
    conditions: workflowForm.conditions.map((item) => ({
      field: item.field,
      operator: item.operator,
      value: parseConditionValue(item)
    })),
    actions: workflowForm.actions.map((item) => {
      const config: Record<string, unknown> = {};
      if (item.type !== "send_template") {
        config.assignee = item.config.assignee;
        if (item.config.user_id.trim()) config.user_id = item.config.user_id.trim();
      }
      if (["create_task", "request_approval", "update_next_action"].includes(item.type)) config.title = item.config.title.trim();
      if (["create_task", "update_next_action"].includes(item.type)) {
        if (item.config.description.trim()) config.description = item.config.description.trim();
        config.due_in_days = Number(item.config.due_in_days);
        config.priority = item.config.priority;
      }
      if (item.type === "request_approval") {
        if (item.config.reason.trim()) config.reason = item.config.reason.trim();
        config.due_in_hours = Number(item.config.due_in_hours);
        config.priority = item.config.priority;
      }
      if (item.type === "send_template") {
        config.template_id = item.config.template_id;
        if (item.config.recipient.trim()) config.recipient = item.config.recipient.trim();
      }
      return { type: item.type, config };
    })
  };
}

async function saveWorkflow() {
  await guarded(async () => {
    const payload = workflowPayload();
    if (editingWorkflow.value) {
      await automationStore.updateWorkflow(editingWorkflow.value.id, editingWorkflow.value.version, payload);
    } else {
      await automationStore.createWorkflow(payload);
    }
    resetWorkflow();
  });
}

function editWorkflow(workflow: AutomationWorkflow) {
  editingWorkflowId.value = workflow.id;
  workflowForm.name = workflow.name;
  workflowForm.description = workflow.description ?? "";
  workflowForm.trigger_type = workflow.trigger_type;
  workflowForm.condition_logic = workflow.condition_logic;
  workflowForm.priority = workflow.priority;
  workflowForm.is_active = workflow.is_active;
  workflowForm.conditions = workflow.conditions.map((item) => ({
    field: item.field,
    operator: item.operator,
    value: item.value === undefined ? "" : typeof item.value === "string" ? item.value : JSON.stringify(item.value)
  }));
  workflowForm.actions = workflow.actions.map((item) => {
    const draft = newAction(item.type);
    draft.config.assignee = (item.config.assignee as ActionConfigDraft["assignee"]) ?? draft.config.assignee;
    draft.config.user_id = String(item.config.user_id ?? "");
    draft.config.title = String(item.config.title ?? "");
    draft.config.description = String(item.config.description ?? "");
    draft.config.due_in_days = Number(item.config.due_in_days ?? 1);
    draft.config.due_in_hours = Number(item.config.due_in_hours ?? 24);
    draft.config.priority = (item.config.priority as ActionConfigDraft["priority"]) ?? "normal";
    draft.config.template_id = String(item.config.template_id ?? "");
    draft.config.recipient = String(item.config.recipient ?? "");
    draft.config.reason = String(item.config.reason ?? "");
    return draft;
  });
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function resetWorkflow() {
  editingWorkflowId.value = "";
  workflowForm.name = "";
  workflowForm.description = "";
  workflowForm.trigger_type = "lead.created";
  workflowForm.condition_logic = "all";
  workflowForm.priority = 100;
  workflowForm.is_active = true;
  workflowForm.conditions = [];
  workflowForm.actions = [newAction("create_task")];
}

async function toggleWorkflow(workflow: AutomationWorkflow) {
  await guarded(() => automationStore.updateWorkflow(workflow.id, workflow.version, { is_active: !workflow.is_active }).then(() => undefined));
}

async function saveTemplate() {
  await guarded(async () => {
    const payload = { name: templateForm.name, channel: templateForm.channel, subject: templateForm.subject, body: templateForm.body };
    if (editingTemplateId.value) await automationStore.updateTemplate(editingTemplateId.value, payload);
    else await automationStore.createTemplate(payload);
    resetTemplate();
  });
}

function editTemplate(item: AutomationMessageTemplate) {
  editingTemplateId.value = item.id;
  templateForm.name = item.name;
  templateForm.channel = item.channel;
  templateForm.subject = item.subject;
  templateForm.body = item.body;
  templateForm.is_active = item.is_active;
}

function resetTemplate() {
  editingTemplateId.value = "";
  templateForm.name = "";
  templateForm.channel = "email";
  templateForm.subject = "";
  templateForm.body = "";
  templateForm.is_active = true;
}

async function toggleTemplate(item: AutomationMessageTemplate) {
  await guarded(() => automationStore.updateTemplate(item.id, { is_active: !item.is_active }).then(() => undefined));
}

async function runScheduled() {
  await guarded(async () => {
    const result = await automationStore.runScheduled();
    scheduledSummary.value = `Проверено: ${result.evaluated}, создано запусков: ${result.matched_runs}`;
    activeTab.value = "runs";
  });
}

async function decide(id: string, version: number, decision: "approved" | "rejected") {
  if (decision === "rejected" && !approvalComments[id]?.trim()) {
    localError.value = "Для отклонения укажите причину.";
    return;
  }
  await guarded(() => automationStore.decideApproval(id, version, decision, approvalComments[id]).then(() => undefined));
}

async function reassignApproval(id: string, version: number) {
  if (!approvalAssignees[id]?.trim()) {
    localError.value = "Укажите ID нового согласующего.";
    return;
  }
  await guarded(() => automationStore.reassignApproval(
    id,
    version,
    approvalAssignees[id].trim(),
    approvalComments[id]
  ).then(() => undefined));
}

async function cancelApproval(id: string, version: number) {
  if (!approvalCancelComments[id]?.trim()) {
    localError.value = "Для отмены укажите причину.";
    return;
  }
  await guarded(() => automationStore.cancelApproval(
    id,
    version,
    approvalCancelComments[id].trim()
  ).then(() => undefined));
}

async function toggleApprovalHistory(id: string) {
  openApprovalHistory[id] = !openApprovalHistory[id];
  if (!openApprovalHistory[id] || automationStore.approvalHistory.value[id]) return;
  await guarded(() => automationStore.refreshApprovalHistory(id).then(() => undefined));
}

async function markOutbox(id: string, status: "sent" | "failed" | "cancelled") {
  if (status === "failed" && !outboxErrors[id]?.trim()) {
    localError.value = "Для статуса failed укажите ошибку.";
    return;
  }
  await guarded(() => automationStore.updateOutbox(id, status, outboxErrors[id]).then(() => undefined));
}

async function guarded(action: () => Promise<void>) {
  localError.value = "";
  try {
    await action();
  } catch (caught) {
    if (!(caught instanceof Error) || !automationStore.error.value) {
      localError.value = caught instanceof Error ? caught.message : "Не удалось выполнить действие.";
    }
  }
}

function workflowName(id: string) {
  return automationStore.workflows.value.find((item) => item.id === id)?.name ?? id;
}

function dateTime(value: string | null) {
  return value ? new Date(value).toLocaleString("ru-RU") : "—";
}

</script>

<template>
  <section class="automation-page stack">
    <section class="automation-hero panel">
      <div><p class="eyebrow">Процессы и контроль</p><h2>Автоматизация</h2><p>Триггеры, условия, действия и журнал исполнения.</p></div>
      <div class="hero-actions">
        <button v-if="automationStore.canManageAutomations.value" type="button" :disabled="automationStore.loading.value" @click="runScheduled">Запустить scheduled-проверку</button>
        <button class="secondary" type="button" :disabled="automationStore.loading.value" @click="automationStore.refreshAll">Обновить</button>
      </div>
    </section>

    <p v-if="profileError" class="alert error">{{ profileError }}</p>
    <p v-else-if="denied" class="automation-denied">Роль <code>{{ crmStore.me.value?.role || "не определена" }}</code> не имеет <code>automations:manage</code> или <code>approvals:manage</code>.</p>
    <template v-else>
      <nav class="automation-tabs" aria-label="Разделы автоматизации">
        <button v-for="tab in tabs" :key="tab.id" type="button" :class="{ active: activeTab === tab.id }" @click="activeTab = tab.id">{{ tab.label }}</button>
      </nav>
      <p v-if="automationStore.error.value || localError" class="alert error">{{ localError || automationStore.error.value }}</p>
      <p v-if="automationStore.success.value" class="alert success">{{ automationStore.success.value }}</p>
      <p v-if="scheduledSummary" class="alert info">{{ scheduledSummary }}</p>

      <section v-if="activeTab === 'workflows'">
        <p v-if="!automationStore.canManageAutomations.value" class="automation-denied">Нет права <code>automations:manage</code>.</p>
        <div v-else class="automation-grid">
          <form class="panel automation-form" @submit.prevent="saveWorkflow">
            <header><div><p class="eyebrow">Workflow builder</p><h2>{{ editingWorkflowId ? "Редактирование сценария" : "Новый сценарий" }}</h2></div><button v-if="editingWorkflowId" class="secondary" type="button" @click="resetWorkflow">Отмена</button></header>
            <label>Название<input v-model="workflowForm.name" required minlength="2" /></label>
            <label>Описание<textarea v-model="workflowForm.description" rows="2"></textarea></label>
            <div class="form-pair"><label>Триггер<select v-model="workflowForm.trigger_type"><option v-for="item in triggers" :key="item.value" :value="item.value">{{ item.label }}</option></select></label><label>Приоритет<input v-model.number="workflowForm.priority" type="number" min="0" max="10000" /></label></div>
            <fieldset><legend>Conditions <button class="secondary mini" type="button" @click="addCondition"><UiIcon name="plus" :size="14" /> Условие</button></legend><label>Логика<select v-model="workflowForm.condition_logic"><option value="all">Все условия</option><option value="any">Любое условие</option></select></label><div v-for="(condition, index) in workflowForm.conditions" :key="index" class="builder-row condition-row"><select v-model="condition.field" required><option value="" disabled>Поле события</option><option v-for="field in triggerFields[workflowForm.trigger_type]" :key="field" :value="field">{{ field }}</option></select><select v-model="condition.operator"><option v-for="operator in operators" :key="operator" :value="operator">{{ operator }}</option></select><input v-model="condition.value" :disabled="condition.operator === 'is_empty'" placeholder="Значение" /><button class="remove-button" type="button" aria-label="Удалить условие" @click="workflowForm.conditions.splice(index, 1)"><UiIcon name="close" :size="15" /></button></div><p v-if="!workflowForm.conditions.length" class="empty">Без условий — сценарий сработает для каждого события.</p></fieldset>
            <fieldset>
              <legend>Действия <button class="secondary mini" type="button" @click="addAction"><UiIcon name="plus" :size="14" /> Действие</button></legend>
              <div v-for="(action, index) in workflowForm.actions" :key="index" class="action-builder">
                <header><div><b>Шаг {{ index + 1 }}</b><small>{{ actionTypes.find((item) => item.value === action.type)?.description }}</small></div><button class="remove-button" type="button" :disabled="workflowForm.actions.length === 1" aria-label="Удалить действие" @click="workflowForm.actions.splice(index, 1)"><UiIcon name="close" :size="15" /></button></header>
                <label>Тип действия<select v-model="action.type" @change="changeActionType(action)"><option v-for="item in actionTypes" :key="item.value" :value="item.value">{{ item.label }}</option></select></label>
                <template v-if="action.type === 'send_template'">
                  <label>Шаблон<select v-model="action.config.template_id" required><option value="" disabled>Выберите шаблон</option><option v-for="template in automationStore.templates.value.filter((item) => item.is_active)" :key="template.id" :value="template.id">{{ template.name }} · {{ template.channel }}</option></select></label>
                  <label>Получатель<input v-model="action.config.recipient" placeholder="Автоматически из контакта" /><small>Можно указать email или переменную sender.</small></label>
                </template>
                <template v-else>
                  <div class="form-pair"><label>Ответственный<select v-model="action.config.assignee"><option value="owner">Владелец записи</option><option value="owner_manager">Руководитель владельца</option><option value="actor">Автор события</option></select></label><label>User ID<input v-model="action.config.user_id" placeholder="Необязательно" /></label></div>
                  <label v-if="action.type !== 'assign_owner'">Название<input v-model="action.config.title" required placeholder="Связаться по {{title}}" /></label>
                  <label v-if="action.type === 'request_approval'">Причина<textarea v-model="action.config.reason" rows="2" placeholder="Что нужно согласовать"></textarea></label>
                  <div v-if="action.type === 'request_approval'" class="action-fields"><label>SLA, часов<input v-model.number="action.config.due_in_hours" type="number" min="1" max="2160" required /></label><label>Приоритет<select v-model="action.config.priority"><option value="low">Низкий</option><option value="normal">Обычный</option><option value="high">Высокий</option><option value="critical">Критический</option></select></label></div>
                  <template v-if="action.type === 'create_task' || action.type === 'update_next_action'">
                    <label>Описание<textarea v-model="action.config.description" rows="2" placeholder="Необязательно"></textarea></label>
                    <div class="action-fields"><label>Срок, дней<input v-model.number="action.config.due_in_days" type="number" min="0" max="365" required /></label><label>Приоритет<select v-model="action.config.priority"><option value="low">Низкий</option><option value="normal">Обычный</option><option value="high">Высокий</option></select></label></div>
                  </template>
                </template>
              </div>
            </fieldset>
            <label class="check-row"><input v-model="workflowForm.is_active" type="checkbox" />Активировать сразу</label>
            <button type="submit" :disabled="automationStore.loading.value">{{ editingWorkflowId ? "Сохранить изменения" : "Создать сценарий" }}</button>
          </form>
          <section class="panel automation-list"><h2>Сценарии</h2><article v-for="workflow in automationStore.workflows.value" :key="workflow.id" class="automation-card"><div><strong>{{ workflow.name }}</strong><small>{{ triggers.find((item) => item.value === workflow.trigger_type)?.label }} · {{ workflow.conditions.length }} условий · {{ workflow.actions.length }} действий</small><small>Приоритет {{ workflow.priority }} · версия {{ workflow.version }}</small></div><span class="status-pill" :class="{ inactive: !workflow.is_active }">{{ workflow.is_active ? "Активен" : "Отключён" }}</span><div class="card-actions"><button type="button" @click="editWorkflow(workflow)">Редактировать</button><button class="secondary" type="button" @click="toggleWorkflow(workflow)">{{ workflow.is_active ? "Отключить" : "Включить" }}</button></div></article><p v-if="!automationStore.workflows.value.length" class="empty">Сценариев нет.</p></section>
        </div>
      </section>

      <section v-else-if="activeTab === 'templates'">
        <p v-if="!automationStore.canManageAutomations.value" class="automation-denied">Нет права <code>automations:manage</code>.</p>
        <div v-else class="automation-grid">
          <form class="panel automation-form" @submit.prevent="saveTemplate"><header><h2>{{ editingTemplateId ? "Редактирование шаблона" : "Новый шаблон" }}</h2><button v-if="editingTemplateId" class="secondary" type="button" @click="resetTemplate">Отмена</button></header><label>Название<input v-model="templateForm.name" required minlength="2" /></label><label>Канал<input v-model="templateForm.channel" required /></label><label>Тема<input v-model="templateForm.subject" required /></label><label>Тело<textarea v-model="templateForm.body" rows="8" required></textarea></label><button type="submit">{{ editingTemplateId ? "Сохранить" : "Создать шаблон" }}</button></form>
          <section class="panel automation-list"><h2>Шаблоны сообщений</h2><article v-for="item in automationStore.templates.value" :key="item.id" class="automation-card"><div><strong>{{ item.name }}</strong><small>{{ item.channel }} · {{ item.subject }}</small><p>{{ item.body }}</p></div><span class="status-pill" :class="{ inactive: !item.is_active }">{{ item.is_active ? "Активен" : "Отключён" }}</span><div class="card-actions"><button type="button" @click="editTemplate(item)">Редактировать</button><button class="secondary" type="button" @click="toggleTemplate(item)">{{ item.is_active ? "Отключить" : "Включить" }}</button></div></article><p v-if="!automationStore.templates.value.length" class="empty">Шаблонов нет.</p></section>
        </div>
      </section>

      <section v-else-if="activeTab === 'runs'" class="panel automation-list">
        <p v-if="!automationStore.canManageAutomations.value" class="automation-denied">Нет права <code>automations:manage</code>.</p>
        <template v-else><header class="list-head"><div><h2>Журнал запусков</h2><p>Idempotency контролируется backend через event key.</p></div><select v-model="runFilter" @change="automationStore.refreshRuns(runFilter)"><option value="">Все статусы</option><option value="succeeded">Успешно</option><option value="failed">Ошибки</option><option value="running">Выполняется</option><option value="waiting_approval">Ожидает согласования</option></select></header><article v-for="run in automationStore.runs.value" :key="run.id" class="automation-card run-card"><div><strong>{{ workflowName(run.workflow_id) }}</strong><small>{{ run.trigger_type }} · {{ run.entity_type }} · {{ run.entity_id }}</small><small>{{ dateTime(run.started_at) }} · event: {{ run.event_key }}</small><p v-if="run.error" class="run-error">{{ run.error }}</p><details v-if="run.result.length"><summary>Результат действий</summary><pre>{{ JSON.stringify(run.result, null, 2) }}</pre></details></div><span class="status-pill" :class="`status-${run.status}`">{{ statusLabel(run.status, "automation") }}</span></article><p v-if="!automationStore.runs.value.length" class="empty">Запусков нет.</p></template>
      </section>

      <section v-else-if="activeTab === 'approvals'" class="panel automation-list">
        <p v-if="!automationStore.canManageApprovals.value" class="automation-denied">Нет права <code>approvals:manage</code>.</p>
        <template v-else>
          <header class="list-head"><div><h2>Согласования</h2><p>Сценарий приостановлен до решения; версия защищает от двойного ответа.</p></div><select v-model="approvalFilter" @change="automationStore.refreshApprovals(approvalFilter)"><option value="">Все статусы</option><option value="pending">Ожидают</option><option value="approved">Согласованы</option><option value="rejected">Отклонены</option><option value="cancelled">Отменены</option><option value="expired">Просрочены</option></select></header>
          <article v-for="item in automationStore.approvals.value" :key="item.id" class="automation-card approval-card">
            <div class="approval-main">
              <strong>{{ item.title }}</strong>
              <small>{{ item.entity_type }} · {{ item.entity_id }} · {{ dateTime(item.created_at) }}</small>
              <small>Приоритет: {{ statusLabel(item.priority, "priority") }} · срок: {{ item.due_at ? dateTime(item.due_at) : "не задан" }} · версия {{ item.version }}</small>
              <small>Согласующий: {{ item.assigned_to_id || "не назначен" }}</small>
              <p v-if="item.reason">{{ item.reason }}</p>
              <p v-if="item.decision_comment">Комментарий: {{ item.decision_comment }}</p>
              <template v-if="item.status === 'pending'">
                <textarea v-model="approvalComments[item.id]" rows="2" placeholder="Комментарий к решению (обязателен при отклонении)"></textarea>
                <div class="approval-reassign">
                  <input v-model="approvalAssignees[item.id]" placeholder="ID нового согласующего" />
                  <button class="secondary" type="button" :disabled="automationStore.loading.value" @click="reassignApproval(item.id, item.version)">Переназначить</button>
                </div>
                <div v-if="automationStore.canManageAutomations.value" class="approval-cancel">
                  <input v-model="approvalCancelComments[item.id]" placeholder="Причина отмены" />
                  <button class="danger-quiet" type="button" :disabled="automationStore.loading.value" @click="cancelApproval(item.id, item.version)">Отменить</button>
                </div>
              </template>
              <button class="secondary history-button" type="button" :disabled="automationStore.loading.value" @click="toggleApprovalHistory(item.id)">{{ openApprovalHistory[item.id] ? "Скрыть историю" : "Показать историю" }}</button>
              <ol v-if="openApprovalHistory[item.id]" class="approval-history">
                <li v-for="entry in automationStore.approvalHistory.value[item.id] ?? []" :key="entry.id"><strong>{{ entry.action }}</strong><span v-if="entry.from_status || entry.to_status">{{ entry.from_status || "—" }} → {{ entry.to_status || "—" }}</span><small>{{ dateTime(entry.created_at) }}<template v-if="entry.actor_id"> · {{ entry.actor_id }}</template></small><p v-if="entry.comment">{{ entry.comment }}</p></li>
                <li v-if="!(automationStore.approvalHistory.value[item.id]?.length)">История пуста.</li>
              </ol>
            </div>
            <span class="status-pill" :class="`status-${item.status}`">{{ statusLabel(item.status, "approval") }}</span>
            <div v-if="item.status === 'pending'" class="card-actions"><button type="button" :disabled="automationStore.loading.value" @click="decide(item.id, item.version, 'approved')">Согласовать</button><button class="danger-quiet" type="button" :disabled="automationStore.loading.value" @click="decide(item.id, item.version, 'rejected')">Отклонить</button></div>
          </article>
          <p v-if="!automationStore.approvals.value.length" class="empty">Согласований нет.</p>
        </template>
      </section>

      <section v-else class="panel automation-list">
        <p v-if="!automationStore.canManageAutomations.value" class="automation-denied">Нет права <code>automations:manage</code>.</p>
        <template v-else><header class="list-head"><div><h2>Transactional Outbox</h2><p>Подготовленные сообщения и ошибки доставки.</p></div><select v-model="outboxFilter" @change="automationStore.refreshOutbox(outboxFilter)"><option value="">Все статусы</option><option value="pending">Ожидают</option><option value="failed">Ошибки</option><option value="sent">Отправлены</option><option value="cancelled">Отменены</option></select></header><article v-for="item in automationStore.outbox.value" :key="item.id" class="automation-card outbox-card"><div><strong>{{ item.subject }}</strong><small>{{ item.channel }} → {{ item.recipient }} · попыток {{ item.attempts }}</small><p>{{ item.body }}</p><p v-if="item.last_error" class="run-error">{{ item.last_error }}</p><input v-if="['pending','sending','failed'].includes(item.status)" v-model="outboxErrors[item.id]" placeholder="Ошибка для статуса failed" /></div><span class="status-pill" :class="`status-${item.status}`">{{ statusLabel(item.status, "outbox") }}</span><div v-if="['pending','sending','failed'].includes(item.status)" class="card-actions"><button type="button" @click="markOutbox(item.id, 'sent')">Sent</button><button class="secondary" type="button" @click="markOutbox(item.id, 'failed')">Failed</button><button class="danger-quiet" type="button" @click="markOutbox(item.id, 'cancelled')">Cancel</button></div></article><p v-if="!automationStore.outbox.value.length" class="empty">Outbox пуст.</p></template>
      </section>
    </template>
  </section>
</template>

<style scoped>
.automation-page{padding-bottom:38px}.automation-hero,.automation-form>header,.list-head{display:flex;align-items:flex-start;justify-content:space-between;gap:16px}.automation-hero h2,.automation-form h2,.automation-list h2{margin:3px 0 6px}.automation-hero p:last-child,.list-head p{margin:0;color:var(--muted)}.hero-actions,.card-actions{display:flex;flex-wrap:wrap;gap:8px}.automation-tabs{display:flex;gap:4px;overflow-x:auto;border:1px solid var(--line);border-radius:var(--radius-card);padding:4px;background:var(--surface)}.automation-tabs button{min-height:36px;color:var(--muted);background:transparent;white-space:nowrap}.automation-tabs button.active{color:var(--text);background:#fff;box-shadow:0 1px 5px rgb(0 0 0/10%)}.automation-denied{border:1px solid #efc2c2;border-radius:var(--radius-card);padding:17px;color:#8f2525;background:#fff6f6}.alert.info{color:#24547b;border-color:#bddcf4;background:#eff8ff}.automation-grid{display:grid;grid-template-columns:minmax(330px,430px) minmax(0,1fr);gap:16px;align-items:start}.automation-form{display:grid;gap:13px}.automation-form label{margin:0}.automation-form fieldset{display:grid;gap:9px;border:1px solid var(--line);border-radius:9px;padding:12px}.automation-form legend{padding:0 5px;font-weight:700}.mini{min-height:28px;padding:4px 8px}.form-pair{display:grid;grid-template-columns:1fr 120px;gap:9px}.builder-row{display:grid;grid-template-columns:minmax(0,1fr) minmax(110px,.6fr) auto;gap:7px}.condition-row{grid-template-columns:minmax(110px,1fr) 100px minmax(100px,1fr) auto}.action-builder{display:grid;gap:6px;border-top:1px solid var(--line-soft);padding-top:9px}.remove-button{width:34px;padding:0;color:#9b2929;background:#fff4f4}.check-row{display:flex;align-items:center;gap:8px}.automation-list{display:grid;gap:10px}.automation-card{display:grid;grid-template-columns:minmax(180px,1fr) auto auto;gap:12px;align-items:start;border:1px solid var(--line);border-radius:var(--radius-card);padding:14px}.automation-card>div:first-child{display:grid;gap:5px}.automation-card small{color:var(--muted)}.automation-card p{margin:2px 0;white-space:pre-wrap}.status-pill{display:inline-flex;border-radius:var(--radius-pill);padding:5px 8px;color:#17663a;background:#e9f8ef;font-size:11px;font-weight:700;white-space:nowrap}.status-pill.inactive,.status-cancelled,.status-rejected{color:#76515b;background:#f3edef}.status-failed{color:#992a2a;background:#fff0f0}.status-pending,.status-running,.status-sending{color:#76500c;background:#fff5d9}.run-error{color:#992a2a!important}.automation-card details{margin-top:5px}.automation-card pre{max-width:100%;overflow:auto;border-radius:var(--radius-control);padding:9px;background:#f6f8fa;font-size:11px}.danger-quiet{color:#a02929;border-color:#efc2c2;background:#fff6f6}@media(max-width:980px){.automation-grid{grid-template-columns:1fr}.automation-card{grid-template-columns:minmax(0,1fr) auto}.automation-card .card-actions{grid-column:1/-1}}@media(max-width:650px){.automation-hero,.list-head{flex-direction:column}.hero-actions{width:100%}.hero-actions button{flex:1}.form-pair,.builder-row,.condition-row,.automation-card{grid-template-columns:1fr}.automation-card>*{grid-column:1!important}}
.action-builder{display:grid;gap:10px;border:1px solid var(--color-border);border-radius:var(--radius-control);padding:12px;background:var(--color-surface-subtle)}.action-builder>header{display:flex;align-items:flex-start;justify-content:space-between;gap:10px}.action-builder>header div{display:grid;gap:2px}.action-builder>header small,.action-builder label small{color:var(--color-text-muted);font-size:var(--font-size-meta);font-weight:400}.action-fields{display:grid;grid-template-columns:1fr 1fr;gap:9px}
.approval-main{min-width:0}.approval-reassign,.approval-cancel{display:grid;grid-template-columns:minmax(180px,1fr) auto;gap:8px}.history-button{justify-self:start}.approval-history{display:grid;gap:7px;margin:4px 0 0;padding:0;list-style:none}.approval-history li{display:grid;gap:2px;border-left:2px solid var(--color-border);padding:6px 10px}.approval-history p{color:var(--color-text-muted)}.status-waiting_approval{color:var(--color-warning-text);background:var(--color-warning-soft)}@media(max-width:650px){.approval-reassign,.approval-cancel{grid-template-columns:1fr}}
</style>
