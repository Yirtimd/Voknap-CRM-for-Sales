<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";

import UiAlert from "../ui/UiAlert.vue";
import UiButton from "../ui/UiButton.vue";
import UiIcon from "../ui/UiIcon.vue";
import { authSecurityStore as security } from "../../stores/authSecurity";
import { crmStore } from "../../stores/crm";

const router = useRouter();
const mfaCode = ref("");
const mfaPassword = ref("");
const currentPassword = ref("");
const newPassword = ref("");

async function changePassword() {
  if (await security.changePassword(currentPassword.value, newPassword.value)) {
    await crmStore.logout();
    void router.push("/login");
  }
}

function copyRecoveryCodes() {
  void navigator.clipboard.writeText(security.recoveryCodes.value.join("\n"));
}

onMounted(() => void security.refresh());
</script>

<template>
  <section class="security-grid">
    <UiAlert v-if="security.error.value" tone="danger" title="Безопасность">{{ security.error.value }}</UiAlert>
    <UiAlert v-if="security.success.value" tone="success">{{ security.success.value }}</UiAlert>

    <section class="panel security-card">
      <header><UiIcon name="settings" :size="20" /><div><h2>Двухфакторная защита</h2><p>Код из приложения-аутентификатора требуется после пароля.</p></div></header>
      <p class="status"><strong>{{ security.mfa.value.enabled ? "Включена" : "Выключена" }}</strong><span v-if="security.mfa.value.enabled">Recovery-кодов: {{ security.mfa.value.recovery_codes_remaining }}</span></p>

      <template v-if="!security.mfa.value.enabled">
        <UiButton v-if="!security.setupSecret.value" type="button" :loading="security.loading.value" @click="security.beginMfaSetup">Настроить MFA</UiButton>
        <div v-else class="setup-box">
          <p>Добавьте этот ключ в Google Authenticator, Microsoft Authenticator, 1Password или другое TOTP-приложение:</p>
          <code>{{ security.setupSecret.value }}</code>
          <a class="provisioning-link" :href="security.provisioningUri.value">Открыть в приложении-аутентификаторе</a>
          <label>Код из приложения<input v-model="mfaCode" inputmode="numeric" autocomplete="one-time-code" /></label>
          <UiButton type="button" :loading="security.loading.value" @click="security.enableMfa(mfaCode)">Подтвердить и включить</UiButton>
        </div>
      </template>

      <form v-else class="security-form" @submit.prevent="security.disableMfa(mfaPassword, mfaCode)">
        <label>Текущий пароль<input v-model="mfaPassword" type="password" autocomplete="current-password" /></label>
        <label>TOTP или recovery-код<input v-model="mfaCode" autocomplete="one-time-code" /></label>
        <div class="button-row">
          <UiButton variant="secondary" type="button" @click="security.regenerateRecoveryCodes(mfaCode)">Новые recovery-коды</UiButton>
          <button class="danger" type="submit">Отключить MFA</button>
        </div>
      </form>

      <div v-if="security.recoveryCodes.value.length" class="recovery-box">
        <strong>Сохраните коды в безопасном месте</strong>
        <code v-for="code in security.recoveryCodes.value" :key="code">{{ code }}</code>
        <UiButton variant="secondary" type="button" @click="copyRecoveryCodes">Скопировать все</UiButton>
      </div>
    </section>

    <form class="panel security-card" @submit.prevent="changePassword">
      <header><UiIcon name="settings" :size="20" /><div><h2>Пароль</h2><p>После смены пароля потребуется войти заново на всех устройствах.</p></div></header>
      <label>Текущий пароль<input v-model="currentPassword" type="password" autocomplete="current-password" required /></label>
      <label>Новый пароль<input v-model="newPassword" type="password" autocomplete="new-password" minlength="12" required /></label>
      <UiButton type="submit" :loading="security.loading.value">Изменить пароль</UiButton>
    </form>

    <section class="panel security-card wide">
      <header><UiIcon name="clock" :size="20" /><div><h2>Активные сессии</h2><p>Устройства, на которых выполнен вход в CRM.</p></div></header>
      <article v-for="session in security.sessions.value" :key="session.id" class="session-row">
        <div><strong>{{ session.current ? "Текущее устройство" : session.user_agent || "Неизвестное устройство" }}</strong><small>{{ session.ip_address || "IP неизвестен" }} · до {{ new Date(session.expires_at).toLocaleString("ru-RU") }}</small></div>
        <UiButton v-if="!session.current" variant="secondary" size="compact" type="button" @click="security.revokeSession(session.id)">Завершить</UiButton>
      </article>
      <p v-if="!security.sessions.value.length" class="empty">Активных сессий не найдено.</p>
      <UiButton v-if="security.sessions.value.length > 1" variant="secondary" type="button" @click="security.revokeOtherSessions">Завершить остальные</UiButton>
    </section>
  </section>
</template>

<style scoped>
.security-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px;align-items:start}.security-grid>.wide,.security-grid>:deep(.ui-alert){grid-column:1/-1}.security-card{display:grid;gap:14px;padding:20px}.security-card>header{display:flex;align-items:flex-start;gap:10px}.security-card h2{margin:0 0 3px}.security-card header p,.setup-box p{margin:0;color:var(--color-text-muted);font-size:var(--font-size-meta)}.status{display:flex;justify-content:space-between;margin:0}.security-form,.setup-box{display:grid;gap:12px}.setup-box,.recovery-box{border:1px solid var(--color-border);border-radius:var(--radius-card);padding:14px;background:var(--color-surface-muted)}.setup-box code{overflow-wrap:anywhere;font-size:13px}.provisioning-link{color:var(--color-primary);font-size:var(--font-size-meta)}.recovery-box{display:grid;grid-template-columns:repeat(2,1fr);gap:7px}.recovery-box strong,.recovery-box button{grid-column:1/-1}.session-row{display:flex;align-items:center;justify-content:space-between;gap:14px;border-top:1px solid var(--color-border);padding-top:12px}.session-row div{display:grid;gap:3px;min-width:0}.session-row strong{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.session-row small{color:var(--color-text-muted)}
@media(max-width:720px){.security-grid{grid-template-columns:1fr}.security-grid>*{grid-column:1!important}.session-row{align-items:flex-start;flex-direction:column}.recovery-box{grid-template-columns:1fr}.recovery-box strong,.recovery-box button{grid-column:1}}
</style>
