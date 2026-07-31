import { computed, ref } from "vue";

import { api, post } from "../api";
import type {
  Cadence,
  CadenceEmailAccount,
  CadenceEnrollment,
  CadenceExecution,
  CadenceStepType
} from "../types";
import { crmStore } from "./crm";

const cadences = ref<Cadence[]>([]);
const enrollments = ref<CadenceEnrollment[]>([]);
const executions = ref<Record<string, CadenceExecution[]>>({});
const emailAccounts = ref<CadenceEmailAccount[]>([]);
const loading = ref(false);
const error = ref("");

const canManage = computed(() => crmStore.me.value?.permissions.includes("sales:manage") ?? false);

function auth(): [string, string] {
  return [crmStore.token.value, crmStore.tenantId.value];
}

async function refresh(companyId?: string) {
  loading.value = true;
  error.value = "";
  try {
    const query = companyId ? `?company_id=${encodeURIComponent(companyId)}` : "";
    [cadences.value, enrollments.value, emailAccounts.value] = await Promise.all([
      api<Cadence[]>("/sequences", {}, ...auth()),
      api<CadenceEnrollment[]>(`/sequences/enrollments${query}`, {}, ...auth()),
      api<CadenceEmailAccount[]>("/sequences/email-accounts", {}, ...auth())
    ]);
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "Не удалось загрузить sequences";
  } finally {
    loading.value = false;
  }
}

async function createCadence(payload: {
  name: string;
  description?: string;
  steps: Array<{
    step_type: CadenceStepType;
    delay_minutes: number;
    title: string;
    body?: string;
    task_priority: "low" | "normal" | "high" | "urgent";
  }>;
}) {
  await api<Cadence>("/sequences", post(payload), ...auth());
  await refresh();
}

async function enroll(payload: {
  cadence_id: string;
  contact_id: string;
  deal_id?: string | null;
  connector_account_id?: string | null;
}, companyId: string) {
  await api<CadenceEnrollment>("/sequences/enrollments", post(payload), ...auth());
  await Promise.all([refresh(companyId), crmStore.refreshAll(), crmStore.loadCompanyWorkspace(companyId)]);
}

async function act(
  enrollment: CadenceEnrollment,
  action: "pause" | "resume" | "stop",
  companyId: string,
  reason?: string
) {
  await api<CadenceEnrollment>(
    `/sequences/enrollments/${enrollment.id}/${action}`,
    post({ version: enrollment.version, reason }),
    ...auth()
  );
  await Promise.all([refresh(companyId), crmStore.refreshAll(), crmStore.loadCompanyWorkspace(companyId)]);
}

async function refreshExecutions(enrollmentId: string) {
  const rows = await api<CadenceExecution[]>(
    `/sequences/enrollments/${enrollmentId}/executions`,
    {},
    ...auth()
  );
  executions.value = { ...executions.value, [enrollmentId]: rows };
}

async function runDue(companyId: string) {
  const result = await api<{ evaluated: number; executed: number }>(
    "/sequences/run-due",
    post({}),
    ...auth()
  );
  crmStore.ok.value = `Cadence: выполнено ${result.executed} из ${result.evaluated}`;
  await Promise.all([refresh(companyId), crmStore.refreshAll(), crmStore.loadCompanyWorkspace(companyId)]);
}

export const sequenceStore = {
  cadences,
  enrollments,
  executions,
  emailAccounts,
  loading,
  error,
  canManage,
  refresh,
  createCadence,
  enroll,
  act,
  refreshExecutions,
  runDue
};
