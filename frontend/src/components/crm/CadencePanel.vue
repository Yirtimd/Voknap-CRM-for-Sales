<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";

import type { CadenceStepType, Contact, Deal } from "../../types";
import { sequenceStore } from "../../stores/sequences";

const props = defineProps<{ companyId: string; contacts: Contact[]; deals: Deal[] }>();
const busy = ref(false);
const showBuilder = ref(false);
const openHistory = ref<Record<string, boolean>>({});
const localError = ref("");
const enrollForm = reactive({ cadence_id: "", contact_id: "", deal_id: "", connector_account_id: "" });
const builder = reactive({
  name: "",
  description: "",
  steps: [newStep("manual_email")] as Array<{
    step_type: CadenceStepType;
    delay_minutes: number;
    title: string;
    body: string;
    task_priority: "low" | "normal" | "high" | "urgent";
  }>
});

const selectedCadence = computed(() =>
  sequenceStore.cadences.value.find((item) => item.id === enrollForm.cadence_id)
);
const needsEmailAccount = computed(() =>
  selectedCadence.value?.steps.some((step) => step.step_type === "automatic_email") ?? false
);
const activeEnrollments = computed(() =>
  sequenceStore.enrollments.value.filter((item) => ["active", "paused"].includes(item.status))
);
const completedEnrollments = computed(() =>
  sequenceStore.enrollments.value.filter((item) => !["active", "paused"].includes(item.status))
);

watch(() => props.companyId, (companyId) => void sequenceStore.refresh(companyId));
watch(needsEmailAccount, (required) => { if (!required) enrollForm.connector_account_id = ""; });
onMounted(() => void sequenceStore.refresh(props.companyId));

function newStep(type: CadenceStepType = "task") {
  return {
    step_type: type,
    delay_minutes: 0,
    title: type === "call" ? "Обсудить предложение" : type.includes("email") ? "Follow-up: {{company.name}}" : "Следующий шаг",
    body: type.includes("email") ? "Здравствуйте, {{contact.name}}!" : "",
    task_priority: "normal" as const
  };
}

function typeLabel(type: CadenceStepType) {
  return {
    task: "Задача",
    call: "Звонок",
    manual_email: "Письмо вручную",
    automatic_email: "Автописьмо"
  }[type];
}

function statusLabel(status: string) {
  return {
    active: "Активна",
    paused: "Пауза",
    completed: "Завершена",
    stopped: "Остановлена",
    replied: "Получен ответ",
    failed: "Ошибка",
    queued: "В очереди",
    succeeded: "Выполнен"
  }[status] ?? status;
}

function dateTime(value: string | null) {
  return value ? new Date(value).toLocaleString("ru-RU") : "—";
}

async function guarded(action: () => Promise<void>) {
  busy.value = true;
  localError.value = "";
  try { await action(); }
  catch (caught) { localError.value = caught instanceof Error ? caught.message : "Не удалось выполнить действие"; }
  finally { busy.value = false; }
}

function submitEnrollment() {
  if (!enrollForm.cadence_id || !enrollForm.contact_id) return;
  void guarded(async () => {
    await sequenceStore.enroll({
      cadence_id: enrollForm.cadence_id,
      contact_id: enrollForm.contact_id,
      deal_id: enrollForm.deal_id || null,
      connector_account_id: enrollForm.connector_account_id || null
    }, props.companyId);
    Object.assign(enrollForm, { cadence_id: "", contact_id: "", deal_id: "", connector_account_id: "" });
  });
}

function submitCadence() {
  if (!builder.name.trim() || !builder.steps.length) return;
  void guarded(async () => {
    await sequenceStore.createCadence({
      name: builder.name.trim(),
      description: builder.description.trim(),
      steps: builder.steps.map((step) => ({ ...step, title: step.title.trim(), body: step.body.trim() }))
    });
    await sequenceStore.refresh(props.companyId);
    builder.name = "";
    builder.description = "";
    builder.steps = [newStep("manual_email")];
    showBuilder.value = false;
  });
}

async function toggleHistory(id: string) {
  openHistory.value[id] = !openHistory.value[id];
  if (openHistory.value[id] && !sequenceStore.executions.value[id]) {
    await guarded(() => sequenceStore.refreshExecutions(id));
  }
}
</script>

