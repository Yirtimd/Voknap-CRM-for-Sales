<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";

import { statusLabel } from "../../design-system/statusDictionary";
import UiIcon from "../ui/UiIcon.vue";
import { crmStore } from "../../stores/crm";

const props = defineProps<{ open: boolean }>();
const emit = defineEmits<{ close: [] }>();

const messagesEl = ref<HTMLElement | null>(null);
const activeView = ref<"chat" | "actions">("chat");
const contextOpen = ref(false);
const isExpanded = ref(false);
const sessionStartIndex = ref(0);

const importantPrompts = computed(() => {
  if (crmStore.agentContext.value.type === "document") {
    return ["Сделай выжимку документа", "Найди суммы и сроки", "Что требует внимания?"];
  }
  if (crmStore.agentContext.value.type === "deal") {
    return ["Сделай сводку по сделке", "Какие риски у сделки?", "Найди следующий шаг"];
  }
  if (crmStore.agentContext.value.type === "company") {
    return ["Сделай сводку по компании", "Какие открытые задачи?", "Подготовь встречу"];
  }
  return ["Дай сводку по CRM", "Найди риски в воронке", "Какие сделки без следующего шага?"];
});

const visibleHistory = computed(() => crmStore.agentHistory.value.slice(sessionStartIndex.value));
const pendingActions = computed(() => crmStore.agentActions.value.filter((action) => action.status === "pending"));

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
    sessionStartIndex.value = 0;
    await nextTick();
    messagesEl.value?.scrollTo({ top: messagesEl.value.scrollHeight });
  }
);

async function send(message?: string) {
  if (message) crmStore.agentForm.value.message = message;
  if (!crmStore.agentForm.value.message.trim()) return;
  const response = await crmStore.sendAgentMessage();
  if (response) crmStore.agentForm.value.message = "";
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
    contextOpen.value = false;
    return;
  }
  if (type === "deal") {
    const deal = crmStore.deals.value.find((item) => item.id === id);
    crmStore.setAgentContext({ type: "deal", deal_id: id, company_id: deal?.company_id ?? null });
    contextOpen.value = false;
    return;
  }
  if (type === "company") {
    crmStore.setAgentContext({ type: "company", company_id: id });
    contextOpen.value = false;
    return;
  }
  crmStore.setAgentContext({ type: type === "knowledge" ? "knowledge" : "workspace" });
  contextOpen.value = false;
}

function startNewChat() {
  sessionStartIndex.value = crmStore.agentHistory.value.length;
  crmStore.agentForm.value.message = "";
  activeView.value = "chat";
}

function payloadEntries(payload: Record<string, unknown>) {
  return Object.entries(payload).map(([key, value]) => ({
    key,
    label: key.replace(/_/g, " "),
    value: typeof value === "object" ? JSON.stringify(value) : String(value ?? "—")
  }));
}

function handleKeydown(event: KeyboardEvent) {
  if (!props.open || event.key !== "Escape") return;
  if (contextOpen.value) {
    contextOpen.value = false;
    return;
  }
  emit("close");
}

onMounted(() => window.addEventListener("keydown", handleKeydown));
onBeforeUnmount(() => window.removeEventListener("keydown", handleKeydown));
</script>

