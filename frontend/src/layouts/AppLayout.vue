<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import voknapLogo from "../assets/voknap-logo.png";
import voknapLogoDark from "../assets/voknap-logo-dark.png";
import GlobalAgentSidebar from "../components/crm/GlobalAgentSidebar.vue";
import NotificationBell from "../components/crm/NotificationBell.vue";
import UiAlert from "../components/ui/UiAlert.vue";
import UiDensityToggle from "../components/ui/UiDensityToggle.vue";
import UiIcon from "../components/ui/UiIcon.vue";
import UiThemeToggle from "../components/ui/UiThemeToggle.vue";
import type { IconName } from "../components/ui/icons";
import { useDensity } from "../design-system/density";
import { useTheme } from "../design-system/theme";
import { crmStore } from "../stores/crm";
import { notificationStore } from "../stores/notifications";

const router = useRouter();
const route = useRoute();
const { density } = useDensity();
const { theme } = useTheme();

const navGroups: Array<{ label: string; items: Array<{ to: string; label: string; icon: IconName }> }> = [
  { label: "Работа", items: [
    { to: "/home", label: "Главная", icon: "home" },
    { to: "/inbox", label: "Входящие", icon: "inbox" },
    { to: "/tasks", label: "Задачи", icon: "tasks" }
  ] },
  { label: "Продажи", items: [
    { to: "/companies", label: "Компании", icon: "companies" },
    { to: "/leads", label: "Лиды и контакты", icon: "leads" },
    { to: "/deals", label: "Сделки", icon: "deals" }
  ] },
  { label: "Развитие", items: [
    { to: "/analytics", label: "Аналитика", icon: "analytics" },
    { to: "/automation", label: "Автоматизация", icon: "automation" },
    { to: "/knowledge", label: "База знаний", icon: "knowledge" }
  ] },
  { label: "Управление", items: [
    { to: "/team", label: "Команда", icon: "team" },
    { to: "/settings", label: "Настройки", icon: "settings" },
    { to: "/crm/contacts", label: "Архив", icon: "archive" }
  ] }
];
const navItems = navGroups.flatMap((group) => group.items);
const mobilePrimary = navItems.filter((item) => ["/home", "/companies", "/deals", "/tasks"].includes(item.to));

const pageTitle = computed(() => String(route.meta.title ?? "Рабочее пространство"));
const pageEyebrow = computed(() => String(route.meta.eyebrow ?? "CRM"));
const isHome = computed(() => route.path === "/home");
const isTasks = computed(() => route.path === "/tasks");
const isAgentOpen = crmStore.agentPanelOpen;
const isMobileMoreOpen = ref(false);
const sidebarMode = ref<"full" | "compact" | "hidden">(
  (localStorage.getItem("cmr_sidebar_mode") as "full" | "compact" | "hidden" | null) ?? "full"
);
const searchQuery = ref("");
const appearanceMenu = ref<HTMLElement | null>(null);
const activePanel = ref<"search" | "new" | "notifications" | "profile" | "menu" | "appearance" | null>(null);

const searchResults = computed(() => {
  const needle = searchQuery.value.trim().toLowerCase();
  if (needle.length < 2) return [];
  const companies = crmStore.companies.value
    .filter((item) => [item.name, item.industry, item.website].some((value) => String(value ?? "").toLowerCase().includes(needle)))
    .map((item) => ({ id: `company-${item.id}`, type: "Компания", title: item.name, meta: item.industry ?? "Компания", to: `/companies/${item.id}` }));
  const deals = crmStore.deals.value
    .filter((item) => [item.title, item.next_step, item.expected_next_event].some((value) => String(value ?? "").toLowerCase().includes(needle)))
    .map((item) => ({ id: `deal-${item.id}`, type: "Сделка", title: item.title, meta: crmStore.money(item.amount), to: `/deals?deal=${item.id}` }));
  const leads = crmStore.leads.value
    .filter((item) => [item.title, item.source, item.status].some((value) => String(value ?? "").toLowerCase().includes(needle)))
    .map((item) => ({ id: `lead-${item.id}`, type: "Лид", title: item.title, meta: item.source ?? item.status, to: `/leads?record=${item.id}` }));
  const tasks = crmStore.tasks.value
    .filter((item) => [item.title, item.description].some((value) => String(value ?? "").toLowerCase().includes(needle)))
    .map((item) => ({ id: `task-${item.id}`, type: "Задача", title: item.title, meta: item.due_at ? new Date(item.due_at).toLocaleString("ru-RU") : "Без срока", to: `/tasks?record=${item.id}` }));
  const contacts = crmStore.contacts.value
    .filter((item) => [item.name, item.email, item.phone, item.company_name].some((value) => String(value ?? "").toLowerCase().includes(needle)))
    .map((item) => ({ id: `contact-${item.id}`, type: "Контакт", title: item.name, meta: item.company_name ?? item.email ?? "Контакт", to: `/leads?contact=${item.id}` }));
  return [...companies, ...contacts, ...leads, ...deals, ...tasks].slice(0, 10);
});