<template>
  <section class="cadence-panel">
    <header class="cadence-head">
      <div><h2>Sequences и cadences</h2><p>Последовательные касания по контактам с задачами и коммуникациями в timeline.</p></div>
      <div class="cadence-head-actions">
        <button v-if="sequenceStore.canManage.value" type="button" class="secondary" @click="guarded(() => sequenceStore.runDue(companyId))">Запустить due-шаги</button>
        <button v-if="sequenceStore.canManage.value" type="button" @click="showBuilder = !showBuilder">{{ showBuilder ? "Закрыть" : "Новая cadence" }}</button>
      </div>
    </header>

    <p v-if="localError || sequenceStore.error.value" class="cadence-error" role="alert">{{ localError || sequenceStore.error.value }}</p>

    <form v-if="showBuilder && sequenceStore.canManage.value" class="cadence-builder" @submit.prevent="submitCadence">
      <div class="cadence-form-grid"><label>Название<input v-model="builder.name" required /></label><label>Описание<input v-model="builder.description" /></label></div>
      <ol class="cadence-step-builder">
        <li v-for="(step, index) in builder.steps" :key="index">
          <b>{{ index + 1 }}</b>
          <select v-model="step.step_type"><option value="task">Задача</option><option value="call">Звонок</option><option value="manual_email">Письмо вручную</option><option value="automatic_email">Автописьмо</option></select>
          <label>Задержка, мин<input v-model.number="step.delay_minutes" type="number" min="0" /></label>
          <input v-model="step.title" placeholder="Название или тема" required />
          <textarea v-model="step.body" rows="2" placeholder="Описание или текст письма"></textarea>
          <button type="button" class="secondary" :disabled="builder.steps.length === 1" @click="builder.steps.splice(index, 1)">Удалить</button>
        </li>
      </ol>
      <div class="cadence-builder-actions"><button type="button" class="secondary" @click="builder.steps.push(newStep())">Добавить шаг</button><button type="submit" :disabled="busy">Создать cadence</button></div>
      <small>Автописьмо отправляется только через подключённый SMTP email-коннектор. Звонок и ручное письмо создают задачи менеджеру.</small>
    </form>

    <form class="cadence-enroll" @submit.prevent="submitEnrollment">
      <select v-model="enrollForm.contact_id" required><option value="">Контакт</option><option v-for="contact in contacts" :key="contact.id" :value="contact.id">{{ contact.name }}</option></select>
      <select v-model="enrollForm.cadence_id" required><option value="">Cadence</option><option v-for="cadence in sequenceStore.cadences.value" :key="cadence.id" :value="cadence.id">{{ cadence.name }} · {{ cadence.steps.length }} шагов</option></select>
      <select v-model="enrollForm.deal_id"><option value="">Без сделки</option><option v-for="deal in deals" :key="deal.id" :value="deal.id">{{ deal.title }}</option></select>
      <select v-if="needsEmailAccount" v-model="enrollForm.connector_account_id" required><option value="">Email-аккаунт</option><option v-for="account in sequenceStore.emailAccounts.value" :key="account.id" :value="account.id">{{ account.title }}</option></select>
      <button type="submit" :disabled="busy || !contacts.length || !sequenceStore.cadences.value.length">Добавить в sequence</button>
    </form>
    <p v-if="needsEmailAccount && !sequenceStore.emailAccounts.value.length" class="cadence-note">Для этой cadence нужен подключённый email-аккаунт в Настройки → Интеграции.</p>

    <section class="cadence-list">
      <h3>Активные <span>{{ activeEnrollments.length }}</span></h3>
      <article v-for="item in activeEnrollments" :key="item.id" class="cadence-card">
        <div class="cadence-card-main"><header><strong>{{ item.contact_name }}</strong><span :class="`status-${item.status}`">{{ statusLabel(item.status) }}</span></header><p>{{ item.cadence_name }} · шаг {{ Math.min(item.current_step + 1, item.step_count) }} из {{ item.step_count }}</p><div class="cadence-progress"><i :style="{ width: `${item.step_count ? item.current_step / item.step_count * 100 : 0}%` }"></i></div><small>Следующий запуск: {{ dateTime(item.next_run_at) }}</small><p v-if="item.stop_reason" class="cadence-reason">{{ item.stop_reason }}</p></div>
        <div class="cadence-card-actions"><button type="button" class="secondary" @click="toggleHistory(item.id)">История</button><button v-if="item.status === 'active'" type="button" class="secondary" @click="guarded(() => sequenceStore.act(item, 'pause', companyId, 'Пауза пользователя'))">Пауза</button><button v-else type="button" class="secondary" @click="guarded(() => sequenceStore.act(item, 'resume', companyId))">Продолжить</button><button type="button" class="danger" @click="guarded(() => sequenceStore.act(item, 'stop', companyId, 'Остановлено пользователем'))">Стоп</button></div>
        <ol v-if="openHistory[item.id]" class="cadence-history"><li v-for="execution in sequenceStore.executions.value[item.id] ?? []" :key="execution.id"><b>{{ execution.step_position + 1 }}. {{ typeLabel(execution.step_type) }}</b><span>{{ execution.title }}</span><small>{{ statusLabel(execution.status) }} · {{ dateTime(execution.executed_at || execution.scheduled_at) }}</small><em v-if="execution.error">{{ execution.error }}</em></li><li v-if="!(sequenceStore.executions.value[item.id]?.length)">Шаги ещё не выполнялись.</li></ol>
      </article>
      <p v-if="!activeEnrollments.length" class="cadence-empty">Активных sequences нет.</p>
    </section>

    <details v-if="completedEnrollments.length" class="cadence-completed"><summary>Завершённые · {{ completedEnrollments.length }}</summary><article v-for="item in completedEnrollments" :key="item.id"><strong>{{ item.contact_name }}</strong><span>{{ item.cadence_name }}</span><small>{{ statusLabel(item.status) }}<template v-if="item.stop_reason"> · {{ item.stop_reason }}</template></small></article></details>
  </section>
