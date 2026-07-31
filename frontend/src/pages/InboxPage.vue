<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import NotificationInbox from "../components/crm/NotificationInbox.vue";
import UiBadge from "../components/ui/UiBadge.vue";
import UiButton from "../components/ui/UiButton.vue";
import UiEmptyState from "../components/ui/UiEmptyState.vue";
import UiIcon from "../components/ui/UiIcon.vue";
import UiInput from "../components/ui/UiInput.vue";
import UiSelect from "../components/ui/UiSelect.vue";
import { statusLabel, statusTone } from "../design-system/statusDictionary";
import { crmStore } from "../stores/crm";

const route = useRoute();
const router = useRouter();
const activeSection = ref<"communications" | "notifications">(
  route.query.tab === "notifications" ? "notifications" : "communications"
);

const loading = ref(true);
const query = ref("");
const channelFilter = ref("");
const statusFilter = ref("");
const selectedId = ref("");
const composerOpen = ref(false);
const visibleEvents = computed(() => crmStore.communicationEvents.value.filter((event) => {
  const needle = query.value.trim().toLowerCase();
  if (channelFilter.value && event.channel !== channelFilter.value) return false;
  if (statusFilter.value && event.status !== statusFilter.value) return false;
  return !needle || [event.subject, event.sender, event.body].some((value) => String(value ?? "").toLowerCase().includes(needle));
}));
const selectedEvent = computed(() => visibleEvents.value.find((event) => event.id === selectedId.value) ?? visibleEvents.value[0] ?? null);
const unreadCount = computed(() => crmStore.communicationEvents.value.filter((event) => ["new", "received", "unread"].includes(event.status)).length);
const failedRuns = computed(() => crmStore.connectorRuns.value.filter((run) => ["failed", "retry_scheduled"].includes(run.status)).length);

watch(visibleEvents, (events) => {
  if (!events.some((event) => event.id === selectedId.value)) selectedId.value = events[0]?.id ?? "";
}, { immediate: true });
watch(() => route.query.tab, (tab) => {
  activeSection.value = tab === "notifications" ? "notifications" : "communications";
});

onMounted(async () => {
  try {
    await Promise.allSettled([
      crmStore.refreshAll(),
      crmStore.refreshActivities(),
      crmStore.refreshCommunication(),
      crmStore.refreshConnectors()
    ]);
  } finally {
    loading.value = false;
  }
});

async function createEvent() {
  await crmStore.createCommunicationEvent();
  composerOpen.value = false;
}

function setSection(section: "communications" | "notifications") {
  activeSection.value = section;
  void router.replace({ path: "/inbox", query: section === "notifications" ? { tab: "notifications" } : {} });
}
</script>