<template>
  <aside v-if="open" class="agent-sidebar" :class="{ 'is-wide': isExpanded }" aria-label="AI-ассистент">
    <header class="agent-sidebar-head">
      <div class="agent-title">
        <span class="agent-title-icon"><UiIcon name="sparkles" :size="19" /></span>
        <div><h2>AI-ассистент</h2><p>Глобальный помощник</p></div>
      </div>
      <div class="agent-head-actions">
        <button class="agent-icon-button" type="button" aria-label="Новый чат" title="Новый чат" @click="startNewChat"><UiIcon name="plus" :size="18" /></button>
        <button class="agent-icon-button agent-expand" type="button" :aria-label="isExpanded ? 'Свернуть AI-ассистента' : 'Развернуть AI-ассистента'" :title="isExpanded ? 'Свернуть' : 'Развернуть'" @click="isExpanded = !isExpanded"><UiIcon :name="isExpanded ? 'minimize' : 'maximize'" :size="18" /></button>
        <button class="agent-icon-button" type="button" aria-label="Закрыть AI-ассистента" title="Закрыть" @click="emit('close')"><UiIcon name="close" :size="18" /></button>
      </div>
    </header>

    <section class="agent-toolbar">
      <div class="agent-view-tabs" role="tablist" aria-label="Разделы AI-ассистента">
        <button type="button" role="tab" :aria-selected="activeView === 'chat'" :class="{ active: activeView === 'chat' }" @click="activeView = 'chat'">Чат</button>
        <button type="button" role="tab" :aria-selected="activeView === 'actions'" :class="{ active: activeView === 'actions' }" @click="activeView = 'actions'">Действия <span v-if="pendingActions.length">{{ pendingActions.length }}</span></button>
      </div>
      <button class="agent-context-chip" type="button" :aria-expanded="contextOpen" aria-controls="agent-context-popover" @click="contextOpen = !contextOpen"><UiIcon name="target" :size="15" /><span>{{ contextLabel }}</span><UiIcon name="chevronDown" :size="15" /></button>
      <section v-if="contextOpen" id="agent-context-popover" class="agent-context-popover">
        <label>Контекст
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
        </label>
        <label v-if="['company', 'deal'].includes(crmStore.agentContext.value.type)" class="agent-global-context">
          <input v-model="crmStore.agentContext.value.include_global" type="checkbox" />
          Добавлять общую базу знаний
        </label>
      </section>
    </section>

    <template v-if="activeView === 'chat'">
      <section ref="messagesEl" class="agent-messages" aria-live="polite">
        <section v-if="!visibleHistory.length" class="agent-empty">
          <span class="agent-empty-icon"><UiIcon name="sparkles" :size="24" /></span>
          <div><h3>Чем помочь?</h3><p>Спросите о CRM, сделках или документах.</p></div>
          <div class="agent-starters">
            <button v-for="prompt in importantPrompts" :key="prompt" type="button" @click="send(prompt)"><UiIcon name="sparkles" :size="16" /><span>{{ prompt }}</span><UiIcon name="chevronRight" :size="16" /></button>
          </div>
        </section>
        <article v-for="message in visibleHistory" :key="message.id" class="agent-message" :class="message.role">
          <strong>{{ message.role === "user" ? "Вы" : "AI-ассистент" }}</strong>
          <p>{{ message.content }}</p>
          <details v-if="message.role === 'assistant' && message.sources.length" class="agent-sources">
            <summary>Источники · {{ message.sources.length }}</summary>
            <button
              v-for="source in message.sources.slice(0, 3)"
              :key="source.chunk_id"
              type="button"
              :disabled="!source.download_url"
              @click="crmStore.downloadAgentSource(source)"
            >
              {{ source.document_title }}<small v-if="source.page_number"> · стр. {{ source.page_number }}</small>
            </button>
          </details>
          <div v-if="message.role === 'assistant' && message.query_id" class="agent-feedback">
            <span>Ответ полезен?</span>
            <button type="button" :class="{ active: crmStore.agentFeedback.value[message.query_id] === 'up' }" aria-label="Ответ полезен" @click="crmStore.sendAgentFeedback(message.query_id, 'up')"><UiIcon name="check" :size="14" /></button>
            <button type="button" :class="{ active: crmStore.agentFeedback.value[message.query_id] === 'down' }" aria-label="Ответ не полезен" @click="crmStore.sendAgentFeedback(message.query_id, 'down')"><UiIcon name="close" :size="14" /></button>
          </div>
        </article>
        <div v-if="crmStore.isLoading.value" class="agent-thinking"><span></span><span></span><span></span><small>AI-ассистент думает</small></div>
      </section>

      <form class="agent-composer" @submit.prevent="send()">
        <div class="composer-shell">
          <textarea v-model="crmStore.agentForm.value.message" placeholder="Спросите AI-ассистента…" rows="2" aria-label="Сообщение AI-ассистенту" @keydown.enter.exact.prevent="send()"></textarea>
          <button type="submit" :disabled="crmStore.isLoading.value || !crmStore.agentForm.value.message.trim()" aria-label="Отправить"><UiIcon name="send" :size="18" /></button>
        </div>
        <small>AI может ошибаться — проверяйте важные данные</small>
      </form>
    </template>

    <section v-else class="agent-actions">
      <header><div><h3>Действия AI</h3><p>Изменения CRM требуют подтверждения.</p></div><span>{{ pendingActions.length }} ожидают</span></header>
      <article v-for="action in crmStore.agentActions.value" :key="action.id" class="action-card">
        <header>
          <strong>{{ action.action_type }}</strong>
          <small>{{ statusLabel(action.status, "aiAction") }}</small>
        </header>
        <dl><div v-for="item in payloadEntries(action.payload)" :key="item.key"><dt>{{ item.label }}</dt><dd>{{ item.value }}</dd></div></dl>
        <div v-if="action.status === 'pending'" class="button-row">
          <button type="button" @click="crmStore.confirmAgentAction(action.id)">Подтвердить действие</button>
          <button class="secondary" type="button" @click="crmStore.rejectAgentAction(action.id)">Отклонить</button>
        </div>
      </article>
      <p v-if="!crmStore.agentActions.value.length" class="agent-actions-empty">Действий пока нет.</p>
    </section>
  </aside>
