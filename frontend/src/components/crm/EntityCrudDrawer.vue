<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";

import UiIcon from "../ui/UiIcon.vue";
import CustomFieldsForm from "./CustomFieldsForm.vue";
import { ENTITY_CONFIG, type LifecycleField } from "../../lifecycleConfig";
import { crmStore } from "../../stores/crm";
import { lifecycleStore, type LifecycleRecord } from "../../stores/lifecycle";
import type { Deal, DuplicateCandidate, EntityType, FieldChange, Lead, ScoreFactor } from "../../types";

const props = withDefaults(defineProps<{
  entityType: EntityType;
  record?: LifecycleRecord | null;
  initialValues?: Record<string, unknown>;
  initialMode?: "view" | "edit" | "create";
}>(), { record: null, initialMode: "view", initialValues: () => ({}) });
const emit = defineEmits<{
  close: [];
  saved: [record: LifecycleRecord];
  removed: [id: string];
}>();

const mode = ref<"view" | "edit" | "create">(props.record ? props.initialMode : "create");
const current = ref<LifecycleRecord | null>(props.record ?? null);
const draft = reactive<Record<string, string | number | null>>({});
const historyRows = ref<FieldChange[]>([]);
const historyOpen = ref(false);
const busy = ref(false);
const error = ref("");
const ok = ref("");
const ownerId = ref("");
const disqualificationReason = ref("");
const conversion = reactive({ stage_id: "", title: "", amount: "" });
const duplicateRecords = ref<Record<string, LifecycleRecord>>({});

const config = computed(() => ENTITY_CONFIG[props.entityType]);
const fields = computed(() => config.value.fields.filter((field) => mode.value === "create" ? field.create : field.edit));
const canWriteRecord = computed(() => {
  if (!current.value || !lifecycleStore.canWrite.value) return false;
  if (crmStore.me.value?.role !== "sales_rep") return true;
  return recordOwner(current.value) === crmStore.me.value.user_id;
});
const duplicateCandidates = computed(() => {
  if (!current.value || !["contacts", "leads", "deals"].includes(props.entityType)) return [];
  return lifecycleStore.duplicateCandidates.value.filter((candidate) =>
    candidate.entity_type === props.entityType &&
    (candidate.record_a_id === current.value?.id || candidate.record_b_id === current.value?.id)
  );
});

onMounted(async () => {
  if (!crmStore.me.value) await crmStore.refreshMe().catch(() => undefined);
  await lifecycleStore.loadMembers();
  resetDraft(current.value ?? undefined);
  ownerId.value = current.value ? recordOwner(current.value) ?? "" : "";
  if (current.value && ["contacts", "leads", "deals"].includes(props.entityType)) {
    try {
      await loadDuplicateCandidates();
    } catch (caught) {
      error.value = caught instanceof Error ? caught.message : "Не удалось загрузить кандидатов в дубли";
    }
  }
});

function crmList(type: EntityType): LifecycleRecord[] {
  if (type === "contacts") return crmStore.contacts.value;
  if (type === "leads") return crmStore.leads.value;
  if (type === "deals") return crmStore.deals.value;
  if (type === "tasks") return crmStore.tasks.value;
  return crmStore.notes.value;
}

function resetDraft(record?: LifecycleRecord) {
  for (const key of Object.keys(draft)) delete draft[key];
  for (const field of config.value.fields) {
    const source = record ? (record as unknown as Record<string, unknown>)[field.key] : props.initialValues[field.key] ?? defaultValue(field);
    draft[field.key] = inputValue(field, source);
  }
}

function defaultValue(field: LifecycleField) {
  if (field.key === "company_id") return crmStore.companies.value[0]?.id ?? "";
  if (field.key === "stage_id") return crmStore.allStages.value[0]?.id ?? "";
  if (field.key === "priority") return "normal";
  if (field.key === "status") return "open";
  return "";
}

function inputValue(field: LifecycleField, value: unknown): string | number {
  if (value === null || value === undefined) return "";
  if (field.kind === "datetime-local") {
    const date = new Date(String(value));
    if (!Number.isNaN(date.getTime())) return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
  }
  return typeof value === "number" ? value : String(value);
}