<template>
  <section class="inbox-page">
    <header class="inbox-hero">
      <div><p class="eyebrow">Единый центр событий</p><h2>Входящие</h2><p>{{ activeSection === "communications" ? "Разберите сообщения, свяжите их с CRM и превратите в следующий шаг." : "Контролируйте персональные события CRM, задач и автоматизации." }}</p></div>
      <div v-if="activeSection === 'communications'" class="inbox-actions"><UiButton variant="secondary" icon="refresh" :loading="loading" @click="crmStore.refreshCommunication">Обновить</UiButton><UiButton icon="plus" @click="composerOpen = !composerOpen">Добавить событие</UiButton></div>
    </header>

    <nav class="inbox-tabs" aria-label="Разделы входящих"><button type="button" :class="{ active: activeSection === 'communications' }" @click="setSection('communications')">Коммуникации</button><button type="button" :class="{ active: activeSection === 'notifications' }" @click="setSection('notifications')">Уведомления</button></nav>

    <template v-if="activeSection === 'communications'">
    <section class="inbox-summary">
      <article><UiIcon name="inbox" :size="20" /><div><strong>{{ unreadCount }}</strong><span>Требуют разбора</span></div></article>
      <article><UiIcon name="check" :size="20" /><div><strong>{{ crmStore.communicationEvents.value.length - unreadCount }}</strong><span>Обработаны</span></div></article>
      <article :class="{ warning: failedRuns }"><UiIcon name="refresh" :size="20" /><div><strong>{{ failedRuns }}</strong><span>Ошибки синхронизации</span></div></article>
    </section>

    <form v-if="composerOpen" class="inbox-composer" @submit.prevent="createEvent">
      <header><div><strong>Новое входящее событие</strong><small>Для ручной фиксации звонка, письма или встречи</small></div><button class="secondary" type="button" aria-label="Закрыть" @click="composerOpen = false"><UiIcon name="close" :size="16" /></button></header>
      <UiSelect v-model="crmStore.communicationEventForm.value.channel" label="Канал"><option value="email">Email</option><option value="call">Звонок</option><option value="calendar">Встреча</option><option value="telegram">Telegram</option><option value="whatsapp">WhatsApp</option></UiSelect>
      <UiSelect v-model="crmStore.communicationEventForm.value.company_id" label="Компания"><option value="">Без компании</option><option v-for="company in crmStore.companies.value" :key="company.id" :value="company.id">{{ company.name }}</option></UiSelect>
      <UiInput v-model="crmStore.communicationEventForm.value.sender" label="Отправитель" />
      <UiInput v-model="crmStore.communicationEventForm.value.subject" label="Тема" required />
      <label class="body-field">Сообщение<textarea v-model="crmStore.communicationEventForm.value.body" rows="3"></textarea></label>
      <UiButton type="submit">Добавить во входящие</UiButton>
    </form>

    <section class="inbox-workspace">
      <aside class="inbox-list">
        <header class="inbox-filters">
          <UiInput v-model="query" type="search" placeholder="Поиск сообщений" />
          <div><UiSelect v-model="channelFilter"><option value="">Все каналы</option><option value="email">Email</option><option value="call">Звонки</option><option value="calendar">Встречи</option><option value="telegram">Telegram</option><option value="whatsapp">WhatsApp</option></UiSelect><UiSelect v-model="statusFilter"><option value="">Все статусы</option><option value="new">Не разобрано</option><option value="linked">Привязано</option><option value="activity_created">Активность</option></UiSelect></div>
        </header>
        <div v-if="loading" class="inbox-skeleton"><span v-for="index in 5" :key="index"></span></div>
        <button v-for="event in visibleEvents" v-else :key="event.id" type="button" class="message-row" :class="{ active: selectedEvent?.id === event.id }" @click="selectedId = event.id">
          <span class="channel-icon"><UiIcon :name="event.channel === 'call' ? 'phone' : event.channel === 'calendar' ? 'calendar' : 'mail'" :size="17" /></span>
          <span class="message-copy"><strong>{{ event.subject }}</strong><small>{{ event.sender || "Неизвестный отправитель" }}</small><small>{{ event.body || "Без текста" }}</small></span>
          <time>{{ new Date(event.occurred_at).toLocaleDateString("ru-RU", { day: "2-digit", month: "short" }) }}</time>
        </button>
        <UiEmptyState v-if="!loading && !visibleEvents.length" compact title="Сообщений нет" description="Новые коммуникации появятся после синхронизации." icon="inbox" />
      </aside>

      <article v-if="selectedEvent" class="message-detail">
        <header><div><p class="eyebrow">{{ selectedEvent.channel }}</p><h3>{{ selectedEvent.subject }}</h3><p>{{ selectedEvent.sender || "Отправитель неизвестен" }} · {{ new Date(selectedEvent.occurred_at).toLocaleString("ru-RU") }}</p></div><UiBadge :tone="statusTone(selectedEvent.status, 'communication')">{{ statusLabel(selectedEvent.status, "communication") }}</UiBadge></header>
        <div class="message-body">{{ selectedEvent.body || "Текст сообщения отсутствует." }}</div>
        <section class="link-card">
          <div><strong>Связать с CRM</strong><small>Контекст будет доступен в компании, контакте и сделке.</small></div>
          <div class="link-fields">
            <UiSelect v-model="selectedEvent.company_id" label="Компания"><option :value="null">Без компании</option><option v-for="company in crmStore.companies.value" :key="company.id" :value="company.id">{{ company.name }}</option></UiSelect>
            <UiSelect v-model="selectedEvent.contact_id" label="Контакт"><option :value="null">Без контакта</option><option v-for="contact in crmStore.contacts.value.filter((item) => !selectedEvent?.company_id || item.company_id === selectedEvent.company_id)" :key="contact.id" :value="contact.id">{{ contact.name }}</option></UiSelect>
            <UiSelect v-model="selectedEvent.deal_id" label="Сделка"><option :value="null">Без сделки</option><option v-for="deal in crmStore.deals.value.filter((item) => !selectedEvent?.company_id || item.company_id === selectedEvent.company_id)" :key="deal.id" :value="deal.id">{{ deal.title }}</option></UiSelect>
          </div>
          <div class="detail-actions"><UiButton variant="secondary" @click="crmStore.linkCommunicationEvent(selectedEvent)">Сохранить привязку</UiButton><UiButton :disabled="!selectedEvent.company_id || Boolean(selectedEvent.activity_id)" @click="crmStore.createActivityFromCommunication(selectedEvent.id)">{{ selectedEvent.activity_id ? "Активность создана" : "Создать активность" }}</UiButton></div>
        </section>
      </article>
      <UiEmptyState v-else title="Выберите сообщение" description="Здесь появятся содержание и действия по коммуникации." icon="mail" />
    </section>
    </template>
    <NotificationInbox v-else />
  </section>
</template>