const initials = computed(() => {
  const name = crmStore.me.value?.full_name ?? crmStore.activeTenant.value?.name ?? "Пользователь";
  return name.split(/\s+/).map((part) => part[0]).join("").slice(0, 2).toUpperCase();
});

function keyboardShortcut(event: KeyboardEvent) {
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
    event.preventDefault();
    activePanel.value = "search";
    requestAnimationFrame(() => document.querySelector<HTMLInputElement>(".home-search input")?.focus());
  }
  if (event.key === "Escape") activePanel.value = null;
}

function closeAppearanceOnOutsideClick(event: PointerEvent) {
  if (
    activePanel.value === "appearance"
    && event.target instanceof Node
    && !appearanceMenu.value?.contains(event.target)
  ) {
    activePanel.value = null;
  }
}

onMounted(async () => {
  await Promise.allSettled([crmStore.refreshAll(), crmStore.refreshMe(), crmStore.refreshCommunication()]);
  window.addEventListener("keydown", keyboardShortcut);
  window.addEventListener("pointerdown", closeAppearanceOnOutsideClick);
});

onBeforeUnmount(() => {
  window.removeEventListener("keydown", keyboardShortcut);
  window.removeEventListener("pointerdown", closeAppearanceOnOutsideClick);
});

function togglePanel(panel: Exclude<typeof activePanel.value, null>) {
  activePanel.value = activePanel.value === panel ? null : panel;
}

function navigate(to: string) {
  activePanel.value = null;
  isMobileMoreOpen.value = false;
  searchQuery.value = "";
  void router.push(to);
}

async function logout() {
  await crmStore.logout();
  void router.push("/login");
}

function setSidebarMode(mode: "full" | "compact" | "hidden") {
  sidebarMode.value = mode;
  localStorage.setItem("cmr_sidebar_mode", mode);
}

function openTaskCreate() {
  void router.replace({ path: "/tasks", query: { ...route.query, create: "1" } });
}

function syncAgentRouteContext() {
  const dealId = typeof route.query.deal === "string" ? route.query.deal : "";
  const deal = crmStore.deals.value.find((item) => item.id === dealId);
  if (deal) {
    crmStore.setAgentContext({
      type: "deal",
      company_id: deal.company_id,
      deal_id: deal.id,
      page_path: route.fullPath
    });
    return;
  }
  const companyId = typeof route.query.company === "string" ? route.query.company : "";
  const company = crmStore.companies.value.find((item) => item.id === companyId);
  if (company) {
    crmStore.setAgentContext({
      type: "company",
      company_id: company.id,
      page_path: route.fullPath
    });
    return;
  }
  if (route.path === "/knowledge" && isAgentOpen.value && crmStore.agentContext.value.type === "document") {
    return;
  }
  crmStore.setAgentContext({
    type: route.path === "/knowledge" ? "knowledge" : "workspace",
    page_path: route.fullPath
  });
}

watch(
  [() => route.fullPath, () => crmStore.companies.value.length, () => crmStore.deals.value.length],
  syncAgentRouteContext,
  { immediate: true }
);
</script>