</template>

<style scoped>
.cadence-panel{display:grid;gap:16px}.cadence-head{display:flex;align-items:flex-start;justify-content:space-between;gap:16px}.cadence-head h2,.cadence-list h3{margin:0}.cadence-head p{margin:5px 0 0;color:var(--color-text-muted)}.cadence-head-actions,.cadence-builder-actions,.cadence-card-actions{display:flex;gap:8px;flex-wrap:wrap}.cadence-error,.cadence-note{margin:0;border-radius:var(--radius-control);padding:10px 12px;color:var(--color-danger-text);background:var(--color-danger-soft)}.cadence-note{color:var(--color-warning-text);background:var(--color-warning-soft)}.cadence-builder{display:grid;gap:12px;border:1px solid var(--color-border);border-radius:var(--radius-card);padding:16px;background:var(--color-surface-subtle)}.cadence-form-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}.cadence-form-grid label,.cadence-step-builder label{display:grid;gap:5px;color:var(--color-text-muted);font-size:var(--font-size-meta)}.cadence-step-builder{display:grid;gap:10px;margin:0;padding:0;list-style:none}.cadence-step-builder li{display:grid;grid-template-columns:30px 150px 130px minmax(180px,1fr) minmax(200px,1.4fr) auto;align-items:center;gap:8px}.cadence-step-builder b{display:grid;place-items:center;width:28px;height:28px;border-radius:50%;color:var(--color-primary);background:var(--color-primary-soft)}.cadence-enroll{display:grid;grid-template-columns:1fr 1.2fr 1fr 1fr auto;gap:8px}.cadence-list{display:grid;gap:10px}.cadence-list h3 span{color:var(--color-text-muted)}.cadence-card{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:12px;border:1px solid var(--color-border);border-radius:var(--radius-card);padding:14px}.cadence-card-main{display:grid;gap:5px}.cadence-card-main header{display:flex;align-items:center;gap:8px}.cadence-card-main p,.cadence-card-main small{margin:0;color:var(--color-text-muted)}.cadence-card-main header span{border-radius:999px;padding:3px 7px;font-size:var(--font-size-meta);background:var(--color-surface-muted)}.cadence-card-main .status-active{color:var(--color-success-text);background:var(--color-success-soft)}.cadence-card-main .status-paused{color:var(--color-warning-text);background:var(--color-warning-soft)}.cadence-progress{overflow:hidden;height:5px;border-radius:999px;background:var(--color-surface-muted)}.cadence-progress i{display:block;height:100%;background:var(--color-primary)}.cadence-reason{color:var(--color-warning-text)!important}.cadence-history{grid-column:1/-1;display:grid;gap:6px;margin:0;padding:10px 0 0;border-top:1px solid var(--color-border-subtle);list-style:none}.cadence-history li,.cadence-completed article{display:grid;grid-template-columns:minmax(160px,.8fr) minmax(200px,1fr) auto;gap:8px}.cadence-history small,.cadence-history em,.cadence-completed small{color:var(--color-text-muted)}.cadence-history em{grid-column:1/-1;color:var(--color-danger-text)}.cadence-empty{margin:0;color:var(--color-text-muted)}.cadence-completed{border-top:1px solid var(--color-border);padding-top:12px}.cadence-completed summary{cursor:pointer;font-weight:700}.cadence-completed article{padding:8px 0;border-bottom:1px solid var(--color-border-subtle)}@media(max-width:900px){.cadence-step-builder li{grid-template-columns:30px 1fr 1fr}.cadence-step-builder li input,.cadence-step-builder li textarea{grid-column:2/-1}.cadence-enroll{grid-template-columns:1fr 1fr}.cadence-card{grid-template-columns:1fr}.cadence-form-grid{grid-template-columns:1fr}}@media(max-width:600px){.cadence-head{display:grid}.cadence-enroll{grid-template-columns:1fr}.cadence-history li,.cadence-completed article{grid-template-columns:1fr}}
</style>
