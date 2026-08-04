<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";

import type { CustomFieldEntityType, CustomFieldOperator } from "../../types";
import { customFieldsStore } from "../../stores/customFields";

const props = defineProps<{ entityType: CustomFieldEntityType }>();
const emit = defineEmits<{ change: [ids: string[] | null] }>();
const fieldId = ref("");
const operator = ref<CustomFieldOperator>("eq");
const value = ref<unknown>("");
const fields = computed(() => customFieldsStore.definitions.value[props.entityType].filter((item) => item.is_filterable && item.is_active));
const field = computed(() => fields.value.find((item) => item.id === fieldId.value));
const operators = computed(() => {
  if (["number", "date", "datetime"].includes(field.value?.field_type ?? "")) return ["eq", "neq", "gt", "gte", "lt", "lte", "is_empty"] as CustomFieldOperator[];
  if (field.value?.field_type === "text") return ["contains", "eq", "neq", "is_empty"] as CustomFieldOperator[];
  if (field.value?.field_type === "multi_select") return ["contains", "is_empty"] as CustomFieldOperator[];
  return ["eq", "neq", "is_empty"] as CustomFieldOperator[];
});

async function load() {
  try {
    await customFieldsStore.loadDefinitions(props.entityType);
  } catch {
    // The parent page remains usable when optional field metadata is unavailable.
  }
  clear();
}
async function apply() {
  if (!fieldId.value) return clear();
  emit("change", await customFieldsStore.search(props.entityType, fieldId.value, operator.value, operator.value === "is_empty" ? null : value.value));
}
function clear() { fieldId.value = ""; operator.value = "eq"; value.value = ""; emit("change", null); }
watch(() => props.entityType, load);
watch(fieldId, () => { operator.value = operators.value[0]; value.value = field.value?.field_type === "boolean" ? true : ""; });
onMounted(load);
</script>

<template>
  <div v-if="fields.length" class="custom-filter">
    <strong>Доп. поле</strong>
    <select v-model="fieldId"><option value="">Выберите поле</option><option v-for="item in fields" :key="item.id" :value="item.id">{{ item.label }}</option></select>
    <select v-if="fieldId" v-model="operator"><option v-for="item in operators" :key="item" :value="item">{{ {eq:'равно',neq:'не равно',contains:'содержит',gt:'больше',gte:'не меньше',lt:'меньше',lte:'не больше',is_empty:'не заполнено'}[item] }}</option></select>
    <template v-if="field && operator !== 'is_empty'">
      <select v-if="['select','multi_select'].includes(field.field_type)" v-model="value"><option v-for="option in field.options" :key="option" :value="option">{{ option }}</option></select>
      <select v-else-if="field.field_type === 'boolean'" v-model="value"><option :value="true">Да</option><option :value="false">Нет</option></select>
      <input v-else v-model="value" :type="field.field_type === 'number' ? 'number' : field.field_type === 'datetime' ? 'datetime-local' : field.field_type === 'date' ? 'date' : 'text'" />
    </template>
    <button v-if="fieldId" type="button" :disabled="customFieldsStore.loading.value" @click="apply">Применить</button>
    <button v-if="fieldId" class="secondary" type="button" @click="clear">Сбросить</button>
  </div>
</template>

<style scoped>
.custom-filter{display:flex;align-items:center;flex-wrap:wrap;gap:8px;border:1px solid var(--color-border);border-radius:var(--radius-control);padding:8px;background:var(--color-surface)}.custom-filter strong{font-size:12px;color:var(--color-text-muted)}.custom-filter select,.custom-filter input,.custom-filter button{width:auto;min-height:34px;padding-block:6px}
</style>
