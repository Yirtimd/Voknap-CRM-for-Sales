import { computed, ref } from "vue";

import { api, apiErrorMessage, post } from "../api";
import type {
  CustomFieldDefinition,
  CustomFieldEntityType,
  CustomFieldOperator,
  CustomFieldReport,
  CustomFieldType,
  CustomFieldValue
} from "../types";
import { crmStore } from "./crm";

const definitions = ref<Record<CustomFieldEntityType, CustomFieldDefinition[]>>({
  companies: [], contacts: [], leads: [], deals: [], tasks: []
});
const values = ref<Record<string, CustomFieldValue[]>>({});
const loading = ref(false);
const error = ref("");

function auth() {
  return { token: crmStore.token.value, tenantId: crmStore.tenantId.value };
}

async function loadDefinitions(entityType: CustomFieldEntityType, includeInactive = false) {
  const { token, tenantId } = auth();
  const rows = await api<CustomFieldDefinition[]>(
    `/custom-fields/definitions?entity_type=${entityType}&include_inactive=${includeInactive}`,
    {}, token, tenantId
  );
  definitions.value[entityType] = rows;
  return rows;
}

async function createDefinition(payload: {
  entity_type: CustomFieldEntityType;
  code: string;
  label: string;
  description?: string | null;
  field_type: CustomFieldType;
  options: string[];
  is_required: boolean;
  is_filterable: boolean;
  is_reportable: boolean;
}) {
  const { token, tenantId } = auth();
  await api<CustomFieldDefinition>("/custom-fields/definitions", post(payload), token, tenantId);
  await loadDefinitions(payload.entity_type, true);
}

async function updateDefinition(field: CustomFieldDefinition, changes: Partial<CustomFieldDefinition>) {
  const { token, tenantId } = auth();
  const updated = await api<CustomFieldDefinition>(`/custom-fields/definitions/${field.id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ version: field.version, ...changes })
  }, token, tenantId);
  await loadDefinitions(field.entity_type, true);
  return updated;
}

async function loadValues(entityType: CustomFieldEntityType, entityId: string) {
  const { token, tenantId } = auth();
  const rows = await api<CustomFieldValue[]>(
    `/custom-fields/values/${entityType}/${entityId}`, {}, token, tenantId
  );
  values.value[`${entityType}:${entityId}`] = rows;
  return rows;
}

async function saveValues(entityType: CustomFieldEntityType, entityId: string, rows: CustomFieldValue[]) {
  const { token, tenantId } = auth();
  const saved = await api<CustomFieldValue[]>(`/custom-fields/values/${entityType}/${entityId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ values: rows.map((row) => ({ field_id: row.field.id, value: row.value, version: row.version })) })
  }, token, tenantId);
  values.value[`${entityType}:${entityId}`] = saved;
  return saved;
}

async function search(
  entityType: CustomFieldEntityType,
  fieldId: string,
  operator: CustomFieldOperator,
  value: unknown
) {
  const { token, tenantId } = auth();
  const result = await api<{ entity_ids: string[] }>(`/custom-fields/search/${entityType}`, post({
    filters: [{ field_id: fieldId, operator, value }]
  }), token, tenantId);
  return result.entity_ids;
}

async function report(
  entityType: CustomFieldEntityType,
  fieldId: string,
  metric: "count" | "sum" | "avg" = "count"
) {
  const { token, tenantId } = auth();
  const measure = metric === "count" ? "" : "&measure=amount";
  return api<CustomFieldReport>(
    `/custom-fields/reports/${entityType}/${fieldId}?metric=${metric}${measure}`,
    {}, token, tenantId
  );
}

async function run<T>(action: () => Promise<T>): Promise<T> {
  loading.value = true;
  error.value = "";
  try {
    return await action();
  } catch (caught) {
    error.value = apiErrorMessage(caught, "Не удалось обработать дополнительные поля");
    throw caught;
  } finally {
    loading.value = false;
  }
}

export const customFieldsStore = {
  definitions,
  values,
  loading,
  error,
  canManage: computed(() => crmStore.me.value?.permissions.includes("custom_fields:manage") ?? false),
  loadDefinitions: (type: CustomFieldEntityType, inactive = false) => run(() => loadDefinitions(type, inactive)),
  createDefinition: (payload: Parameters<typeof createDefinition>[0]) => run(() => createDefinition(payload)),
  updateDefinition: (field: CustomFieldDefinition, changes: Partial<CustomFieldDefinition>) => run(() => updateDefinition(field, changes)),
  loadValues: (type: CustomFieldEntityType, id: string) => run(() => loadValues(type, id)),
  saveValues: (type: CustomFieldEntityType, id: string, rows: CustomFieldValue[]) => run(() => saveValues(type, id, rows)),
  search: (type: CustomFieldEntityType, fieldId: string, operator: CustomFieldOperator, value: unknown) => run(() => search(type, fieldId, operator, value)),
  report: (type: CustomFieldEntityType, fieldId: string, metric: "count" | "sum" | "avg" = "count") => run(() => report(type, fieldId, metric))
};