<template>
  <main class="app-shell" :class="[`sidebar-${sidebarMode}`, `density-${density}`, { 'agent-open': isAgentOpen, 'tasks-workspace-active': isTasks }]" :data-density="density">
    <aside class="sidebar" aria-label="Основная навигация">
      <div class="sidebar-controls" aria-label="Режим боковой панели">
        <button type="button" :class="{ active: sidebarMode === 'full' }" aria-label="Полный сайдбар" title="Полный сайдбар" @click="setSidebarMode('full')"><span class="layout-icon layout-icon-full" aria-hidden="true"></span></button>
        <button type="button" :class="{ active: sidebarMode === 'compact' }" aria-label="Компактный сайдбар" title="Компактный сайдбар" @click="setSidebarMode('compact')"><span class="layout-icon layout-icon-compact" aria-hidden="true"></span></button>
        <button type="button" :class="{ active: sidebarMode === 'hidden' }" aria-label="Скрыть сайдбар" title="Скрыть сайдбар" @click="setSidebarMode('hidden')"><span class="layout-icon layout-icon-hidden" aria-hidden="true"></span></button>
      </div>
      <div class="brand">
        <span class="brand-mark"><img :src="theme === 'dark' ? voknapLogoDark : voknapLogo" alt="Voknap" /></span>
      </div>

      <nav class="nav">
        <section v-for="group in navGroups" :key="group.label" class="nav-group">
          <p class="nav-group__label">{{ group.label }}</p>
          <RouterLink v-for="item in group.items" :key="item.to" :to="item.to" :data-label="item.label">
            <UiIcon class="nav-icon" :name="item.icon" :size="20" />
            <b>{{ item.label }}</b>
          </RouterLink>
        </section>
      </nav>

      <div class="sidebar-footer">
        <div ref="appearanceMenu" class="sidebar-appearance">
          <button
            class="secondary sidebar-appearance__trigger"
            type="button"
            :aria-expanded="activePanel === 'appearance'"
            aria-haspopup="dialog"
            @click="togglePanel('appearance')"
          >
            <UiIcon name="sun" :size="17" />
            <span>Оформление</span>
            <UiIcon class="sidebar-appearance__chevron" name="chevronDown" :size="15" />
          </button>
          <section
            v-if="activePanel === 'appearance'"
            class="sidebar-appearance__popover"
            role="dialog"
            aria-label="Оформление интерфейса"
          >
            <header><strong>Оформление</strong></header>
            <div class="sidebar-appearance__group">
              <span>Тема</span>
              <UiThemeToggle />
            </div>
            <div class="sidebar-appearance__group">
              <span>Плотность</span>
              <UiDensityToggle />
            </div>
          </section>
        </div>
        <button class="secondary" type="button" @click="logout">Выйти</button>
      </div>
    </aside>

    <div v-if="sidebarMode === 'hidden'" class="sidebar-hover-zone" aria-hidden="true"></div>

    <section class="content">
      <header v-if="isHome" class="topbar home-topbar">
        <label class="home-search" aria-label="Поиск по рабочему пространству">
          <UiIcon name="search" :size="18" />
          <input v-model="searchQuery" type="search" placeholder="Поиск сделок, компаний и задач..." @focus="activePanel = 'search'" />
          <kbd>⌘K</kbd>
          <section v-if="activePanel === 'search'" class="top-popover search-popover">
            <p v-if="searchQuery.trim().length < 2" class="popover-empty">Введите минимум 2 символа</p>
            <button v-for="item in searchResults" :key="item.id" type="button" class="popover-row" @click="navigate(item.to)">
              <span>{{ item.type }}</span><div><strong>{{ item.title }}</strong><small>{{ item.meta }}</small></div>
            </button>
            <p v-if="searchQuery.trim().length >= 2 && !searchResults.length" class="popover-empty">Ничего не найдено</p>
          </section>
        </label>
        <div class="home-top-actions">
          <div class="top-action-wrap">
            <button type="button" class="secondary home-new-button" @click="togglePanel('new')"><UiIcon name="plus" :size="16" /> Создать <UiIcon name="chevronDown" :size="16" /></button>
            <section v-if="activePanel === 'new'" class="top-popover action-popover">
              <button type="button" @click="navigate('/companies?create=1')">Новую компанию</button>
              <button type="button" @click="navigate('/leads')">Новый лид</button>
              <button type="button" @click="navigate('/deals?create=1')">Новую сделку</button>
              <button type="button" @click="navigate('/tasks?create=1')">Новую задачу</button>
              <button type="button" @click="navigate('/inbox')">Входящее событие</button>
            </section>
          </div>
          <NotificationBell />
          <div class="top-action-wrap">
            <button type="button" class="secondary home-avatar" aria-label="Профиль" @click="togglePanel('profile')">{{ initials }}</button>
            <section v-if="activePanel === 'profile'" class="top-popover profile-popover">
              <strong>{{ crmStore.me.value?.full_name ?? "Пользователь" }}</strong>
              <small>{{ crmStore.me.value?.email }}</small>
              <small>{{ crmStore.me.value?.role }} · {{ crmStore.activeTenant.value?.name }}</small>
              <button type="button" @click="navigate('/settings')">Настройки профиля</button>
            </section>
          </div>
          <div class="top-action-wrap">
            <button type="button" class="secondary home-caret" aria-label="Меню" @click="togglePanel('menu')"><UiIcon name="chevronDown" :size="18" /></button>
            <section v-if="activePanel === 'menu'" class="top-popover action-popover menu-popover">
              <button type="button" @click="navigate('/settings')">Настройки рабочего пространства</button>
              <button type="button" @click="crmStore.openAgent(crmStore.agentContext.value); activePanel = null">AI-ассистент</button>
              <button type="button" class="danger-item" @click="logout">Выйти</button>
            </section>
          </div>
        </div>
      </header>

      <header v-else class="topbar" :class="{ 'tasks-topbar': isTasks }">
        <div>
          <p class="eyebrow">{{ pageEyebrow }}</p>
          <h1>{{ pageTitle }}</h1>
        </div>
        <div v-if="isTasks" class="tasks-top-actions">
          <button type="button" class="secondary tasks-ai-inbox" @click="navigate('/inbox?tab=notifications')"><UiIcon name="sparkles" :size="16" /> AI-входящие <b>{{ notificationStore.summary.value.unread_count }}</b></button>
          <NotificationBell />
          <button type="button" class="tasks-new-button" @click="openTaskCreate"><UiIcon name="plus" :size="16" /> Новая задача</button>
          <button type="button" class="secondary tasks-refresh" @click="crmStore.refreshAll"><UiIcon name="refresh" :size="16" /> Обновить</button>
          <button type="button" class="secondary tasks-more" aria-label="Дополнительные действия"><UiIcon name="more" :size="18" /></button>
        </div>
        <div v-else class="page-top-actions"><NotificationBell /><button type="button" class="secondary" @click="crmStore.refreshAll">Обновить</button></div>
      </header>

      <UiAlert v-if="crmStore.error.value" tone="danger" title="Не удалось выполнить действие">{{ crmStore.error.value }}</UiAlert>
      <UiAlert v-if="crmStore.ok.value" tone="success">{{ crmStore.ok.value }}</UiAlert>

      <RouterView />
    </section>

    <button
      v-if="!isAgentOpen"
      class="agent-edge"
      type="button"
      aria-label="Открыть AI агента"
      @click="crmStore.openAgent(crmStore.agentContext.value)"
    >
      <UiIcon name="chevronLeft" :size="18" />
    </button>

    <div v-if="isAgentOpen" class="agent-backdrop" @click="crmStore.closeAgent"></div>
    <GlobalAgentSidebar :open="isAgentOpen" @close="crmStore.closeAgent" />

    <nav class="mobile-nav" aria-label="Мобильная навигация">
      <RouterLink v-for="item in mobilePrimary" :key="item.to" :to="item.to">
        <UiIcon :name="item.icon" :size="20" /><span>{{ item.label }}</span>
      </RouterLink>
      <button type="button" :class="{ active: isMobileMoreOpen }" @click="isMobileMoreOpen = true">
        <UiIcon name="more" :size="20" /><span>Ещё</span>
      </button>
    </nav>

    <div v-if="isMobileMoreOpen" class="mobile-more-layer" @click.self="isMobileMoreOpen = false">
      <section class="mobile-more" role="dialog" aria-modal="true" aria-label="Все разделы">
        <header><h2>Все разделы</h2><button class="secondary" type="button" aria-label="Закрыть" @click="isMobileMoreOpen = false"><UiIcon name="close" :size="18" /></button></header>
        <UiThemeToggle class="mobile-theme" />
        <UiDensityToggle class="mobile-density" />
        <div class="mobile-more__grid">
          <RouterLink v-for="item in navItems" :key="item.to" :to="item.to" @click="isMobileMoreOpen = false">
            <UiIcon :name="item.icon" :size="20" /><span>{{ item.label }}</span>
          </RouterLink>
        </div>
      </section>
    </div>
  </main>
