<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";

import voknapLogo from "../assets/voknap-logo.png";
import voknapLogoDark from "../assets/voknap-logo-dark.png";
import UiAlert from "../components/ui/UiAlert.vue";
import UiButton from "../components/ui/UiButton.vue";
import UiInput from "../components/ui/UiInput.vue";
import UiThemeToggle from "../components/ui/UiThemeToggle.vue";
import { useTheme } from "../design-system/theme";
import { crmStore } from "../stores/crm";
import { api, apiErrorMessage, post } from "../api";

const router = useRouter();
const route = useRoute();
const { theme } = useTheme();
const mode = ref<"login" | "register">("login");
const resetMode = ref<"none" | "request" | "confirm">("none");
const resetEmail = ref("");
const resetToken = ref("");
const newPassword = ref("");
const localError = ref("");
const localMessage = ref("");

async function registerCompany() {
  await crmStore.registerCompany();
  if (crmStore.isAuthed.value) void router.push("/dashboard");
}

async function login() {
  await crmStore.login();
  if (crmStore.isAuthed.value) void router.push("/dashboard");
}

async function verifyMfa() {
  await crmStore.verifyMfaLogin();
  if (crmStore.isAuthed.value) void router.push("/dashboard");
}

async function requestReset() {
  localError.value = "";
  localMessage.value = "";
  try {
    const result = await api<{ message: string; dev_reset_token: string | null }>(
      "/auth/password/reset/request",
      post({ email: resetEmail.value })
    );
    localMessage.value = "Если аккаунт существует, инструкция отправлена на email.";
    if (result.dev_reset_token) {
      resetToken.value = result.dev_reset_token;
      resetMode.value = "confirm";
      localMessage.value = "Локальный режим: можно сразу задать новый пароль.";
    }
  } catch (caught) {
    localError.value = apiErrorMessage(caught);
  }
}

async function confirmReset() {
  localError.value = "";
  try {
    await api<void>(
      "/auth/password/reset/confirm",
      post({ token: resetToken.value, new_password: newPassword.value })
    );
    localMessage.value = "Пароль изменён. Войдите с новым паролем.";
    resetMode.value = "none";
    mode.value = "login";
    crmStore.loginForm.value.password = "";
  } catch (caught) {
    localError.value = apiErrorMessage(caught);
  }
}

function openLogin() {
  resetMode.value = "none";
  crmStore.mfaToken.value = "";
  localError.value = "";
}

onMounted(() => {
  const token = typeof route.query.reset_token === "string" ? route.query.reset_token : "";
  if (token) {
    resetToken.value = token;
    resetMode.value = "confirm";
  }
});
</script>

<template>
  <main class="login-shell">
    <UiThemeToggle class="login-theme" />
    <section class="login-story">
      <img class="login-logo" :src="theme === 'dark' ? voknapLogoDark : voknapLogo" alt="Voknap" />
      <div>
        <p class="eyebrow">AI Sales Workspace</p>
        <h1>Продажи, которые двигаются сами</h1>
        <p>Единое пространство для сделок, задач, коммуникаций и следующего лучшего действия.</p>
      </div>
      <ul>
        <li>Приоритеты команды на одном экране</li>
        <li>Контекст клиента без переключения вкладок</li>
        <li>AI-рекомендации с прозрачным контролем</li>
      </ul>
    </section>

    <section class="auth-card">
      <header>
        <div><p class="eyebrow">Добро пожаловать</p><h2>{{ crmStore.mfaToken.value ? "Подтверждение входа" : resetMode === "request" ? "Восстановление пароля" : resetMode === "confirm" ? "Новый пароль" : mode === "login" ? "Вход в рабочее пространство" : "Создание компании" }}</h2></div>
        <div v-if="resetMode === 'none' && !crmStore.mfaToken.value" class="auth-switch" aria-label="Режим авторизации">
          <button type="button" :class="{ active: mode === 'login' }" @click="mode = 'login'">Вход</button>
          <button type="button" :class="{ active: mode === 'register' }" @click="mode = 'register'">Регистрация</button>
        </div>
      </header>
      <UiAlert v-if="crmStore.error.value" tone="danger" title="Не удалось продолжить">{{ crmStore.error.value }}</UiAlert>
      <UiAlert v-if="crmStore.ok.value" tone="success">{{ crmStore.ok.value }}</UiAlert>
      <UiAlert v-if="localError" tone="danger" title="Не удалось продолжить">{{ localError }}</UiAlert>
      <UiAlert v-if="localMessage" tone="success">{{ localMessage }}</UiAlert>

      <form v-if="crmStore.mfaToken.value" class="auth-form" @submit.prevent="verifyMfa">
        <p class="auth-note">Введите шестизначный код из приложения-аутентификатора или recovery-код.</p>
        <UiInput v-model="crmStore.mfaCode.value" label="Код подтверждения" inputmode="numeric" autocomplete="one-time-code" autofocus />
        <UiButton type="submit" size="prominent" :loading="crmStore.isLoading.value">Подтвердить вход</UiButton>
        <button class="auth-link" type="button" @click="openLogin">Вернуться ко входу</button>
      </form>

      <form v-else-if="resetMode === 'request'" class="auth-form" @submit.prevent="requestReset">
        <UiInput v-model="resetEmail" label="Рабочий email" type="email" autocomplete="email" required />
        <UiButton type="submit" size="prominent">Получить ссылку</UiButton>
        <button class="auth-link" type="button" @click="openLogin">Вернуться ко входу</button>
      </form>

      <form v-else-if="resetMode === 'confirm'" class="auth-form" @submit.prevent="confirmReset">
        <UiInput v-model="newPassword" label="Новый пароль" type="password" autocomplete="new-password" hint="Не менее 12 символов" required />
        <UiButton type="submit" size="prominent">Изменить пароль</UiButton>
        <button class="auth-link" type="button" @click="openLogin">Вернуться ко входу</button>
      </form>

      <form v-else-if="mode === 'login'" class="auth-form" @submit.prevent="login">
        <UiInput v-model="crmStore.loginForm.value.email" label="Рабочий email" type="email" autocomplete="email" placeholder="name@company.ru" />
        <UiInput v-model="crmStore.loginForm.value.password" label="Пароль" type="password" autocomplete="current-password" />
        <UiButton type="submit" size="prominent" :loading="crmStore.isLoading.value">Войти</UiButton>
        <button class="auth-link" type="button" @click="resetMode = 'request'">Забыли пароль?</button>
        <p class="auth-note">Доступ выдаёт администратор вашего рабочего пространства.</p>
      </form>

      <form v-else class="auth-form" @submit.prevent="registerCompany">
        <div class="auth-pair">
          <UiInput v-model="crmStore.registerForm.value.company_name" label="Компания" autocomplete="organization" />
          <UiInput v-model="crmStore.registerForm.value.company_slug" label="Адрес пространства" hint="Например, voknap-team" />
        </div>
        <UiInput v-model="crmStore.registerForm.value.owner_full_name" label="Имя владельца" autocomplete="name" />
        <UiInput v-model="crmStore.registerForm.value.owner_email" label="Email владельца" type="email" autocomplete="email" />
        <UiInput v-model="crmStore.registerForm.value.owner_password" label="Пароль" type="password" autocomplete="new-password" />
        <UiButton type="submit" size="prominent" :loading="crmStore.isLoading.value">Создать рабочее пространство</UiButton>
      </form>
    </section>
  </main>
