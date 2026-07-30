<script setup lang="ts">
import { computed, onMounted, ref } from "vue";

import UiBadge from "../components/ui/UiBadge.vue";
import UiEmptyState from "../components/ui/UiEmptyState.vue";
import UiTabs from "../components/ui/UiTabs.vue";
import { statusMeta } from "../design-system/statusDictionary";
import { crmStore } from "../stores/crm";
import type { AgentContext, KnowledgeDocument } from "../types";

const activeTab = ref<"chat" | "documents" | "collections" | "agents" | "settings">("chat");
const brainTabs = [
  { value: "chat", label: "Чат с базой знаний" },
  { value: "documents", label: "Документы" },
  { value: "collections", label: "Коллекции" },
  { value: "agents", label: "AI-агенты" },
  { value: "settings", label: "Настройки" }
];
const uploadInput = ref<HTMLInputElement | null>(null);
const uploadFile = ref<File | null>(null);
const uploadTitle = ref("");
const uploadInProgress = ref(false);
const uploadReady = ref(false);
const selectedDocumentId = ref("");

const suggestedQuestions = [
  "Как мы квалифицируем лиды?",
  "Где хранятся цены?",
  "Объясни процесс адаптации.",
  "Как мы работаем с крупными клиентами?",
  "Покажи правила компании.",
  "Найди шаблон договора."
];

const relatedKnowledge = [
  { title: "Квалификация лидов", children: ["Сценарий продаж", "Цены", "Исследование", "Предложение"] },
  { title: "Продажи крупным клиентам", children: ["Проверка безопасности", "Участники", "Коммерческие условия"] }
];

const knowledgeHistory = computed(() => crmStore.agentHistory.value.slice(-20));

function askSuggested(question: string) {
  crmStore.knowledgeAskForm.value.question = question;
  void askCurrentKnowledge();
}

function retrievalLabel(method?: string) {
  if (method === "hybrid") return "Гибридный поиск";
  if (method === "lexical") return "По тексту";
  return "По смыслу";
}

async function askCurrentKnowledge() {
  const document = crmStore.knowledgeDocuments.value.find((item) => item.id === selectedDocumentId.value);
  return crmStore.askKnowledge(document
    ? {
        scope: document.visibility as "global" | "company" | "deal",
        company_id: document.company_id ?? undefined,
        deal_id: document.deal_id ?? undefined,
        document_id: document.id
      }
    : { scope: "global" });
}

function askAboutDocument(document: KnowledgeDocument) {
  selectedDocumentId.value = document.id;
  crmStore.openAgent(
    {
      type: "document",
      document_id: document.id,
      company_id: document.company_id ?? null,
      deal_id: document.deal_id ?? null
    },
    `Что важно знать из документа «${document.title}»?`
  );
}

function openCitation(documentId: string) {
  const document = crmStore.knowledgeDocuments.value.find((item) => item.id === documentId);
  if (document) void crmStore.downloadKnowledgeDocument(document);
}

function contextLabel(context: AgentContext) {
  if (context.type === "document") {
    return crmStore.knowledgeDocuments.value.find((item) => item.id === context.document_id)?.title ?? "Документ";
  }
  if (context.type === "deal") {
    return crmStore.deals.value.find((item) => item.id === context.deal_id)?.title ?? "Сделка";
  }
  if (context.type === "company") {
    return crmStore.companies.value.find((item) => item.id === context.company_id)?.name ?? "Компания";
  }
  return context.type === "knowledge" ? "База знаний" : "Вся CRM";
}

function selectUpload(event: Event) {
  uploadFile.value = (event.target as HTMLInputElement).files?.[0] ?? null;
}

async function uploadKnowledgeFile() {
  if (!uploadFile.value) return;
  uploadInProgress.value = true;
  try {
    const succeeded = await crmStore.uploadKnowledgeDocument(uploadFile.value, {
      title: uploadTitle.value,
      scope: "global"
    });
    if (succeeded) {
      uploadFile.value = null;
      uploadTitle.value = "";
      if (uploadInput.value) uploadInput.value.value = "";
      uploadReady.value = true;
    }
  } finally {
    uploadInProgress.value = false;
  }
}

