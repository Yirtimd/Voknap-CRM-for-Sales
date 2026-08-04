<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import CompanyDrawer from "../components/crm/CompanyDrawer.vue";
import CustomFieldFilter from "../components/crm/CustomFieldFilter.vue";
import UiIcon from "../components/ui/UiIcon.vue";
import { crmStore } from "../stores/crm";
import type { Company } from "../types";

const query = ref("");
const sort = ref<"health" | "name" | "pipeline">("health");
const selectedCompany = ref<Company | null>(null);
const showCreateCompany = ref(false);
const companyNameInput = ref<HTMLInputElement | null>(null);
const customFieldIds = ref<string[] | null>(null);
const route = useRoute();
const router = useRouter();

function handleEscape(event: KeyboardEvent) {
  if (event.key !== "Escape") return;
  if (showCreateCompany.value) showCreateCompany.value = false;
  else if (selectedCompany.value) closeCompany();
}

onMounted(() => {
  void crmStore.refreshAll();
  window.addEventListener("keydown", handleEscape);
});

onBeforeUnmount(() => {
  window.removeEventListener("keydown", handleEscape);
  document.body.style.overflow = "";
});

watch(showCreateCompany, (open) => {
  document.body.style.overflow = open ? "hidden" : "";
});

watch(
  () => route.query.create,
  (value) => { if (value === "1") openCreateCompany(); },
  { immediate: true }
);

watch(
  [() => route.query.company, () => crmStore.companies.value.length],
  ([companyId]) => {
    if (typeof companyId !== "string" || selectedCompany.value?.id === companyId) return;
    const company = crmStore.companies.value.find((item) => item.id === companyId);
    if (company) void openCompany(company);
  },
  { immediate: true }
);

function closeCompany() {
  selectedCompany.value = null;
  if (route.query.company) void router.replace("/companies");
}

function openCreateCompany() {
  showCreateCompany.value = true;
  requestAnimationFrame(() => companyNameInput.value?.focus());
}

async function createCompany() {
  await crmStore.createCompany();
  if (!crmStore.error.value) showCreateCompany.value = false;
}

function companyDeals(company: Company) {
  return crmStore.deals.value.filter((deal) => deal.company_id === company.id);
}

function companyTasks(company: Company) {
  return crmStore.tasks.value.filter((task) => task.company_id === company.id && !task.done_at);
}

function companyPipeline(company: Company) {
  return companyDeals(company).reduce((sum, deal) => sum + Number(deal.amount ?? 0), 0);
}

function companyHealth(company: Company) {
  return Math.min(98, 58 + companyDeals(company).length * 9 + companyTasks(company).length * 4);
}

function healthTone(company: Company) {
  const health = companyHealth(company);
  if (health >= 60) return "good";
  if (health >= 45) return "warn";
  return "bad";
}

function companyInitial(company: Company) {
  return company.name.trim().slice(0, 1).toUpperCase();
}

function nextAction(company: Company) {
  const action = crmStore.nextActions.value.find(
    (item) => item.company_id === company.id && item.status === "open"
  );
  if (action) return action.title;
  const task = companyTasks(company)[0];
  if (task) return task.title;
  if (!companyDeals(company).length) return "Создать первую сделку";
  return "Запланировать follow-up";
}

async function openCompany(company: Company) {
  selectedCompany.value = company;
  await crmStore.loadCompanyWorkspace(company.id);
  await crmStore.refreshCompanyCopilot(company.id);
}

const filteredCompanies = computed(() => {
  const needle = query.value.trim().toLowerCase();
  const rows = crmStore.companies.value.filter((company) => {
    if (customFieldIds.value && !customFieldIds.value.includes(company.id)) return false;
    if (!needle) return true;
    return [company.name, company.industry, company.website].some((value) => String(value ?? "").toLowerCase().includes(needle));
  });
  return rows.sort((left, right) => {
    if (sort.value === "name") return left.name.localeCompare(right.name);
    if (sort.value === "pipeline") return companyPipeline(right) - companyPipeline(left);
    return companyHealth(right) - companyHealth(left);
  });
});

const totalPipeline = computed(() => filteredCompanies.value.reduce((sum, company) => sum + companyPipeline(company), 0));
const totalDeals = computed(() => filteredCompanies.value.reduce((sum, company) => sum + companyDeals(company).length, 0));
const averageHealth = computed(() => {
  if (!filteredCompanies.value.length) return 0;
  const sum = filteredCompanies.value.reduce((acc, company) => acc + companyHealth(company), 0);
  return Math.round(sum / filteredCompanies.value.length);
});
</script>

