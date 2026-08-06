import { computed, ref } from "vue";

import { api, apiErrorMessage, post } from "../api";
import type { AuthSession, MfaStatus } from "../types";
import { crmStore } from "./crm";

const sessions = ref<AuthSession[]>([]);
const mfa = ref<MfaStatus>({ enabled: false, enabled_at: null, recovery_codes_remaining: 0 });
const setupSecret = ref("");
const provisioningUri = ref("");
const recoveryCodes = ref<string[]>([]);
const loading = ref(false);
const error = ref("");
const success = ref("");
const currentSession = computed(() => sessions.value.find((session) => session.current) ?? null);

function auth() {
  return crmStore.token.value;
}

async function refresh() {
  if (!auth()) return;
  loading.value = true;
  error.value = "";
  try {
    [sessions.value, mfa.value] = await Promise.all([
      api<AuthSession[]>("/auth/sessions", {}, auth()),
      api<MfaStatus>("/auth/mfa", {}, auth())
    ]);
  } catch (caught) {
    error.value = apiErrorMessage(caught);
  } finally {
    loading.value = false;
  }
}

async function beginMfaSetup() {
  return mutate(async () => {
    const result = await api<{ secret: string; provisioning_uri: string }>("/auth/mfa/setup", post({}), auth());
    setupSecret.value = result.secret;
    provisioningUri.value = result.provisioning_uri;
  }, "Добавьте ключ в приложение-аутентификатор и подтвердите код.");
}

async function enableMfa(code: string) {
  return mutate(async () => {
    const result = await api<{ recovery_codes: string[] }>("/auth/mfa/enable", post({ code }), auth());
    recoveryCodes.value = result.recovery_codes;
    setupSecret.value = "";
    provisioningUri.value = "";
    await refresh();
  }, "MFA включена. Сохраните recovery-коды — повторно они не показываются.");
}

async function disableMfa(password: string, code: string) {
  return mutate(async () => {
    await api<void>("/auth/mfa/disable", post({ password, code }), auth());
    recoveryCodes.value = [];
    await refresh();
  }, "MFA отключена.");
}

async function regenerateRecoveryCodes(code: string) {
  return mutate(async () => {
    const result = await api<{ recovery_codes: string[] }>("/auth/mfa/recovery-codes", post({ code }), auth());
    recoveryCodes.value = result.recovery_codes;
    await refresh();
  }, "Новые recovery-коды созданы. Старые больше не действуют.");
}

async function revokeSession(id: string) {
  return mutate(async () => {
    await api<void>(`/auth/sessions/${id}`, { method: "DELETE" }, auth());
    await refresh();
  }, "Сессия завершена.");
}

async function revokeOtherSessions() {
  return mutate(async () => {
    await api<{ revoked: number }>("/auth/sessions", { method: "DELETE" }, auth());
    await refresh();
  }, "Остальные сессии завершены.");
}

async function changePassword(currentPassword: string, newPassword: string) {
  return mutate(async () => {
    await api<void>(
      "/auth/password/change",
      post({ current_password: currentPassword, new_password: newPassword }),
      auth()
    );
  }, "Пароль изменён. Все сессии завершены — войдите заново.");
}

async function mutate(action: () => Promise<void>, message: string) {
  loading.value = true;
  error.value = "";
  success.value = "";
  try {
    await action();
    success.value = message;
    return true;
  } catch (caught) {
    error.value = apiErrorMessage(caught);
    return false;
  } finally {
    loading.value = false;
  }
}

export const authSecurityStore = {
  sessions,
  mfa,
  setupSecret,
  provisioningUri,
  recoveryCodes,
  loading,
  error,
  success,
  currentSession,
  refresh,
  beginMfaSetup,
  enableMfa,
  disableMfa,
  regenerateRecoveryCodes,
  revokeSession,
  revokeOtherSessions,
  changePassword
};