<style scoped>
.inbox-page{display:grid;gap:16px}.inbox-hero{display:flex;align-items:flex-end;justify-content:space-between;gap:20px}.inbox-hero h2{margin:4px 0 6px;font-size:28px}.inbox-hero p:last-child{margin:0;color:var(--color-text-muted)}.inbox-actions{display:flex;gap:8px}.inbox-tabs{display:flex;gap:4px;border:1px solid var(--color-border);border-radius:var(--radius-card);padding:4px;background:var(--color-surface)}.inbox-tabs button{flex:1;min-height:38px;color:var(--color-text-muted);background:transparent}.inbox-tabs button.active{color:var(--color-text-primary);background:var(--color-primary-soft);box-shadow:inset 0 0 0 1px var(--color-primary)}.inbox-summary{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}.inbox-summary article{display:flex;align-items:center;gap:12px;border:1px solid var(--color-border);border-radius:var(--radius-card);padding:14px 16px;background:var(--color-surface)}.inbox-summary article>svg{color:var(--color-primary)}.inbox-summary article.warning>svg{color:var(--color-warning)}.inbox-summary article div{display:grid}.inbox-summary strong{font-size:22px}.inbox-summary span{color:var(--color-text-muted);font-size:var(--font-size-meta)}.inbox-composer{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;border:1px solid var(--color-border);border-radius:var(--radius-panel);padding:16px;background:var(--color-surface)}.inbox-composer header{grid-column:1/-1;display:flex;justify-content:space-between}.inbox-composer header div{display:grid}.inbox-composer header small{color:var(--color-text-muted)}.body-field{grid-column:1/-1}.inbox-composer>button:last-child{grid-column:4}.inbox-workspace{display:grid;grid-template-columns:minmax(320px,390px) minmax(0,1fr);min-height:610px;overflow:hidden;border:1px solid var(--color-border);border-radius:var(--radius-panel);background:var(--color-surface)}.inbox-list{overflow:auto;border-right:1px solid var(--color-border)}.inbox-filters{position:sticky;top:0;z-index:2;display:grid;gap:8px;border-bottom:1px solid var(--color-border);padding:12px;background:var(--color-surface)}.inbox-filters>div{display:grid;grid-template-columns:1fr 1fr;gap:6px}.message-row{width:100%;display:grid;grid-template-columns:36px minmax(0,1fr) auto;align-items:start;gap:10px;min-height:92px;border:0;border-bottom:1px solid var(--color-border-subtle);border-radius:0;padding:13px;color:var(--color-text-primary);background:var(--color-surface);box-shadow:none;text-align:left}.message-row:hover,.message-row.active{background:var(--color-primary-soft)}.message-row.active{box-shadow:inset 3px 0 var(--color-primary)}.channel-icon{display:grid;place-items:center;width:34px;height:34px;border-radius:var(--radius-control);color:var(--color-primary);background:var(--color-surface)}.message-copy{display:grid;gap:2px;overflow:hidden}.message-copy strong,.message-copy small{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.message-copy small{color:var(--color-text-muted);font-size:var(--font-size-meta)}.message-row time{color:var(--color-text-muted);font-size:var(--font-size-caption)}.message-detail{display:grid;align-content:start;gap:24px;padding:24px}.message-detail>header{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;border-bottom:1px solid var(--color-border-subtle);padding-bottom:18px}.message-detail h3{margin:4px 0 6px;font-size:24px}.message-detail header p:last-child{margin:0;color:var(--color-text-muted);font-size:var(--font-size-meta)}.message-body{min-height:150px;white-space:pre-wrap}.link-card{display:grid;gap:14px;border:1px solid var(--color-border);border-radius:var(--radius-card);padding:16px;background:var(--color-surface-subtle)}.link-card>div:first-child{display:grid}.link-card small{color:var(--color-text-muted)}.link-fields{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}.detail-actions{display:flex;justify-content:flex-end;gap:8px}.inbox-skeleton{display:grid}.inbox-skeleton span{height:92px;border-bottom:1px solid var(--color-border-subtle);background:linear-gradient(90deg,var(--color-surface),var(--color-surface-muted),var(--color-surface));background-size:200% 100%;animation:pulse 1.2s infinite}@keyframes pulse{to{background-position:-200% 0}}
@media(max-width:900px){.inbox-workspace{grid-template-columns:1fr}.inbox-list{border-right:0}.message-detail{border-top:1px solid var(--color-border)}}
@media(max-width:640px){.inbox-hero{align-items:flex-start;flex-direction:column}.inbox-actions{width:100%}.inbox-actions>*{flex:1}.inbox-summary{grid-template-columns:1fr}.inbox-composer{grid-template-columns:1fr}.inbox-composer>*{grid-column:1!important}.inbox-workspace{min-height:0}.link-fields{grid-template-columns:1fr}.detail-actions{flex-direction:column}.message-detail{padding:18px 14px}}
</style>