</template>

<style scoped>
.login-shell{position:relative;width:min(1120px,100%);min-height:100dvh;display:grid;grid-template-columns:minmax(0,.9fr) minmax(420px,1fr);align-items:center;gap:clamp(36px,7vw,96px);padding:clamp(72px,8vw,96px) clamp(28px,6vw,72px) clamp(28px,6vw,72px)}.login-theme{position:absolute;top:24px;right:clamp(28px,6vw,72px);width:min(320px,calc(100% - 36px))}
.login-story{display:grid;gap:28px}.login-story .login-logo{width:96px;height:96px}.login-story h1{max-width:600px;margin:6px 0 14px;font-size:clamp(38px,5vw,64px);line-height:1.02;letter-spacing:-.045em}.login-story p{max-width:560px;margin:0;color:var(--color-text-muted);font-size:16px;line-height:24px}.login-story ul{display:grid;gap:12px;margin:0;padding:0;list-style:none}.login-story li{display:flex;gap:10px;color:var(--color-text-secondary)}.login-story li::before{content:"";width:8px;height:8px;margin-top:6px;border-radius:var(--radius-pill);background:var(--color-primary)}
.auth-card{display:grid;gap:20px;border:1px solid var(--color-border);border-radius:var(--radius-modal);padding:clamp(22px,4vw,36px);background:var(--color-surface);box-shadow:var(--shadow-modal)}.auth-card header{display:grid;gap:18px}.auth-card h2{margin:4px 0 0;font-size:24px;line-height:30px}.auth-switch{display:grid;grid-template-columns:1fr 1fr;gap:4px;border:1px solid var(--color-border);border-radius:var(--radius-control);padding:4px;background:var(--color-surface-muted)}.auth-switch button{min-height:36px;border:0;border-radius:var(--radius-sm);color:var(--color-text-muted);background:transparent;box-shadow:none}.auth-switch button.active{color:var(--color-text-primary);background:var(--color-surface);box-shadow:var(--shadow-card)}.auth-form{display:grid;gap:14px}.auth-pair{display:grid;grid-template-columns:1fr 1fr;gap:12px}.auth-note{margin:0;color:var(--color-text-muted);font-size:var(--font-size-meta);line-height:var(--line-height-meta);text-align:center}.auth-link{min-height:auto;padding:2px;border:0;color:var(--color-primary);background:transparent;box-shadow:none;text-align:center}
@media(max-width:840px){.login-shell{grid-template-columns:1fr;max-width:620px}.login-story{gap:16px}.login-story h1{font-size:36px}.login-story ul{display:none}}
@media(max-width:520px){.login-shell{padding:76px 18px 18px}.login-theme{top:18px;right:18px}.login-story h1{font-size:30px}.login-story>div>p:last-child{font-size:14px}.auth-card{padding:20px 16px}.auth-pair{grid-template-columns:1fr}}
</style>