function referenceOptions(field: LifecycleField) {
  const companyId = String(draft.company_id ?? "");
  if (field.reference === "companies") return crmStore.companies.value.map((item) => ({ value: item.id, label: item.name }));
  if (field.reference === "stages") return crmStore.allStages.value.map((item) => ({ value: item.id, label: item.name }));
  if (field.reference === "contacts") return crmStore.contacts.value.filter((item) => !companyId || item.company_id === companyId).map((item) => ({ value: item.id, label: item.name }));
  if (field.reference === "leads") return crmStore.leads.value.filter((item) => !companyId || item.company_id === companyId).map((item) => ({ value: item.id, label: item.title }));
  if (field.reference === "deals") return crmStore.deals.value.filter((item) => !companyId || item.company_id === companyId).map((item) => ({ value: item.id, label: item.title }));
  return [];
}

function payload() {
  const result: Record<string, unknown> = {};
  for (const field of fields.value) {
    const value = draft[field.key];
    if (field.kind === "number") result[field.key] = value === "" || value === null ? null : Number(value);
    else if (field.kind === "datetime-local") result[field.key] = value ? new Date(String(value)).toISOString() : null;
    else result[field.key] = value === "" ? null : value;
  }
  return result;
}

async function save() {
  if (props.entityType === "notes" && mode.value === "create" && !draft.lead_id && !draft.deal_id) {
    error.value = "Выберите лид или сделку для заметки.";
    return;
  }
  await run(async () => {
    const saved = mode.value === "create"
      ? await lifecycleStore.create(props.entityType, payload())
      : await lifecycleStore.update(props.entityType, current.value!, payload());
    current.value = saved;
    mode.value = "view";
    emit("saved", saved);
    return "Сохранено";
  });
}

async function showHistory() {
  if (!current.value) return;
  await run(async () => {
    historyRows.value = await lifecycleStore.history(props.entityType, current.value!.id);
    historyOpen.value = true;
    return "";
  });
}

async function archiveRecord(isArchived: boolean) {
  if (!current.value) return;
  await run(async () => {
    await lifecycleStore.archive(props.entityType, current.value!, isArchived);
    emit("removed", current.value!.id);
    emit("close");
    return isArchived ? "Архивировано" : "Возвращено";
  });
}

async function deleteRecord() {
  if (!current.value || !window.confirm(`Переместить «${title(current.value)}» в корзину? Запись можно восстановить.`)) return;
  await run(async () => {
    await lifecycleStore.remove(props.entityType, current.value!);
    emit("removed", current.value!.id);
    emit("close");
    return "Перемещено в корзину";
  });
}

async function restoreRecord() {
  if (!current.value) return;
  await run(async () => {
    await lifecycleStore.restore(props.entityType, current.value!);
    emit("saved", current.value!);
    emit("close");
    return "Восстановлено";
  });
}

async function reassign() {
  if (!current.value || !ownerId.value || props.entityType === "notes") return;
  await run(async () => {
    await lifecycleStore.reassign(props.entityType as Exclude<EntityType, "notes">, current.value!, ownerId.value);
    return "Ответственный изменён";
  });
}

async function qualify(qualified: boolean) {
  if (!current.value) return;
  if (!qualified && !disqualificationReason.value.trim()) {
    error.value = "Укажите причину дисквалификации.";
    return;
  }
  await run(async () => {
    const saved = await lifecycleStore.qualify(current.value!, qualified, disqualificationReason.value.trim() || null);
    current.value = saved;
    emit("saved", saved);
    return qualified ? "Лид квалифицирован" : "Лид дисквалифицирован";
  });
}

async function convert() {
  if (!current.value || !conversion.stage_id) {
    error.value = "Выберите этап сделки.";
    return;
  }
  await run(async () => {
    const result = await lifecycleStore.convert(current.value!, {
      stage_id: conversion.stage_id,
      title: conversion.title || null,
      amount: conversion.amount === "" ? null : Number(conversion.amount)
    });
    current.value = result.lead;
    emit("saved", result.lead);
    return "Сделка создана";
  });
}

function duplicateRecordId(candidate: DuplicateCandidate) {
  return candidate.record_a_id === current.value?.id ? candidate.record_b_id : candidate.record_a_id;
}

function duplicateTitle(candidate: DuplicateCandidate) {
  const record = duplicateRecords.value[duplicateRecordId(candidate)];
  return record ? title(record) : duplicateRecordId(candidate);
}