</template>

<style scoped>
.home-search, .top-action-wrap { position: relative; }
.page-top-actions { display:flex; align-items:center; gap:8px; }
.sidebar-appearance { position:relative; }
.sidebar-appearance__trigger { width:100%; justify-content:flex-start; gap:8px; }
.sidebar-appearance__trigger span { flex:1; text-align:left; }
.sidebar-appearance__chevron { transition:transform var(--duration-fast) var(--ease-standard); }
.sidebar-appearance__trigger[aria-expanded="true"] .sidebar-appearance__chevron { transform:rotate(180deg); }
.sidebar-appearance__popover { position:absolute; z-index:85; bottom:calc(100% + 8px); left:0; display:grid; gap:14px; width:260px; border:1px solid var(--color-border); border-radius:var(--radius-card); padding:14px; color:var(--color-text-primary); background:var(--color-surface); box-shadow:var(--shadow-popover); }
.sidebar-appearance__popover header { display:flex; align-items:center; justify-content:space-between; }
.sidebar-appearance__group { display:grid; gap:7px; }
.sidebar-appearance__group > span { color:var(--color-text-muted); font-size:var(--font-size-meta); font-weight:700; }
.sidebar-appearance__popover :deep(.ui-theme span),
.sidebar-appearance__popover :deep(.ui-density span) { display:none; }
.top-popover { position: absolute; z-index: 80; top: calc(100% + 8px); right: 0; width: 280px; overflow: hidden; border: 1px solid var(--line); border-radius: var(--radius-card); padding: 8px; background: var(--surface-solid); box-shadow: 0 16px 40px rgb(0 0 0 / 14%); }
.search-popover { right: auto; left: 0; width: 100%; min-width: 390px; }
.top-popover button { width: 100%; justify-content: flex-start; border: 0; padding: 10px; color: var(--text); background: transparent; text-align: left; }
.top-popover button:hover { background: var(--surface-muted); }
.popover-row { display: flex; align-items: center; gap: 10px; }
.popover-row > span { flex: 0 0 62px; color: var(--brand); font-size: 10px; font-weight: 800; text-transform: uppercase; }
.popover-row > div { display: grid; min-width: 0; gap: 2px; }
.popover-row small, .profile-popover small { color: var(--muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.popover-empty { margin: 0; padding: 14px 10px; color: var(--muted); text-align: center; }
.notification-popover header { display: flex; justify-content: space-between; padding: 8px 10px; }
.popover-row i { width: 8px; height: 8px; border-radius: 50%; background: var(--brand); }
.popover-row i.danger { background: var(--danger); }
.popover-row i.warning { background: var(--warning); }
.profile-popover { display: grid; gap: 6px; padding: 14px; }
.profile-popover button { margin-top: 6px; }
.top-popover .danger-item { color: var(--danger); }
.tasks-topbar { min-height: 82px; background: rgba(255, 255, 255, 0.9); }
.tasks-topbar h1 { margin: 2px 0 0; font-size: 28px; line-height: 34px; letter-spacing: -0.025em; }
.tasks-topbar .eyebrow { margin: 0; font-size: 10px; line-height: 14px; letter-spacing: 0.08em; text-transform: uppercase; }
.tasks-top-actions { display: flex; align-items: center; gap: 8px; }
.tasks-top-actions button { height: 38px; border-radius: var(--radius-control); padding: 0 13px; font-size: 13px; white-space: nowrap; }
.tasks-top-actions button span { font-size: 15px; }
.tasks-top-actions .tasks-ai-inbox { gap: 7px; color: #172033; }
.tasks-ai-inbox span { color: #7656e8; }
.tasks-ai-inbox b { display: grid; place-items: center; min-width: 22px; height: 22px; border-radius: 999px; padding: 0 6px; color: #0b72e7; background: #edf5ff; font-size: 10px; }
.tasks-top-actions .tasks-new-button { gap: 7px; border-color: #0b72e7; background: #0b72e7; }
.tasks-top-actions .tasks-refresh { gap: 7px; color: #172033; }
.tasks-top-actions .tasks-more { width: 38px; padding: 0; color: #172033; font-size: 18px; }
.app-shell.tasks-workspace-active { background: #f6f8fb; }
.tasks-workspace-active .content { width: min(1600px, 100%); padding: 20px 24px 32px; }
.tasks-workspace-active .topbar { margin: -20px -24px 20px; padding: 18px 24px; }
@media (max-width: 760px) { .tasks-top-actions .tasks-ai-inbox, .tasks-top-actions .tasks-refresh { display: none; } .tasks-topbar h1 { font-size: 23px; } }
@media (max-width: 920px) { .app-shell.tasks-workspace-active { grid-template-columns: 1fr; } .tasks-workspace-active .content { padding: calc(18px + env(safe-area-inset-top)) 14px calc(92px + env(safe-area-inset-bottom)); } .tasks-workspace-active .topbar { margin: -18px -14px 16px; padding: 16px 14px 12px; } }
@media (max-width: 760px) { .search-popover { min-width: 280px; } .top-popover { right: auto; left: 0; } }
</style>
