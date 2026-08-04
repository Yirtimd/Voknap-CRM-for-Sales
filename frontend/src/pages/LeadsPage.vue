<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import EntityCrudDrawer from "../components/crm/EntityCrudDrawer.vue";
import CustomFieldFilter from "../components/crm/CustomFieldFilter.vue";
import UiBadge from "../components/ui/UiBadge.vue";
import UiButton from "../components/ui/UiButton.vue";
import UiEmptyState from "../components/ui/UiEmptyState.vue";
import UiIcon from "../components/ui/UiIcon.vue";
import UiInput from "../components/ui/UiInput.vue";
import UiSelect from "../components/ui/UiSelect.vue";
import UiSkeletonGroup from "../components/ui/UiSkeletonGroup.vue";
import { statusLabel, statusTone } from "../design-system/statusDictionary";
import { crmStore } from "../stores/crm";
import type { Contact, EntityType, Lead, Note } from "../types";

const route = useRoute();
const router = useRouter();

const loading = ref(true);
const query = ref("");
const statusFilter = ref("");
const activeList = ref<"leads" | "contacts">("leads");
const customFieldIds = ref<string[] | null>(null);

const crudType = ref<EntityType | null>(null);
const crudRecord = ref<Contact | Lead | Note | null>(null);
const crudMode = ref<"view" | "edit" | "create">("view");
const crudInitialValues = ref<Record<string, unknown>>({});
const filteredLeads = computed(() => crmStore.leads.value.filter((lead) => {
  const needle = query.value.trim().toLowerCase();
  return (!customFieldIds.value || customFieldIds.value.includes(lead.id))
    && (!statusFilter.value || lead.status === statusFilter.value)
    && (!needle || [lead.title, lead.source, companyName(lead.company_id)].some((value) => String(value ?? "").toLowerCase().includes(needle)));
}));
const filteredContacts = computed(() => crmStore.contacts.value.filter((contact) => {
  const needle = query.value.trim().toLowerCase();
  return (!customFieldIds.value || customFieldIds.value.includes(contact.id)) && (!needle || [contact.name, contact.email, contact.phone, contact.company_name].some((value) => String(value ?? "").toLowerCase().includes(needle)));
}));
const leadStatuses = computed(() => [...new Set(crmStore.leads.value.map((lead) => lead.status))]);
const convertedCount = computed(() => crmStore.leads.value.filter((lead) => ["converted", "qualified"].includes(lead.status)).length);
const hotLeadCount = computed(() => crmStore.leads.value.filter((lead) => (lead.score ?? 0) >= 75).length);

onMounted(async () => {
  try {
    await crmStore.refreshAll();
    openFromRoute();
  } catch {
    // Global workspace alert renders the store error.
  } finally {
    loading.value = false;
  }
});

function openCrud(type: "contacts" | "leads" | "notes", record: Contact | Lead | Note | null = null, mode: "view" | "edit" | "create" = record ? "view" : "create", initialValues: Record<string, unknown> = {}) {
  crudType.value = type;
  crudRecord.value = record;
  crudMode.value = mode;
  crudInitialValues.value = initialValues;
}

function openFromRoute() {
  const leadId = typeof route.query.record === "string" ? route.query.record : "";
  const contactId = typeof route.query.contact === "string" ? route.query.contact : "";
  const lead = crmStore.leads.value.find((item) => item.id === leadId);
  const contact = crmStore.contacts.value.find((item) => item.id === contactId);
  if (lead) openCrud("leads", lead);
  else if (contact) openCrud("contacts", contact);
}

function closeCrud() {
  crudType.value = null;
  crudRecord.value = null;
  crudInitialValues.value = {};
  if (route.query.record || route.query.contact) void router.replace({ query: { ...route.query, record: undefined, contact: undefined } });
}

watch(() => [route.query.record, route.query.contact], openFromRoute);

function companyName(companyId: string) {
  return crmStore.companies.value.find((company) => company.id === companyId)?.name ?? "Компания";
}

function scoreLabel(lead: Lead) {
  return lead.score === null || lead.score === undefined ? "Не рассчитан" : `${lead.score}/100`;
}
</script>