async function loadDuplicateCandidates() {
  if (!current.value || !["contacts", "leads", "deals"].includes(props.entityType)) return;
  const type = props.entityType as "contacts" | "leads" | "deals";
  await lifecycleStore.loadDuplicateCandidates(type);
  const ids = lifecycleStore.duplicateCandidates.value
    .filter((candidate) => candidate.entity_type === type && (candidate.record_a_id === current.value?.id || candidate.record_b_id === current.value?.id))
    .map(duplicateRecordId);
  const loaded = await Promise.allSettled(ids.map((id) => lifecycleStore.loadDuplicateRecord(type, id)));
  loaded.forEach((result, index) => {
    if (result.status === "fulfilled") duplicateRecords.value[ids[index]] = result.value;
  });
}

async function scanDuplicates() {
  if (!["contacts", "leads", "deals"].includes(props.entityType)) return;
  await run(async () => {
    await lifecycleStore.scanDuplicates(props.entityType as "contacts" | "leads" | "deals");
    await loadDuplicateCandidates();
    return duplicateCandidates.value.length ? `Найдено кандидатов: ${duplicateCandidates.value.length}` : "Дубли не найдены";
  });
}

async function mergeCandidate(candidate: DuplicateCandidate) {
  if (!current.value || !["contacts", "leads", "deals"].includes(props.entityType)) return;
  const source = duplicateRecords.value[duplicateRecordId(candidate)];
  if (!source) {
    error.value = "Не удалось загрузить карточку кандидата. Обновите данные.";
    return;
  }
  if (!window.confirm(`Объединить «${duplicateTitle(candidate)}» с текущей записью? Текущая запись сохранится.`)) return;
  await run(async () => {
    const result = await lifecycleStore.merge(props.entityType as "contacts" | "leads" | "deals", current.value!, [source]);
    current.value = { ...current.value!, version: result.version } as LifecycleRecord;
    await loadDuplicateCandidates();
    emit("saved", current.value);
    return "Записи объединены";
  });
}

async function dismissCandidate(candidate: DuplicateCandidate) {
  await run(async () => {
    await lifecycleStore.dismissDuplicate(candidate, "Пользователь отметил пару как не дубль");
    await loadDuplicateCandidates();
    return "Кандидат исключён";
  });
}

async function run(action: () => Promise<string>) {
  busy.value = true;
  error.value = "";
  ok.value = "";
  try {
    ok.value = await action();
  } catch {
    error.value = lifecycleStore.error.value || "Не удалось выполнить действие";
  } finally {
    busy.value = false;
  }
}

function title(record: LifecycleRecord) {
  return String((record as unknown as Record<string, unknown>)[config.value.titleKey] ?? "Запись");
}

function displayValue(key: string, value: unknown) {
  if (value === null || value === undefined || value === "") return "—";
  if (key === "amount") return crmStore.money(Number(value));
  if (key.endsWith("_at")) return new Date(String(value)).toLocaleString("ru-RU");
  return typeof value === "object" ? JSON.stringify(value) : String(value);
}

function recordOwner(record: LifecycleRecord) {
  if ("assigned_to_id" in record) return record.assigned_to_id;
  if ("owner_id" in record) return record.owner_id ?? null;
  if ("author_id" in record) return record.author_id ?? null;
  return null;
}

function scoringRecord() {
  return current.value as Lead | Deal | null;
}

function currentScore() {
  const record = scoringRecord();
  if (!record) return null;
  return props.entityType === "leads"
    ? (record as Lead).score ?? null
    : (record as Deal).opportunity_score ?? null;
}

function scoreFactors(): ScoreFactor[] {
  return scoringRecord()?.score_factors ?? [];
}

function forecastProbability() {
  return props.entityType === "deals"
    ? (scoringRecord() as Deal | null)?.forecast_probability ?? null
    : null;
}

function scoreGradeLabel() {
  const grade = scoringRecord()?.score_grade;
  if (grade === "hot") return "Высокий потенциал";
  if (grade === "warm") return "Средний потенциал";
  return "Требует развития";
}

async function recalculateCurrentScore() {
  if (!current.value || !["leads", "deals"].includes(props.entityType)) return;
  busy.value = true;
  error.value = "";
  await crmStore.recalculateScore(
    props.entityType === "leads" ? "lead" : "deal",
    current.value.id
  );
  const updated = crmList(props.entityType).find((item) => item.id === current.value?.id);
  if (updated) {
    current.value = updated;
    emit("saved", updated);
  }
  error.value = crmStore.error.value;
  ok.value = crmStore.error.value ? "" : "Оценка пересчитана";
  busy.value = false;
}
</script>

