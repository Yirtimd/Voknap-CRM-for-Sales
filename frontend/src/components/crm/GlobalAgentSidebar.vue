<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue";

import { statusLabel } from "../../design-system/statusDictionary";
import UiIcon from "../ui/UiIcon.vue";
import { crmStore } from "../../stores/crm";

const props = defineProps<{ open: boolean }>();
const emit = defineEmits<{ close: [] }>();

const messagesEl = ref<HTMLElement | null>(null);

const importantPrompts = computed(() => {
  if (crmStore.agentContext.value.type === "document") {
    return ["Сделай выжимку документа", "Найди суммы и сроки", "Какие обязательства указаны?", "Что требует внимания?"];
  }
  if (crmStore.agentContext.value.type === "deal") {
    return ["Сделай сводку по сделке", "Какие риски у сделки?", "Найди следующий шаг", "Что сказано в документах?"];
  }
  if (crmStore.agentContext.value.type === "company") {
    return ["Сделай сводку по компании", "Какие открытые задачи?", "Что известно из документов?", "Подготовь встречу"];
  }
  return ["Что нужно сделать сегодня?", "Найди риски в воронке", "Какие сделки без следующего шага?", "Ответь по базе знаний"];
});

const contextValue = computed(() => {
  const context = crmStore.agentContext.value;
  if (context.type === "document" && context.document_id) return `document:${context.document_id}`;
  if (context.type === "deal" && context.deal_id) return `deal:${context.deal_id}`;
  if (context.type === "company" && context.company_id) return `company:${context.company_id}`;
  return context.type;
});

const contextLabel = computed(() => {
  const context = crmStore.agentContext.value;
  if (context.type === "document") {
    return crmStore.knowledgeDocuments.value.find((item) => item.id === context.document_id)?.title ?? "Выбранный документ";
  }
  if (context.type === "deal") {
    return crmStore.deals.value.find((item) => item.id === context.deal_id)?.title ?? "Текущая сделка";
  }
  if (context.type === "company") {
    return crmStore.companies.value.find((item) => item.id === context.company_id)?.name ?? "Текущая компания";
  }
  return context.type === "knowledge" ? "Вся база знаний" : "Вся CRM";
});

watch(
  () => props.open,
  async (isOpen) => {
    if (!isOpen) return;
    await crmStore.refreshAgent();
    await nextTick();
    messagesEl.value?.scrollTo({ top: messagesEl.value.scrollHeight });
  }
);

async function send(message?: string) {
  if (message) crmStore.agentForm.value.message = message;
  if (!crmStore.agentForm.value.message.trim()) return;
  await crmStore.sendAgentMessage();
  await nextTick();
  messagesEl.value?.scrollTo({ top: messagesEl.value.scrollHeight, behavior: "smooth" });
}

function selectContext(event: Event) {
  const value = (event.target as HTMLSelectElement).value;
  const [type, id] = value.split(":");
  if (type === "document") {
    const document = crmStore.knowledgeDocuments.value.find((item) => item.id === id);
    crmStore.setAgentContext({
      type: "document",
      document_id: id,
      company_id: document?.company_id ?? null,
      deal_id: document?.deal_id ?? null
    });
    return;
  }
  if (type === "deal") {
    const deal = crmStore.deals.value.find((item) => item.id === id);
    crmStore.setAgentContext({ type: "deal", deal_id: id, company_id: deal?.company_id ?? null });
    return;
  }
  if (type === "company") {
    crmStore.setAgentContext({ type: "company", company_id: id });
    return;
  }
  crmStore.setAgentContext({ type: type === "knowledge" ? "knowledge" : "workspace" });
}

function formatPayload(payload: Record<string, unknown>) {
  return JSON.stringify(payload, null, 2);
}
</script>

