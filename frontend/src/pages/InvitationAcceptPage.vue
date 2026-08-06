<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { useRoute, useRouter } from "vue-router";

import { crmStore } from "../stores/crm";
import { teamStore } from "../stores/team";

const route = useRoute();
const router = useRouter();
const form = reactive({ token: "", full_name: "", password: "" });
const done = ref(false);

onMounted(() => {
  form.token = typeof route.query.token === "string" ? route.query.token : "";
});

async function accept() {
  try {
    const result = await teamStore.acceptInvitation({
      token: form.token.trim(),
      full_name: form.full_name.trim() || null,
      password: form.password
    });
    crmStore.token.value = result.access_token;
    crmStore.tenantId.value = result.tenant_id;
    localStorage.setItem("cmr_tenant_id", result.tenant_id);
    await crmStore.refreshSession();
    await crmStore.refreshMe();
    done.value = true;
  } catch {
    // Store renders normalized API error.
  }
}
</script>

<template>
  <main class="invite-accept-page">
    <section class="invite-card">
      <p class="eyebrow">Voknap CRM</p>
      <h1>Принять приглашение</h1>
      <template v-if="!done">
        <p>Ссылка одноразовая. Для существующего пользователя укажите текущий пароль.</p>
        <form @submit.prevent="accept">
          <label>Токен приглашения<input v-model="form.token" required minlength="32" autocomplete="off" /></label>
          <label>Имя нового пользователя<input v-model="form.full_name" minlength="2" autocomplete="name" /></label>
          <label>Пароль<input v-model="form.password" type="password" required minlength="12" maxlength="72" autocomplete="current-password" /></label>
          <button type="submit" :disabled="teamStore.loading.value">Принять приглашение</button>
        </form>
        <p v-if="teamStore.error.value" class="alert error">{{ teamStore.error.value }}</p>
      </template>
      <template v-else><div class="alert success">Приглашение принято. Доступ активирован.</div><button type="button" @click="router.push('/home')">Перейти в CRM</button></template>
    </section>
  </main>
</template>

<style scoped>
.invite-accept-page{display:grid;min-height:100vh;place-items:center;padding:20px;background:#f4f6f9}.invite-card{width:min(480px,100%);border:1px solid var(--line);border-radius:16px;padding:28px;background:#fff;box-shadow:0 18px 50px rgb(15 23 42/10%)}.invite-card h1{margin:4px 0 10px}.invite-card>p{color:var(--muted)}.invite-card form{display:grid;gap:14px;margin:22px 0}.invite-card label{margin:0}
</style>
