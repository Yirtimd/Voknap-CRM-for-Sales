<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";

import type { CustomFieldEntityType, CustomFieldReport } from "../../types";
import { customFieldsStore } from "../../stores/customFields";

const entityType = ref<CustomFieldEntityType>("deals");
const fieldId = ref("");
const metric = ref<"count" | "sum" | "avg">("count");
const report = ref<CustomFieldReport | null>(null);
const fields = computed(() => customFieldsStore.definitions.value[entityType.value].filter((item) => item.is_active && item.is_reportable));
const max = computed(() => Math.max(...(report.value?.buckets.map((item) => item.value) ?? [1]), 1));

async function loadFields() {
  try {
    await customFieldsStore.loadDefinitions(entityType.value);
  } catch {
    // Existing analytics remains available if custom metadata cannot be loaded.
  }
  fieldId.value = fields.value[0]?.id ?? "";
  report.value = null;
}
async function build() {
  if (!fieldId.value) return;
  report.value = await customFieldsStore.report(entityType.value, fieldId.value, metric.value);
}
watch(entityType, loadFields);
onMounted(loadFields);
</script>

<template>
  <section class="analytics-panel custom-report">
    <header><div><p class="eyebrow">Конструктор отчёта</p><h3>Срез по дополнительному полю</h3></div></header>
    <div class="report-controls">
      <select v-model="entityType"><option value="companies">Компании</option><option value="contacts">Контакты</option><option value="leads">Лиды</option><option value="deals">Сделки</option><option value="tasks">Задачи</option></select>
      <select v-model="fieldId"><option value="">Выберите поле</option><option v-for="field in fields" :key="field.id" :value="field.id">{{ field.label }}</option></select>
      <select v-model="metric"><option value="count">Количество</option><option v-if="entityType === 'deals'" value="sum">Сумма сделок</option><option v-if="entityType === 'deals'" value="avg">Средний чек</option></select>
      <button type="button" :disabled="!fieldId || customFieldsStore.loading.value" @click="build">Построить</button>
    </div>
    <p v-if="!fields.length">Сначала отметьте хотя бы одно активное поле как доступное для отчётов.</p>
    <div v-if="report" class="report-bars"><article v-for="bucket in report.buckets" :key="bucket.label"><span>{{ bucket.label }} <small>{{ bucket.count }} записей</small></span><div><i :style="{width: `${Math.max(2, bucket.value / max * 100)}%`}"></i></div><strong>{{ metric === 'count' ? bucket.value : new Intl.NumberFormat('ru-RU', {style:'currency',currency:'RUB',maximumFractionDigits:0}).format(bucket.value) }}</strong></article></div>
    <p v-if="customFieldsStore.error.value" class="alert error">{{ customFieldsStore.error.value }}</p>
  </section>
</template>

<style scoped>
.custom-report{display:grid;gap:14px}.custom-report h3,.custom-report p{margin:0}.report-controls{display:flex;flex-wrap:wrap;gap:8px}.report-controls select,.report-controls button{width:auto}.report-bars{display:grid;gap:10px}.report-bars article{display:grid;grid-template-columns:minmax(120px,1fr) minmax(160px,3fr) auto;align-items:center;gap:10px}.report-bars span{display:grid}.report-bars small{color:var(--color-text-muted)}.report-bars div{height:8px;border-radius:99px;background:var(--color-surface-muted);overflow:hidden}.report-bars i{display:block;height:100%;border-radius:inherit;background:var(--color-primary)}@media(max-width:620px){.report-bars article{grid-template-columns:1fr auto}.report-bars article div{grid-column:1/-1;grid-row:2}}
</style>