<template>
  <section class="leads-page">
    <section class="leads-hero">
      <div><p class="eyebrow">Верх воронки</p><h2>Лиды и контакты</h2><p>Квалифицируйте входящие обращения и сохраняйте контекст до создания сделки.</p></div>
      <div class="leads-actions">
        <RouterLink class="button-link secondary-link" to="/inbox"><UiIcon name="inbox" :size="16" /> Входящие</RouterLink>
        <UiButton icon="plus" @click="openCrud('leads')">Новый лид</UiButton>
      </div>
    </section>

    <section class="leads-metrics" aria-label="Сводка">
      <article><span>Всего лидов</span><strong>{{ crmStore.leads.value.length }}</strong><small>В активной базе</small></article>
      <article><span>Квалифицированы</span><strong>{{ convertedCount }}</strong><small>Готовы к сделке</small></article>
      <article><span>Горячие лиды</span><strong>{{ hotLeadCount }}</strong><small>Lead score от 75</small></article>
    </section>

    <section class="leads-workspace">
      <header class="leads-toolbar">
        <div class="leads-tabs">
          <button type="button" :class="{ active: activeList === 'leads' }" @click="activeList = 'leads'">Лиды <b>{{ crmStore.leads.value.length }}</b></button>
          <button type="button" :class="{ active: activeList === 'contacts' }" @click="activeList = 'contacts'">Контакты <b>{{ crmStore.contacts.value.length }}</b></button>
        </div>
        <div class="leads-filters">
          <UiInput v-model="query" type="search" placeholder="Поиск по названию, компании или контакту" />
          <UiSelect v-if="activeList === 'leads'" v-model="statusFilter">
            <option value="">Все статусы</option>
            <option v-for="status in leadStatuses" :key="status" :value="status">{{ statusLabel(status, "lead") }}</option>
          </UiSelect>
          <UiButton v-else variant="secondary" icon="plus" @click="openCrud('contacts')">Контакт</UiButton>
        </div>
      </header>

      <UiSkeletonGroup v-if="loading" :rows="3" avatar />
      <CustomFieldFilter :key="activeList" :entity-type="activeList" @change="customFieldIds = $event" />
      <template v-if="activeList === 'leads'">
        <button v-for="lead in filteredLeads" :key="lead.id" class="lead-row" type="button" @click="openCrud('leads', lead)">
          <span class="lead-avatar">{{ lead.title.slice(0, 2).toUpperCase() }}</span>
          <span class="lead-main"><strong>{{ lead.title }}</strong><small>{{ companyName(lead.company_id) }} · {{ lead.source ?? "Источник не указан" }}</small></span>
          <span class="lead-score" :class="lead.score_grade ?? 'cold'">{{ scoreLabel(lead) }}</span>
          <UiBadge :tone="statusTone(lead.status, 'lead')">{{ statusLabel(lead.status, "lead") }}</UiBadge>
          <span class="row-action">Открыть <UiIcon name="chevronRight" :size="16" /></span>
        </button>
        <UiEmptyState v-if="!filteredLeads.length" title="Лиды не найдены" description="Измените фильтры или добавьте первое обращение." icon="leads">
          <template #actions><UiButton icon="plus" @click="openCrud('leads')">Добавить лид</UiButton></template>
        </UiEmptyState>
      </template>
      <template v-else>
        <button v-for="contact in filteredContacts" :key="contact.id" class="lead-row" type="button" @click="openCrud('contacts', contact)">
          <span class="lead-avatar contact">{{ contact.name.slice(0, 2).toUpperCase() }}</span>
          <span class="lead-main"><strong>{{ contact.name }}</strong><small>{{ contact.company_name || companyName(contact.company_id) }} · {{ contact.email || contact.phone || "Контакты не указаны" }}</small></span>
          <span class="row-action">Открыть <UiIcon name="chevronRight" :size="16" /></span>
        </button>
        <UiEmptyState v-if="!filteredContacts.length" title="Контакты не найдены" description="Добавьте контакт или измените запрос." icon="team">
          <template #actions><UiButton icon="plus" @click="openCrud('contacts')">Добавить контакт</UiButton></template>
        </UiEmptyState>
      </template>
    </section>

    <EntityCrudDrawer v-if="crudType" :entity-type="crudType" :record="crudRecord" :initial-mode="crudMode" :initial-values="crudInitialValues" @close="closeCrud" />
  </section>