onMounted(() => {
  void Promise.all([crmStore.refreshKnowledge(), crmStore.refreshAgent()]);
});
</script>

<template>
  <section class="brain-page">
    <UiTabs v-model="activeTab" class="brain-tabs" :items="brainTabs" label="Разделы базы знаний" />

    <section v-if="activeTab === 'chat'" class="brain-chat-layout">
      <div class="brain-main">
        <section class="brain-ask">
          <p class="eyebrow">База знаний</p>
          <h2>Добрый день, Дмитрий.</h2>
          <p>Что вы хотите узнать?</p>

          <label class="brain-context">
            Искать в
            <select v-model="selectedDocumentId">
              <option value="">Вся база знаний</option>
              <option v-for="document in crmStore.knowledgeDocuments.value" :key="document.id" :value="document.id">{{ document.title }}</option>
            </select>
          </label>

          <form class="brain-question" @submit.prevent="askCurrentKnowledge">
            <textarea
              v-model="crmStore.knowledgeAskForm.value.question"
              rows="3"
              placeholder="Спросите о продажах, правилах, ценах или договорах..."
            ></textarea>
            <button type="submit">Спросить</button>
          </form>

          <div class="suggested-grid" aria-label="Предлагаемые вопросы">
            <button v-for="question in suggestedQuestions" :key="question" type="button" @click="askSuggested(question)">
              {{ question }}
            </button>
          </div>
        </section>

        <section v-if="knowledgeHistory.length" class="panel brain-answer">
          <div class="brain-answer-head">
            <div>
              <p class="eyebrow">Единая история</p>
              <h2>Диалог с AI-помощником</h2>
            </div>
            <UiBadge tone="info">{{ knowledgeHistory.length }} сообщений</UiBadge>
          </div>

          <article v-for="message in knowledgeHistory" :key="message.id" class="brain-history-message" :class="message.role">
            <header>
              <strong>{{ message.role === "user" ? "Вы" : "AI-помощник" }}</strong>
              <small>{{ contextLabel(message.context) }}</small>
            </header>
            <p>{{ message.content }}</p>
            <div v-if="message.sources.length" class="source-list">
              <article v-for="citation in message.sources" :key="citation.chunk_id" class="brain-source">
                <div>
                  <strong>{{ citation.document_title }}</strong>
                  <small>{{ retrievalLabel(citation.retrieval_method) }}<template v-if="citation.page_number"> · стр. {{ citation.page_number }}</template></small>
                </div>
                <p>{{ citation.text }}</p>
                <button type="button" class="secondary" @click="openCitation(citation.document_id)">Открыть</button>
              </article>
            </div>
            <div v-if="message.role === 'assistant' && message.query_id" class="agent-feedback">
              <span>Ответ полезен?</span>
              <button type="button" class="secondary" @click="crmStore.sendAgentFeedback(message.query_id, 'up')">Да</button>
              <button type="button" class="secondary" @click="crmStore.sendAgentFeedback(message.query_id, 'down')">Нет</button>
            </div>
          </article>
        </section>
      </div>

      <aside class="brain-rail">
        <section class="panel compact-panel">
          <h2>Связанные знания</h2>
          <div v-for="group in relatedKnowledge" :key="group.title" class="knowledge-branch">
            <strong>{{ group.title }}</strong>
            <span v-for="child in group.children" :key="child">{{ child }}</span>
          </div>
        </section>

        <section class="panel compact-panel">
          <h2>Документы</h2>
          <div v-for="document in crmStore.knowledgeDocuments.value.slice(0, 4)" :key="document.id" class="document-mini-row">
            <div>
              <strong>{{ document.title }}</strong>
              <small>Фрагментов: {{ document.chunks_count }}</small>
            </div>
            <UiBadge :tone="statusMeta(document.status, 'document').tone">{{ statusMeta(document.status, "document").label }}</UiBadge>
          </div>
          <p v-if="!crmStore.knowledgeDocuments.value.length" class="empty">Документы пока не подключены.</p>
        </section>
      </aside>
    </section>

    <section v-else-if="activeTab === 'documents'" class="documents-workspace">
      <section class="panel">
        <div class="panel-head">
          <div>
            <p class="eyebrow">Память рабочего пространства</p>
            <h2>Документы</h2>
          </div>
          <button type="button" @click="uploadInput?.click()">Загрузить файл</button>
        </div>

        <form class="document-upload-form" @submit.prevent="uploadKnowledgeFile">
          <label class="wide-field">
            PDF, DOCX or TXT
            <input ref="uploadInput" type="file" accept=".pdf,.docx,.txt" required @change="selectUpload" />
          </label>
          <label>Название, необязательно<input v-model="uploadTitle" placeholder="По умолчанию — имя файла" /></label>
          <button type="submit" :disabled="!uploadFile || uploadInProgress">
            {{ uploadInProgress ? "Обработка и индексация…" : "Загрузить и проиндексировать" }}
          </button>
        </form>
        <div v-if="uploadReady" class="knowledge-upload-ready">
          <span>Документ проиндексирован. Можно задавать вопросы.</span>
          <button type="button" @click="activeTab = 'chat'">Перейти к вопросам</button>
        </div>

        <form class="document-upload-form" @submit.prevent="crmStore.createKnowledgeDocument">
          <h3 class="wide-field">Или добавьте текст</h3>
          <label>Название<input v-model="crmStore.knowledgeDocumentForm.value.title" required /></label>
          <label>Коллекция<input v-model="crmStore.knowledgeDocumentForm.value.source_type" /></label>
          <label class="wide-field">Содержание<textarea v-model="crmStore.knowledgeDocumentForm.value.text" class="large-textarea" required></textarea></label>
          <button type="submit">Добавить документ</button>
        </form>
      </section>

      <section class="panel">
        <article v-for="document in crmStore.knowledgeDocuments.value" :key="document.id" class="document-row">
          <div>
            <strong>{{ document.title }}</strong>
            <small>Фрагментов: {{ document.chunks_count }} · обновлено {{ new Date(document.created_at).toLocaleDateString("ru-RU") }}</small>
          </div>
          <div>
            <button v-if="document.download_url" type="button" class="secondary" @click="crmStore.downloadKnowledgeDocument(document)">Скачать</button>
            <button type="button" class="secondary" @click="askAboutDocument(document)">Задать вопрос</button>
            <UiBadge :tone="statusMeta(document.status, 'document').tone">{{ statusMeta(document.status, "document").label }}</UiBadge>
          </div>
        </article>
        <UiEmptyState v-if="!crmStore.knowledgeDocuments.value.length" title="Документов пока нет" description="Загрузите файл или добавьте текст, чтобы AI мог отвечать по материалам компании." icon="knowledge">
          <template #actions><button type="button" @click="uploadInput?.click()">Загрузить документ</button></template>
        </UiEmptyState>
      </section>
    </section>

    <section v-else class="panel brain-placeholder">
      <p class="eyebrow">{{ activeTab }}</p>
      <h2>{{ activeTab === "collections" ? "Коллекции" : activeTab === "agents" ? "AI-агенты" : "Настройки" }}</h2>
      <p class="hint">Раздел находится в разработке.</p>
    </section>
  </section>
</template>

<style scoped>
.brain-context { display:grid; gap:6px; margin:18px 0 10px; color:var(--text-muted); font-size:12px; }
.brain-context select { min-height:40px; border:1px solid var(--line); border-radius:10px; padding:0 10px; background:var(--surface-solid); color:var(--text); }
.knowledge-upload-ready { display:flex; align-items:center; justify-content:space-between; gap:12px; margin:12px 0; border:1px solid var(--success); border-radius:10px; padding:10px 12px; background:color-mix(in srgb, var(--success) 8%, transparent); }
.agent-feedback { display:flex; align-items:center; gap:8px; margin-top:14px; color:var(--text-muted); font-size:12px; }
.brain-history-message { display:grid; gap:8px; margin-top:12px; border:1px solid var(--line); border-radius:12px; padding:12px; }
.brain-history-message.user { margin-left:12%; background:var(--surface-muted); }
.brain-history-message header { display:flex; justify-content:space-between; gap:12px; }
.brain-history-message header small { color:var(--text-muted); }
.brain-history-message > p { margin:0; white-space:pre-wrap; }
</style>