<template>
  <div class="entity-crud-backdrop" @click.self="$emit('close')">
    <aside class="entity-crud-drawer" role="dialog" aria-modal="true" :aria-label="mode === 'create' ? `Создать: ${config.singular}` : current ? title(current) : config.label">
      <header class="entity-crud-head">
        <div><p class="eyebrow">{{ config.label }} · CRUD</p><h2>{{ mode === "create" ? `Новый ${config.singular}` : current ? title(current) : config.label }}</h2></div>
        <button class="secondary crud-close" type="button" aria-label="Закрыть" @click="$emit('close')"><UiIcon name="close" :size="20" /></button>
      </header>

      <form v-if="(mode === 'create' || mode === 'edit') && lifecycleStore.canWrite.value" class="entity-crud-form" @submit.prevent="save">
        <label v-for="field in fields" :key="field.key">{{ field.label }}
          <textarea v-if="field.kind === 'textarea'" v-model="draft[field.key]" :required="field.required" rows="4"></textarea>
          <select v-else-if="field.kind === 'select' || field.kind === 'reference'" v-model="draft[field.key]" :required="field.required"><option value="">{{ field.required ? "Выберите" : "Не выбрано" }}</option><option v-for="option in field.kind === 'reference' ? referenceOptions(field) : field.options" :key="option.value" :value="option.value">{{ option.label }}</option></select>
          <input v-else v-model="draft[field.key]" :type="field.kind || 'text'" :required="field.required" :min="field.min" :max="field.max" />
        </label>
        <div class="crud-buttons"><button type="submit" :disabled="busy">{{ mode === "create" ? "Создать" : "Сохранить" }}</button><button v-if="current" class="secondary" type="button" @click="mode = 'view'">Отмена</button></div>
      </form>
      <p v-else-if="mode === 'create'" class="alert error">Недостаточно прав для создания записи.</p>

      <template v-else-if="current">
        <div class="crud-status"><span>{{ current.deleted_at ? "Корзина" : current.is_archived ? "Архив" : "Активна" }}</span><span>Версия {{ current.version }}</span></div>
        <div class="crud-buttons">
          <button v-if="canWriteRecord && !current.deleted_at" type="button" @click="resetDraft(current); mode = 'edit'">Редактировать</button>
          <button class="secondary" type="button" @click="showHistory">История</button>
          <button v-if="canWriteRecord && !current.is_archived && !current.deleted_at" class="secondary" type="button" @click="archiveRecord(true)">В архив</button>
          <button v-if="canWriteRecord && current.is_archived && !current.deleted_at" class="secondary" type="button" @click="archiveRecord(false)">Вернуть</button>
          <button v-if="canWriteRecord && !current.deleted_at" class="crud-danger" type="button" @click="deleteRecord">В корзину</button>
          <button v-if="canWriteRecord && current.deleted_at" type="button" @click="restoreRecord">Восстановить</button>
        </div>
        <dl class="crud-fields"><template v-for="field in config.fields" :key="field.key"><dt>{{ field.label }}</dt><dd>{{ displayValue(field.key, (current as unknown as Record<string, unknown>)[field.key]) }}</dd></template></dl>
        <CustomFieldsForm v-if="props.entityType !== 'notes'" :entity-type="props.entityType" :entity-id="current.id" :editable="canWriteRecord && !current.deleted_at" />

        <section v-if="['leads', 'deals'].includes(props.entityType)" class="crud-tool scoring-card">
          <div class="scoring-heading">
            <div><h3>{{ props.entityType === 'leads' ? 'Lead score' : 'Opportunity score' }}</h3><p>Объяснимая оценка · {{ scoringRecord()?.score_model_version ?? 'ещё не рассчитана' }}</p></div>
            <strong>{{ currentScore() ?? '—' }}<small v-if="currentScore() !== null">/100</small></strong>
          </div>
          <p v-if="currentScore() !== null" class="score-grade">{{ scoreGradeLabel() }}</p>
          <div v-if="scoreFactors().length" class="score-factor-list">
            <div v-for="factor in scoreFactors()" :key="factor.key">
              <span><strong>{{ factor.label }}</strong><small>{{ factor.signal }}</small></span>
              <b>+{{ factor.points }}/{{ factor.max_points }}</b>
            </div>
          </div>
          <p v-else>Факторы появятся после первого расчёта.</p>
          <p v-if="forecastProbability() !== null">Вероятность для прогноза: <strong>{{ forecastProbability() }}%</strong></p>
          <button v-if="canWriteRecord" class="secondary" type="button" :disabled="busy" @click="recalculateCurrentScore">Пересчитать</button>
        </section>

        <section v-if="canWriteRecord && lifecycleStore.canReassign.value && config.reassign" class="crud-tool"><h3>Ответственный</h3><select v-model="ownerId"><option value="">Выберите участника</option><option v-for="member in lifecycleStore.knownOwners.value" :key="member.user_id" :value="member.user_id">{{ member.full_name }}</option></select><input v-model="ownerId" placeholder="или UUID участника" /><button type="button" @click="reassign">Назначить</button></section>

        <section v-if="props.entityType === 'leads' && canWriteRecord && !current.deleted_at" class="crud-tool"><h3>Lifecycle лида</h3><p>Статус: <strong>{{ (current as Lead).status }}</strong></p><template v-if="(current as Lead).status !== 'converted'"><button type="button" @click="qualify(true)">Квалифицировать</button><input v-model="disqualificationReason" placeholder="Причина отказа" /><button class="secondary" type="button" @click="qualify(false)">Дисквалифицировать</button></template><div v-if="(current as Lead).status === 'qualified'" class="crud-convert"><select v-model="conversion.stage_id"><option value="">Этап сделки</option><option v-for="stage in crmStore.allStages.value" :key="stage.id" :value="stage.id">{{ stage.name }}</option></select><input v-model="conversion.title" placeholder="Название сделки" /><input v-model="conversion.amount" type="number" min="0" placeholder="Сумма" /><button type="button" @click="convert">Конвертировать</button></div><RouterLink v-if="(current as Lead).converted_deal_id" class="secondary-link" :to="`/deals?deal=${(current as Lead).converted_deal_id}`">Открыть сделку</RouterLink></section>

        <section v-if="canWriteRecord && config.merge" class="crud-tool">
          <div class="duplicate-heading"><div><h3>Поиск дублей</h3><p>Показываются только пары, найденные backend.</p></div><button v-if="lifecycleStore.canManageSales.value" class="secondary" type="button" :disabled="busy" @click="scanDuplicates">Найти дубли</button></div>
          <article v-for="candidate in duplicateCandidates" :key="candidate.id" class="duplicate-candidate">
            <div><strong>{{ duplicateTitle(candidate) }}</strong><small>Совпадение {{ candidate.score }}% · {{ candidate.matched_fields.join(", ") || "совпавшие поля не указаны" }}</small></div>
            <div class="duplicate-actions"><button type="button" :disabled="busy || !duplicateRecords[duplicateRecordId(candidate)]" @click="mergeCandidate(candidate)">Объединить</button><button v-if="lifecycleStore.canManageSales.value" class="secondary" type="button" :disabled="busy" @click="dismissCandidate(candidate)">Не дубль</button></div>
          </article>
          <p v-if="!duplicateCandidates.length" class="empty">Кандидатов в дубли нет.</p>
        </section>

        <section v-if="historyOpen" class="crud-tool crud-history"><h3>История полей</h3><ol><li v-for="change in historyRows" :key="change.id"><strong>{{ change.field_name }}</strong><span>{{ displayValue(change.field_name, change.old_value) }} → {{ displayValue(change.field_name, change.new_value) }}</span><small>v{{ change.entity_version }} · {{ new Date(change.created_at).toLocaleString('ru-RU') }}</small></li></ol><p v-if="!historyRows.length">Изменений пока нет.</p></section>
      </template>

      <p v-if="error" class="alert error">{{ error }}</p><p v-if="ok" class="alert success">{{ ok }}</p>
    </aside>
    <section v-if="lifecycleStore.conflict.value" class="crud-conflict" role="alertdialog" aria-modal="true"><h2>Запись уже изменена</h2><p>Актуальная версия: {{ lifecycleStore.conflict.value.currentVersion ?? "неизвестна" }}. Перезапись остановлена.</p><button type="button" @click="lifecycleStore.clearConflict(); $emit('close')">Загрузить актуальные данные</button><button class="secondary" type="button" @click="lifecycleStore.clearConflict">Отмена</button></section>
  </div>