</template>

<style scoped>
.leads-page{display:grid;gap:16px}.leads-hero{display:flex;align-items:flex-end;justify-content:space-between;gap:24px;border:1px solid var(--color-border);border-radius:var(--radius-panel);padding:24px;background:linear-gradient(135deg,var(--color-surface),var(--color-primary-soft))}.leads-hero h2{margin:4px 0 8px;font-size:26px}.leads-hero p:last-child{max-width:620px;margin:0;color:var(--color-text-muted)}.leads-actions{display:flex;gap:8px;flex:0 0 auto}.leads-metrics{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}.leads-metrics article{display:grid;gap:4px;border:1px solid var(--color-border);border-radius:var(--radius-card);padding:16px;background:var(--color-surface)}.leads-metrics span,.leads-metrics small{color:var(--color-text-muted);font-size:var(--font-size-meta)}.leads-metrics strong{font-size:28px;line-height:34px}.leads-workspace{overflow:hidden;border:1px solid var(--color-border);border-radius:var(--radius-panel);background:var(--color-surface)}.leads-toolbar{display:flex;align-items:center;justify-content:space-between;gap:16px;border-bottom:1px solid var(--color-border-subtle);padding:14px 16px}.leads-tabs{display:flex;gap:4px}.leads-tabs button{min-height:36px;border:0;border-radius:var(--radius-control);color:var(--color-text-muted);background:transparent;box-shadow:none}.leads-tabs button.active{color:var(--color-primary);background:var(--color-primary-soft)}.leads-tabs b{margin-left:5px}.leads-filters{display:grid;grid-template-columns:minmax(260px,1fr) 180px;gap:8px}.lead-row{width:100%;display:grid;grid-template-columns:42px minmax(0,1fr) auto auto 100px;align-items:center;gap:12px;min-height:72px;border:0;border-bottom:1px solid var(--color-border-subtle);border-radius:0;padding:10px 16px;color:var(--color-text-primary);background:var(--color-surface);box-shadow:none;text-align:left}.lead-row:hover{background:var(--color-surface-subtle)}.lead-avatar{display:grid;place-items:center;width:40px;height:40px;border-radius:var(--radius-control);color:var(--color-primary);background:var(--color-primary-soft);font-size:var(--font-size-meta);font-weight:800}.lead-avatar.contact{color:var(--color-ai);background:var(--color-ai-soft)}.lead-main{display:grid;gap:3px}.lead-main small{overflow:hidden;color:var(--color-text-muted);font-size:var(--font-size-meta);text-overflow:ellipsis;white-space:nowrap}.lead-score{border-radius:999px;padding:5px 8px;color:var(--color-text-muted);background:var(--color-surface-muted);font-size:var(--font-size-meta);font-weight:800}.lead-score.hot{color:var(--color-success-text);background:var(--color-success-soft)}.lead-score.warm{color:var(--color-warning-text);background:var(--color-warning-soft)}.row-action{display:flex;align-items:center;justify-content:flex-end;gap:3px;color:var(--color-primary);font-size:var(--font-size-compact);font-weight:700}.leads-loading{display:grid;gap:1px}.leads-loading span{height:72px;background:linear-gradient(90deg,var(--color-surface-subtle),var(--color-surface-muted),var(--color-surface-subtle));background-size:200% 100%;animation:lead-pulse 1.2s infinite}.leads-workspace :deep(.ui-empty){margin:16px}@keyframes lead-pulse{to{background-position:-200% 0}}
@media(max-width:760px){.leads-hero{align-items:flex-start;flex-direction:column}.leads-actions{width:100%}.leads-actions>*{flex:1}.leads-metrics{grid-template-columns:1fr}.leads-toolbar{align-items:stretch;flex-direction:column}.leads-filters{grid-template-columns:1fr}.lead-row{grid-template-columns:42px minmax(0,1fr) auto}.lead-row :deep(.ui-badge){grid-column:2}.row-action{grid-column:3;grid-row:1/span 2;font-size:0}}
</style>