<template>
  <aside v-if="open" class="agent-sidebar">
    <header class="agent-sidebar-head">
      <div class="agent-title">
        <h2>AI Агент</h2>
        <p>Глобальный помощник</p>
      </div>
      <button class="secondary agent-close" type="button" aria-label="Закрыть AI-агента" @click="emit('close')">Закрыть</button>
    </header>

    <section class="agent-context-picker">
      <span>Контекст</span>
      <strong>{{ contextLabel }}</strong>
      <select :value="contextValue" aria-label="Контекст AI-помощника" @change="selectContext">
        <option value="workspace">Вся CRM</option>
        <option value="knowledge">Вся база знаний</option>
        <optgroup label="Компании">
          <option v-for="company in crmStore.companies.value" :key="company.id" :value="`company:${company.id}`">{{ company.name }}</option>
        </optgroup>
        <optgroup label="Сделки">
          <option v-for="deal in crmStore.deals.value" :key="deal.id" :value="`deal:${deal.id}`">{{ deal.title }}</option>
        </optgroup>
        <optgroup label="Документы">
          <option v-for="document in crmStore.knowledgeDocuments.value" :key="document.id" :value="`document:${document.id}`">{{ document.title }}</option>
        </optgroup>
      </select>
      <label v-if="['company', 'deal'].includes(crmStore.agentContext.value.type)">
        <input v-model="crmStore.agentContext.value.include_global" type="checkbox" />
        Добавлять общую базу знаний
      </label>
    </section>

    <section class="agent-card agent-summary">
      <header>
        <strong>Сводка по CRM</strong>
        <button type="button" aria-label="Открыть сводку" @click="send('Дай сводку по CRM')"><UiIcon name="chevronRight" :size="17" /></button>
      </header>
      <div class="agent-context">
        <div><strong>{{ crmStore.openTasks.value.length }}</strong><small>Открытые задачи</small></div>
        <div><strong>{{ crmStore.deals.value.length }}</strong><small>Сделки</small></div>
        <div><strong>{{ crmStore.money(crmStore.totalPipeline.value) }}</strong><small>Портфель</small></div>
      </div>
    </section>

    <section class="agent-card agent-important">
      <h3>Что важно</h3>
      <button
        v-for="prompt in importantPrompts"
        :key="prompt"
        type="button"
        @click="send(prompt)"
      >
        <span class="prompt-icon"><UiIcon name="target" :size="16" /></span>
        <strong>{{ prompt }}</strong>
        <UiIcon name="chevronRight" :size="16" />
      </button>
    </section>

    <section ref="messagesEl" class="agent-messages">
      <article v-for="message in crmStore.agentHistory.value" :key="message.id" class="agent-message" :class="message.role">
        <strong>{{ message.role === "user" ? "Вы" : "Агент" }}</strong>
        <p>{{ message.content }}</p>
        <section v-if="message.role === 'assistant' && message.sources.length" class="agent-sources">
          <span>Источники: {{ message.sources.length }}</span>
          <button
            v-for="source in message.sources.slice(0, 3)"
            :key="source.chunk_id"
            type="button"
            class="secondary"
            :disabled="!source.download_url"
            @click="crmStore.downloadAgentSource(source)"
          >
            {{ source.document_title }}<small v-if="source.page_number"> · стр. {{ source.page_number }}</small>
          </button>
        </section>
        <div v-if="message.role === 'assistant' && message.query_id" class="agent-feedback">
          <span>Ответ полезен?</span>
          <button
            type="button"
            class="secondary"
            :class="{ active: crmStore.agentFeedback.value[message.query_id] === 'up' }"
            @click="crmStore.sendAgentFeedback(message.query_id, 'up')"
          >Да</button>
          <button
            type="button"
            class="secondary"
            :class="{ active: crmStore.agentFeedback.value[message.query_id] === 'down' }"
            @click="crmStore.sendAgentFeedback(message.query_id, 'down')"
          >Нет</button>
        </div>
      </article>
      <p v-if="!crmStore.agentHistory.value.length" class="empty">Истории пока нет. Выберите быстрый запрос или напишите сообщение.</p>
    </section>

    <section v-if="crmStore.agentActions.value.length" class="agent-actions">
      <h3>Действия</h3>
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
    </section>

    <form class="agent-card agent-composer" @submit.prevent="send()">
      <div class="composer-shell">
        <textarea v-model="crmStore.agentForm.value.message" placeholder="Спросите что угодно..." rows="2"></textarea>
        <button type="submit" :disabled="crmStore.isLoading.value" aria-label="Отправить"><UiIcon name="send" :size="17" /></button>
      </div>
      <small>AI может ошибаться</small>
    </form>
  </aside>
</template>

<style scoped>
.agent-context-picker { display:grid; gap:6px; margin:0 14px; padding:12px; border:1px solid var(--line); border-radius:12px; background:var(--surface-solid); }
.agent-context-picker > span { color:var(--text-muted); font-size:11px; text-transform:uppercase; }
.agent-context-picker select { width:100%; min-height:38px; }
.agent-context-picker label { display:flex; align-items:center; gap:7px; color:var(--text-muted); font-size:12px; }
.agent-sources { display:grid; gap:5px; margin-top:10px; padding-top:8px; border-top:1px solid var(--line); }
.agent-sources > span { color:var(--text-muted); font-size:11px; }
.agent-sources button { width:100%; justify-content:flex-start; overflow:hidden; font-size:11px; text-overflow:ellipsis; white-space:nowrap; }
.agent-feedback { display:flex; align-items:center; gap:5px; margin-top:8px; color:var(--text-muted); font-size:11px; }
.agent-feedback button { min-height:28px; padding:3px 9px; font-size:11px; }
.agent-feedback button.active { border-color:var(--primary); color:var(--primary); }
</style>
