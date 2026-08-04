<script setup lang="ts">
import { onMounted, ref, watch } from "vue";

import type { CustomFieldEntityType, CustomFieldValue } from "../../types";
import { customFieldsStore } from "../../stores/customFields";

const props = defineProps<{
  entityType: CustomFieldEntityType;
  entityId: string;
  editable?: boolean;
}>();

const rows = ref<CustomFieldValue[]>([]);
const saved = ref(false);

async function load() {
  saved.value = false;
  try {
    rows.value = await customFieldsStore.loadValues(props.entityType, props.entityId);
  } catch {
    rows.value = [];
  }
}

async function save() {
  rows.value = await customFieldsStore.saveValues(props.entityType, props.entityId, rows.value);
  saved.value = true;
}

function updateMulti(row: CustomFieldValue, option: string, checked: boolean) {
  const current = Array.isArray(row.value) ? [...row.value] as string[] : [];
  row.value = checked ? [...new Set([...current, option])] : current.filter((item) => item !== option);
}

function dateTimeValue(value: unknown) {
  if (!value) return "";
  const date = new Date(String(value));
  return Number.isNaN(date.getTime()) ? "" : new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
}

function setDateTime(row: CustomFieldValue, value: string) {
  row.value = value ? new Date(value).toISOString() : null;
}

watch(() => [props.entityType, props.entityId], load);
onMounted(load);
</script>

<template>
  <section v-if="rows.length" class="custom-values">
    <header><div><h3>Дополнительные поля</h3><p>Поля, настроенные для этого типа записи.</p></div></header>
    <div class="custom-values-grid">
      <label v-for="row in rows" :key="row.field.id">
        <span>{{ row.field.label }} <b v-if="row.field.is_required">*</b></span>
        <small v-if="row.field.description">{{ row.field.description }}</small>
        <textarea v-if="row.field.field_type === 'text'" :value="String(row.value ?? '')" :disabled="!editable" rows="3" @input="row.value = ($event.target as HTMLTextAreaElement).value"></textarea>
        <input v-else-if="row.field.field_type === 'number'" :value="row.value == null ? '' : Number(row.value)" :disabled="!editable" type="number" step="any" @input="row.value = ($event.target as HTMLInputElement).value === '' ? null : Number(($event.target as HTMLInputElement).value)" />
        <input v-else-if="row.field.field_type === 'date'" :value="String(row.value ?? '')" :disabled="!editable" type="date" @input="row.value = ($event.target as HTMLInputElement).value || null" />
        <input v-else-if="row.field.field_type === 'datetime'" :value="dateTimeValue(row.value)" :disabled="!editable" type="datetime-local" @input="setDateTime(row, ($event.target as HTMLInputElement).value)" />
        <label v-else-if="row.field.field_type === 'boolean'" class="custom-check"><input :checked="row.value === true" :disabled="!editable" type="checkbox" @change="row.value = ($event.target as HTMLInputElement).checked" /> Да</label>
        <select v-else-if="row.field.field_type === 'select'" :value="String(row.value ?? '')" :disabled="!editable" @change="row.value = ($event.target as HTMLSelectElement).value || null"><option value="">Не выбрано</option><option v-for="option in row.field.options" :key="option" :value="option">{{ option }}</option></select>
        <span v-else class="custom-multi"><label v-for="option in row.field.options" :key="option" class="custom-check"><input :checked="Array.isArray(row.value) && row.value.includes(option)" :disabled="!editable" type="checkbox" @change="updateMulti(row, option, ($event.target as HTMLInputElement).checked)" /> {{ option }}</label></span>
      </label>
    </div>
    <button v-if="editable" type="button" :disabled="customFieldsStore.loading.value" @click="save">Сохранить дополнительные поля</button>
    <p v-if="saved" class="custom-ok">Дополнительные поля сохранены.</p>
    <p v-if="customFieldsStore.error.value" class="alert error">{{ customFieldsStore.error.value }}</p>
  </section>
</template>

<style scoped>
.custom-values{display:grid;gap:12px;margin-top:18px;border-top:1px solid var(--color-border);padding-top:18px}.custom-values header h3,.custom-values header p{margin:0}.custom-values header p,.custom-values label small{color:var(--color-text-muted);font-size:12px}.custom-values-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.custom-values-grid>label{display:grid;gap:5px;margin:0}.custom-values-grid>label:has(textarea),.custom-multi{grid-column:1/-1}.custom-values-grid b{color:var(--color-danger)}.custom-check{display:flex!important;align-items:center;gap:7px;margin:0}.custom-multi{display:flex;flex-wrap:wrap;gap:10px}.custom-ok{color:var(--color-success-text);font-size:13px}@media(max-width:620px){.custom-values-grid{grid-template-columns:1fr}}
</style>
