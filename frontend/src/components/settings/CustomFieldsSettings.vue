<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";

import type { CustomFieldEntityType, CustomFieldType } from "../../types";
import { customFieldsStore } from "../../stores/customFields";

const entityType = ref<CustomFieldEntityType>("companies");
const form = ref({
  code: "", label: "", description: "", field_type: "text" as CustomFieldType,
  options: "", is_required: false, is_filterable: true, is_reportable: true
});
const rows = computed(() => customFieldsStore.definitions.value[entityType.value]);
const entityOptions: Array<{ value: CustomFieldEntityType; label: string }> = [
  { value: "companies", label: "Компании" }, { value: "contacts", label: "Контакты" },
  { value: "leads", label: "Лиды" }, { value: "deals", label: "Сделки" }, { value: "tasks", label: "Задачи" }
];
const fieldTypes: Array<{ value: CustomFieldType; label: string }> = [
  { value: "text", label: "Текст" }, { value: "number", label: "Число" },
  { value: "date", label: "Дата" }, { value: "datetime", label: "Дата и время" },
  { value: "boolean", label: "Да / нет" }, { value: "select", label: "Один вариант" },
  { value: "multi_select", label: "Несколько вариантов" }
];

async function load() {
  try { await customFieldsStore.loadDefinitions(entityType.value, true); } catch { /* error is rendered below */ }
}
async function create() {
  await customFieldsStore.createDefinition({
    entity_type: entityType.value,
    code: form.value.code,
    label: form.value.label,
    description: form.value.description || null,
    field_type: form.value.field_type,
    options: ["select", "multi_select"].includes(form.value.field_type)
      ? form.value.options.split("\n").map((item) => item.trim()).filter(Boolean) : [],
    is_required: form.value.is_required,
    is_filterable: form.value.is_filterable,
    is_reportable: form.value.is_reportable
  });
  form.value.code = ""; form.value.label = ""; form.value.description = ""; form.value.options = "";
}

watch(entityType, load);
onMounted(load);
</script>

<template>
  <section class="custom-settings">
    <header><div><h2>Дополнительные поля</h2><p>Единая схема полей для карточек, фильтров и аналитики.</p></div><select v-model="entityType"><option v-for="item in entityOptions" :key="item.value" :value="item.value">{{ item.label }}</option></select></header>
    <p v-if="!customFieldsStore.canManage.value" class="alert warning">Просмотр доступен. Изменять схему может владелец или администратор.</p>
    <form v-if="customFieldsStore.canManage.value" class="field-builder" @submit.prevent="create">
      <label>Название<input v-model="form.label" required minlength="2" placeholder="Сегмент клиента" /></label>
      <label>Системный код<input v-model="form.code" required pattern="[a-z][a-z0-9_]+" placeholder="customer_segment" /></label>
      <label>Тип<select v-model="form.field_type"><option v-for="item in fieldTypes" :key="item.value" :value="item.value">{{ item.label }}</option></select></label>
      <label>Описание<input v-model="form.description" placeholder="Подсказка пользователю" /></label>
      <label v-if="['select','multi_select'].includes(form.field_type)" class="wide">Варианты, по одному в строке<textarea v-model="form.options" required rows="4"></textarea></label>
      <div class="field-flags wide"><label><input v-model="form.is_required" type="checkbox" /> Обязательное</label><label><input v-model="form.is_filterable" type="checkbox" /> В фильтрах</label><label><input v-model="form.is_reportable" type="checkbox" /> В отчётах</label></div>
      <button type="submit" :disabled="customFieldsStore.loading.value">Создать поле</button>
    </form>
    <div class="field-list">
      <article v-for="field in rows" :key="field.id" :class="{ inactive: !field.is_active }">
        <div><strong>{{ field.label }}</strong><small>{{ field.code }} · {{ fieldTypes.find((item) => item.value === field.field_type)?.label }}</small></div>
        <span>{{ field.is_required ? "Обязательное" : "Необязательное" }} · {{ field.is_filterable ? "фильтр" : "без фильтра" }} · {{ field.is_reportable ? "отчёт" : "без отчёта" }}</span>
        <button v-if="customFieldsStore.canManage.value" class="secondary" type="button" @click="customFieldsStore.updateDefinition(field, { is_active: !field.is_active })">{{ field.is_active ? "Отключить" : "Включить" }}</button>
      </article>
      <p v-if="!rows.length">Для выбранной сущности полей пока нет.</p>
    </div>
    <p v-if="customFieldsStore.error.value" class="alert error">{{ customFieldsStore.error.value }}</p>
  </section>
</template>

<style scoped>
.custom-settings{display:grid;gap:16px}.custom-settings>header{display:flex;align-items:center;justify-content:space-between;gap:16px}.custom-settings h2,.custom-settings header p{margin:0}.custom-settings header p,.field-list small,.field-list span{color:var(--color-text-muted)}.field-builder{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;border:1px solid var(--color-border);border-radius:var(--radius-card);padding:16px}.wide{grid-column:1/-1}.field-flags{display:flex;flex-wrap:wrap;gap:14px}.field-flags label{display:flex;align-items:center;gap:7px;margin:0}.field-list{display:grid;gap:8px}.field-list article{display:grid;grid-template-columns:minmax(150px,1fr) minmax(180px,1fr) auto;align-items:center;gap:12px;border:1px solid var(--color-border);border-radius:var(--radius-control);padding:12px}.field-list article>div{display:grid}.field-list .inactive{opacity:.58}@media(max-width:680px){.custom-settings>header{align-items:stretch;flex-direction:column}.field-builder{grid-template-columns:1fr}.wide{grid-column:auto}.field-list article{grid-template-columns:1fr}}
</style>
