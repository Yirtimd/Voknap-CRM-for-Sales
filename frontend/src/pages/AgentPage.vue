<script setup lang="ts">
import { onMounted } from "vue";

import { statusLabel } from "../design-system/statusDictionary";
import { crmStore } from "../stores/crm";

onMounted(() => {
  void crmStore.refreshAgent();
});

function formatPayload(payload: Record<string, unknown>) {
  return JSON.stringify(payload, null, 2);
}
</script>

<template>
  <section class="section-grid">
    <form class="panel wide" @submit.prevent="crmStore.sendAgentMessage()">
      <h2>AI агент</h2>
      <label>Сообщение<textarea v-model="crmStore.agentForm.value.message" class="agent-input"></textarea></label>
      <div class="button-row">
        <button type="submit">Отправить</button>
        <button class="secondary" type="button" @click="crmStore.agentForm.value.message = 'Дай сводку по CRM'">Сводка</button>
        <button class="secondary" type="button" @click="crmStore.agentForm.value.message = 'Создай задачу позвонить клиенту'">Задача</button>
      </div>
    </form>

    <section class="panel">
      <h2>Диалог</h2>
      <div v-for="message in crmStore.agentHistory.value" :key="message.id" class="chat-message" :class="message.role">
        <strong>{{ message.role === "user" ? "Вы" : "Агент" }}</strong>
        <p>{{ message.content }}</p>
      </div>
      <p v-if="!crmStore.agentHistory.value.length" class="empty">Истории пока нет</p>
    </section>

    <section class="panel">
      <h2>Действия на подтверждение</h2>
      <article v-for="action in crmStore.agentActions.value" :key="action.id" class="action-card">
        <header>
          <strong>{{ action.action_type }}</strong>
          <small>{{ statusLabel(action.status, "aiAction") }}</small>
        </header>
        <pre>{{ formatPayload(action.payload) }}</pre>
        <div v-if="action.status === 'pending'" class="button-row">
          <button type="button" @click="crmStore.confirmAgentAction(action.id)">Подтвердить</button>
          <button class="secondary" type="button" @click="crmStore.rejectAgentAction(action.id)">Отклонить</button>
        </div>
      </article>
      <p v-if="!crmStore.agentActions.value.length" class="empty">Действий пока нет</p>
    </section>

    <section class="panel wide">
      <h2>Источники последнего ответа</h2>
      <div v-for="source in crmStore.agentLastResponse.value?.sources ?? []" :key="String(source.chunk_id)" class="source-card">
        <strong>{{ source.document_title }}</strong>
        <small>score {{ Number(source.score ?? 0).toFixed(3) }}</small>
        <p>{{ source.text }}</p>
      </div>
      <p v-if="!crmStore.agentLastResponse.value?.sources?.length" class="empty">Источников пока нет</p>
    </section>
  </section>
</template>