<template>
  <section class="companies-workspace">
    <CompanyDrawer
      v-if="selectedCompany"
      :company="selectedCompany"
      :initial-tab="typeof route.query.tab === 'string' ? route.query.tab : undefined"
      embedded
      @close="closeCompany"
    />

    <template v-else>
    <header class="companies-head">
      <p>{{ crmStore.companies.value.length }} компаний в базе</p>
    </header>

    <section class="companies-controls">
      <label class="companies-search">
        <UiIcon name="search" :size="16" />
        <input v-model="query" type="search" placeholder="Поиск компаний..." aria-label="Поиск компаний" />
      </label>
      <label class="companies-filter">
        <UiIcon name="sort" :size="16" />
        <select v-model="sort" aria-label="Сортировка компаний">
          <option value="health">Сначала высокий рейтинг</option>
          <option value="pipeline">Сначала крупный портфель</option>
          <option value="name">По названию</option>
        </select>
      </label>
      <button type="button" class="new-company-button" @click="openCreateCompany"><UiIcon name="plus" :size="16" /> Новая компания</button>
    </section>
    <CustomFieldFilter entity-type="companies" @change="customFieldIds = $event" />

    <section class="companies-metrics">
      <article class="company-metric-card">
        <div><span>Сделки</span><strong>{{ totalDeals }}</strong><small>Открытых сделок</small></div>
        <span class="metric-orb blue"><UiIcon name="deals" :size="20" /></span>
      </article>
      <article class="company-metric-card">
        <div><span>Портфель</span><strong>{{ crmStore.money(totalPipeline) }}</strong><small>Сумма активных сделок</small></div>
        <span class="metric-orb green" aria-hidden="true">₽</span>
      </article>
      <article class="company-metric-card">
        <div><span>Средний рейтинг</span><strong>{{ averageHealth }}</strong><small>Состояние отношений</small></div>
        <span class="metric-orb purple"><UiIcon name="heart" :size="20" /></span>
      </article>
    </section>

    <section class="companies-list">
      <article
        v-for="company in filteredCompanies"
        :key="company.id"
        class="company-list-row clickable-row"
        role="button"
        tabindex="0"
        @click="openCompany(company)"
        @keydown.enter="openCompany(company)"
        @keydown.space.prevent="openCompany(company)"
      >
        <span class="company-avatar" :class="healthTone(company)">{{ companyInitial(company) }}</span>
        <div class="company-main">
          <strong>{{ company.name }}</strong>
          <small>B2B · {{ company.website?.replace("https://", "") ?? "example.com" }}</small>
        </div>
        <div class="health-cell">
          <span>Рейтинг {{ companyHealth(company) }}</span>
          <div class="company-health-line" :class="healthTone(company)">
            <span :style="{ width: `${companyHealth(company)}%` }"></span>
          </div>
        </div>
        <div class="row-stat"><strong>{{ companyDeals(company).length }}</strong><small>Сделки</small></div>
        <div class="row-stat"><strong>{{ companyTasks(company).length }}</strong><small>Задачи</small></div>
        <div class="next-cell">
          <small>Следующий шаг</small>
          <span>{{ nextAction(company) }}</span>
        </div>
      </article>

      <section v-if="!filteredCompanies.length" class="empty-state" aria-live="polite">
        <strong>{{ query ? "Ничего не найдено" : "Компаний пока нет" }}</strong>
        <p>{{ query ? "Измените запрос или сбросьте поиск." : "Добавьте первую компанию, чтобы создать сделку и задачи." }}</p>
        <button v-if="query" type="button" class="secondary" @click="query = ''">Сбросить поиск</button>
        <button v-else type="button" @click="openCreateCompany">Добавить компанию</button>
      </section>
    </section>

    <div v-if="showCreateCompany" class="workspace-modal-backdrop" @click.self="showCreateCompany = false">
      <section class="panel company-create-modal" role="dialog" aria-modal="true" aria-labelledby="new-company-title">
        <header class="panel-head">
          <div><p class="eyebrow">Компания</p><h2 id="new-company-title">Новая компания</h2></div>
          <button class="secondary" type="button" @click="showCreateCompany = false">Закрыть</button>
        </header>
        <form class="compact-form" @submit.prevent="createCompany">
          <label>Название<input ref="companyNameInput" v-model="crmStore.companyForm.value.name" required minlength="2" /></label>
          <label>Сайт<input v-model="crmStore.companyForm.value.website" type="url" placeholder="https://example.ru" /></label>
          <label>Отрасль<input v-model="crmStore.companyForm.value.industry" /></label>
          <label>Описание<textarea v-model="crmStore.companyForm.value.description"></textarea></label>
          <button type="submit" :disabled="crmStore.isLoading.value">Создать</button>
        </form>
      </section>
    </div>

    </template>
  </section>
</template>

<style scoped>
.company-create-modal { width: min(560px, calc(100vw - 32px)); max-height: calc(100vh - 48px); overflow: auto; }
.company-create-modal .panel-head { margin-bottom: 14px; }
.company-create-modal h2 { margin: 0; }
</style>