</template>

<style scoped>
.agent-sidebar{grid-template-rows:auto auto minmax(0,1fr) auto;gap:0;width:min(430px,100vw);padding:0;color:var(--color-text-primary);border-color:var(--color-border);background:var(--color-surface);box-shadow:var(--shadow-drawer);transition:width 180ms ease}.agent-sidebar.is-wide{width:min(640px,100vw)}.agent-sidebar-head{min-height:64px;align-items:center;padding:12px 16px;border-bottom:1px solid var(--color-border-subtle)}.agent-title{display:flex;align-items:center;gap:10px}.agent-title-icon,.agent-empty-icon{display:grid;place-items:center;flex:0 0 auto;color:var(--color-ai);background:var(--color-ai-soft)}.agent-title-icon{width:38px;height:38px;border-radius:var(--radius-control)}.agent-title h2{color:var(--color-text-primary);font-size:16px;line-height:24px}.agent-title p{margin:0;color:var(--color-text-muted);font-size:12px;line-height:17px}.agent-head-actions{display:flex;gap:4px}.agent-icon-button{display:grid;place-items:center;width:38px;min-width:38px;height:38px;min-height:38px;padding:0;color:var(--color-text-secondary);border:0;border-radius:var(--radius-control);background:transparent;box-shadow:none}.agent-icon-button:hover{color:var(--color-text-primary);background:var(--color-surface-muted)}.agent-toolbar{position:relative;display:flex;align-items:center;justify-content:space-between;gap:8px;min-height:52px;padding:7px 16px;border-bottom:1px solid var(--color-border-subtle);background:var(--color-surface)}.agent-view-tabs{display:flex;gap:3px;padding:3px;border-radius:var(--radius-control);background:var(--color-surface-muted)}.agent-view-tabs button{gap:6px;min-height:32px;padding:5px 10px;color:var(--color-text-muted);border:0;background:transparent;box-shadow:none;font-size:13px}.agent-view-tabs button.active{color:var(--color-text-primary);background:var(--color-surface);box-shadow:var(--shadow-card)}.agent-view-tabs button span{display:grid;place-items:center;min-width:18px;height:18px;padding:0 5px;color:var(--color-ai);border-radius:var(--radius-pill);background:var(--color-ai-soft);font-size:11px}.agent-context-chip{display:flex;min-width:0;max-width:52%;min-height:38px;padding:7px 9px;color:var(--color-ai);border:1px solid var(--color-border);background:var(--color-surface-subtle);box-shadow:none}.agent-context-chip span{overflow:hidden;color:var(--color-text-secondary);font-size:13px;text-overflow:ellipsis;white-space:nowrap}.agent-context-popover{position:absolute;top:calc(100% + 6px);right:16px;z-index:3;display:grid;gap:12px;width:min(340px,calc(100vw - 32px));padding:14px;border:1px solid var(--color-border);border-radius:var(--radius-panel);background:var(--color-surface);box-shadow:var(--shadow-popover)}.agent-context-popover label{display:grid;gap:7px;margin:0;color:var(--color-text-secondary);font-size:13px;font-weight:600}.agent-context-popover select{width:100%;min-height:44px}.agent-context-popover .agent-global-context{display:flex;align-items:center;font-weight:400}.agent-messages{gap:14px;min-height:0;padding:20px 18px;overflow-y:auto;border:0;background:var(--color-bg-canvas);scrollbar-gutter:stable}.agent-empty{display:grid;place-items:center;align-content:center;gap:14px;min-height:100%;padding:24px 0;text-align:center}.agent-empty-icon{width:52px;height:52px;border-radius:var(--radius-panel)}.agent-empty h3{margin:0;color:var(--color-text-primary);font-size:20px;line-height:28px}.agent-empty p{margin:3px 0 0;color:var(--color-text-muted);font-size:14px;line-height:20px}.agent-starters{display:grid;gap:8px;width:100%;max-width:460px;margin-top:8px}.agent-starters button{display:grid;grid-template-columns:20px minmax(0,1fr) 18px;align-items:center;min-height:48px;padding:10px 12px;color:var(--color-text-secondary);border:1px solid color-mix(in srgb,var(--color-ai) 28%,var(--color-border));border-radius:var(--radius-card);background:var(--color-ai-soft);box-shadow:none;text-align:left}.agent-starters button>svg:first-child{color:var(--color-ai)}.agent-starters button span{font-size:14px;font-weight:600;line-height:20px}.agent-starters button:hover{border-color:var(--color-ai);transform:translateY(-1px)}.agent-message{gap:6px;max-width:88%;padding:12px 14px;color:var(--color-text-secondary);border:1px solid var(--color-border);border-radius:var(--radius-card);background:var(--color-surface);box-shadow:var(--shadow-card)}.agent-message.assistant{justify-self:start;border-color:color-mix(in srgb,var(--color-ai) 24%,var(--color-border));background:color-mix(in srgb,var(--color-ai-soft) 45%,var(--color-surface))}.agent-message.user{justify-self:end;color:var(--color-text-primary);border-color:color-mix(in srgb,var(--color-primary) 28%,var(--color-border));background:var(--color-primary-soft)}.agent-message>strong{color:var(--color-text-muted);font-size:12px;line-height:17px}.agent-message p{color:inherit;font-size:14px;line-height:20px}.agent-sources{margin-top:5px;padding-top:8px;border-top:1px solid var(--color-border-subtle)}.agent-sources summary{cursor:pointer;color:var(--color-ai);font-size:12px;font-weight:600}.agent-sources button{justify-content:flex-start;width:100%;min-height:34px;margin-top:6px;overflow:hidden;padding:6px 8px;color:var(--color-text-secondary);border:1px solid var(--color-border);background:var(--color-surface);box-shadow:none;font-size:12px;text-overflow:ellipsis;white-space:nowrap}.agent-feedback{display:flex;align-items:center;gap:5px;margin-top:5px;color:var(--color-text-muted);font-size:12px}.agent-feedback button{display:grid;place-items:center;width:30px;min-width:30px;height:30px;min-height:30px;padding:0;color:var(--color-text-muted);border:1px solid transparent;background:transparent;box-shadow:none}.agent-feedback button:hover,.agent-feedback button.active{color:var(--color-ai);border-color:var(--color-border);background:var(--color-ai-soft)}.agent-thinking{display:flex;align-items:center;gap:4px;justify-self:start;padding:10px 12px;color:var(--color-text-muted);border:1px solid var(--color-border);border-radius:var(--radius-card);background:var(--color-surface)}.agent-thinking span{width:6px;height:6px;border-radius:50%;background:var(--color-ai);animation:agent-pulse 1s ease-in-out infinite}.agent-thinking span:nth-child(2){animation-delay:120ms}.agent-thinking span:nth-child(3){animation-delay:240ms}.agent-thinking small{margin-left:5px;font-size:12px}.agent-composer{display:grid;gap:7px;padding:12px 16px calc(12px + env(safe-area-inset-bottom));border-top:1px solid var(--color-border);background:var(--color-surface)}.composer-shell{grid-template-columns:minmax(0,1fr) 44px;gap:10px;align-items:end;min-height:64px;padding:9px 9px 9px 12px;border:1px solid var(--color-border-strong);border-radius:var(--radius-panel);background:var(--color-surface-subtle)}.composer-shell:focus-within{border-color:var(--color-ai);box-shadow:0 0 0 3px color-mix(in srgb,var(--color-ai) 18%,transparent)}.composer-shell textarea{field-sizing:content;min-height:44px;max-height:120px;padding:10px 0;color:var(--color-text-primary);background:transparent;font-size:14px;line-height:20px}.composer-shell button{width:44px;min-width:44px;height:44px;min-height:44px;color:var(--color-text-on-accent);border-radius:var(--radius-control);background:var(--color-ai)}.composer-shell button:hover:not(:disabled){background:var(--color-ai-hover)}.agent-composer>small{color:var(--color-text-muted);font-size:12px;line-height:17px}.agent-actions{display:grid;align-content:start;height:100%;min-height:0;max-height:none;gap:12px;padding:18px;overflow-y:auto;overscroll-behavior:contain;background:var(--color-bg-canvas);scrollbar-gutter:stable}.agent-actions>header{display:flex;align-items:flex-start;justify-content:space-between;gap:12px}.agent-actions h3{margin:0;color:var(--color-text-primary);font-size:18px;line-height:26px}.agent-actions header p{margin:2px 0 0;color:var(--color-text-muted);font-size:13px}.agent-actions>header>span{padding:5px 8px;color:var(--color-ai);border-radius:var(--radius-pill);background:var(--color-ai-soft);font-size:12px;font-weight:600}.action-card{display:grid;gap:12px;padding:14px;border:1px solid var(--color-border);border-radius:var(--radius-card);background:var(--color-surface);box-shadow:var(--shadow-card)}.action-card>header{display:flex;align-items:center;justify-content:space-between;gap:10px}.action-card>header small{color:var(--color-text-muted)}.action-card dl{display:grid;gap:0;margin:0}.action-card dl div{display:grid;grid-template-columns:minmax(100px,.7fr) minmax(0,1fr);gap:10px;padding:8px 0;border-top:1px solid var(--color-border-subtle)}.action-card dt{color:var(--color-text-muted);font-size:12px;text-transform:capitalize}.action-card dd{margin:0;overflow-wrap:anywhere;color:var(--color-text-secondary);font-size:13px}.agent-actions-empty{margin:auto;color:var(--color-text-muted);font-size:14px}.button-row{display:flex;gap:8px}.button-row button{min-height:38px}.button-row button:first-child{background:var(--color-ai)}@keyframes agent-pulse{0%,100%{opacity:.35;transform:translateY(0)}50%{opacity:1;transform:translateY(-2px)}}@media(max-width:640px){.agent-sidebar,.agent-sidebar.is-wide{width:100vw}.agent-expand{display:none}.agent-sidebar-head{padding-inline:14px}.agent-toolbar{padding-inline:14px}.agent-context-chip{max-width:48%}.agent-messages{padding:16px 14px}.agent-message{max-width:94%}.agent-composer{padding-inline:14px}}@media(prefers-reduced-motion:reduce){.agent-sidebar,.agent-starters button{transition:none}.agent-thinking span{animation:none}}
</style>