</template>

<style scoped>
.entity-crud-backdrop{position:fixed;inset:0;z-index:120;background:rgb(15 23 42/35%);backdrop-filter:blur(2px)}.entity-crud-drawer{position:absolute;top:0;right:0;width:min(590px,100%);height:100%;overflow-y:auto;padding:24px;background:var(--color-surface);box-shadow:-20px 0 55px rgb(15 23 42/20%)}.entity-crud-head{display:flex;align-items:flex-start;justify-content:space-between;gap:14px}.entity-crud-head h2{margin:3px 0 0;font-size:24px;overflow-wrap:anywhere}.crud-close{width:38px;padding:0;font-size:23px}.entity-crud-form{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:13px;margin-top:22px}.entity-crud-form label{margin:0}.entity-crud-form label:has(textarea),.entity-crud-form .crud-buttons{grid-column:1/-1}.crud-buttons{display:flex;flex-wrap:wrap;gap:8px;margin:18px 0}.crud-danger{color:var(--color-danger-text);border-color:var(--color-danger);background:var(--color-danger-soft)}.crud-status{display:flex;gap:10px;margin:18px 0;color:var(--muted);font-size:13px}.crud-status span:first-child{border-radius:99px;padding:5px 8px;color:var(--color-success-text);background:var(--color-success-soft);font-weight:700}.crud-fields{display:grid;grid-template-columns:150px minmax(0,1fr);margin:0}.crud-fields dt,.crud-fields dd{margin:0;border-bottom:1px solid var(--line-soft);padding:10px 0;overflow-wrap:anywhere}.crud-fields dt{color:var(--muted)}.crud-tool{display:grid;gap:9px;margin-top:18px;border-top:1px solid var(--line-soft);padding-top:18px}.crud-tool h3,.crud-tool p{margin:0}.crud-tool p{color:var(--muted);font-size:13px}.crud-convert{display:grid;gap:8px}.crud-check{display:flex;align-items:center;gap:8px;margin:0}.duplicate-heading,.duplicate-candidate,.duplicate-actions{display:flex;align-items:flex-start;justify-content:space-between;gap:8px}.duplicate-candidate{border:1px solid var(--color-border);border-radius:var(--radius-control);padding:10px}.duplicate-candidate>div:first-child{display:grid;gap:3px;min-width:0}.duplicate-candidate small{color:var(--color-text-muted);overflow-wrap:anywhere}.duplicate-actions{flex-shrink:0}.crud-history ol{display:grid;gap:8px;margin:0;padding:0;list-style:none}.crud-history li{display:grid;gap:3px;border:1px solid var(--line);border-radius:8px;padding:10px}.crud-history small{color:var(--muted)}.crud-conflict{position:absolute;top:50%;left:50%;z-index:2;width:min(420px,calc(100% - 32px));border-radius:14px;padding:24px;background:var(--color-surface);box-shadow:0 22px 60px rgb(15 23 42/25%);transform:translate(-50%,-50%)}.crud-conflict h2{margin-top:0}.crud-conflict button{margin:4px}.scoring-card{border:1px solid var(--color-border);border-radius:var(--radius-card);padding:14px;background:var(--color-ai-soft)}.scoring-heading,.score-factor-list>div{display:flex;align-items:center;justify-content:space-between;gap:12px}.scoring-heading>div{display:grid;gap:3px}.scoring-heading>strong{font-size:30px}.scoring-heading>strong small{font-size:13px}.score-grade{color:var(--color-text-primary)!important;font-weight:700}.score-factor-list{display:grid;gap:7px}.score-factor-list>div{border-top:1px solid var(--color-border-subtle);padding-top:7px}.score-factor-list span{display:grid;gap:2px}.score-factor-list small{color:var(--color-text-muted)}.score-factor-list b{white-space:nowrap}@media(max-width:620px){.entity-crud-backdrop{height:100dvh}.entity-crud-drawer{width:100dvw;height:100dvh;padding:calc(18px + env(safe-area-inset-top)) 16px calc(24px + env(safe-area-inset-bottom));box-shadow:none}.entity-crud-form{grid-template-columns:1fr}.crud-fields{grid-template-columns:110px minmax(0,1fr)}.crud-buttons{position:sticky;bottom:0;z-index:2;margin-inline:-16px;padding:10px 16px calc(10px + env(safe-area-inset-bottom));background:var(--color-surface)}.crud-buttons button{min-height:44px;flex:1}.duplicate-heading,.duplicate-candidate{align-items:stretch;flex-direction:column}.duplicate-actions button{flex:1}}
</style>
