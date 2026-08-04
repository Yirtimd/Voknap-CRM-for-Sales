<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";

import UiIcon from "../components/ui/UiIcon.vue";
import CustomFieldReportPanel from "../components/crm/CustomFieldReportPanel.vue";
import { crmStore } from "../stores/crm";
import { formatStageName, isTerminalStage } from "../utils/stages";

const loading = ref(false);
const loadError = ref("");
const data = computed(() => crmStore.analyticsOverview.value);
type AnalyticsPanel = "summary" | "forecast" | "conversion" | "sla" | "risk" | "activity";

const activePanel = ref<AnalyticsPanel | null>(null);

async function loadAnalytics() {
  loading.value = true;
  loadError.value = "";
  try {
    await crmStore.refreshAnalytics();
  } catch (caught) {
    loadError.value = caught instanceof Error ? caught.message : "Аналитика временно недоступна";
  } finally {
    loading.value = false;
  }
}

onMounted(loadAnalytics);

const forecast = computed(() => data.value?.forecast);
const riskMap = computed(() => data.value?.risk_map);
const taskSla = computed(() => data.value?.task_sla);

const topRiskDeals = computed(() => riskMap.value?.deals?.slice(0, 3) ?? []);
const stuckDeals = computed(() => data.value?.stuck_deals?.slice(0, 3) ?? []);
const managerActivity = computed(() => data.value?.manager_activity ?? []);
const forecastOwners = computed(() => data.value?.forecast_by_owner ?? []);
const forecastTeams = computed(() => data.value?.forecast_by_team ?? []);
const forecastQuality = computed(() => data.value?.forecast_quality);
const unhealthyCompanies = computed(() => data.value?.company_health?.filter((company) => company.risk_level !== "low").slice(0, 3) ?? []);

const bottleneckStage = computed(() => {
  const stages = data.value?.stage_conversion ?? [];
  const activeStages = stages.filter((stage) => !isTerminalStage(stage.stage_name));
  return [...activeStages].sort((left, right) => right.stuck_count - left.stuck_count || left.conversion_from_previous - right.conversion_from_previous)[0];
});

const goalProgress = computed(() => {
  const openPipeline = forecast.value?.open_pipeline ?? 0;
  const weighted = forecast.value?.weighted_revenue ?? 0;
  if (!openPipeline) return 0;
  return Math.min(98, Math.round((weighted / openPipeline) * 100));
});

const avgResolution = computed(() => {
  const value = taskSla.value?.average_resolution_hours;
  return value == null ? "2,1 ч" : `${Math.round(value * 10) / 10} ч`;
});

const meetingsThisWeek = computed(() => managerActivity.value.reduce((sum, manager) => sum + manager.meetings, 0));
const completedTasks = computed(() => taskSla.value?.completed ?? 0);
const periodDays = computed(() => forecast.value?.period_days ?? 90);

const forecastPoints = computed(() => {
  const source = [
    forecast.value?.commit_revenue ?? 0,
    forecast.value?.best_case_revenue ?? 0,
    forecast.value?.weighted_revenue ?? 0,
    forecast.value?.pipeline_revenue ?? 0,
    forecast.value?.due_in_period ?? 0,
    forecast.value?.open_pipeline ?? 0
  ];
  const max = Math.max(...source, 1);
  return source.map((point, index) => {
    const x = 10 + index * 56;
    const y = 142 - (point / max) * 106;
    return `${x},${Math.max(22, Math.round(y))}`;
  }).join(" ");
});

const stageHealth = computed(() => {
  const stages = data.value?.stage_conversion ?? [];
  const maxAmount = Math.max(...stages.map((stage) => stage.amount), 1);
  return stages.map((stage) => ({
    ...stage,
    width: Math.max(4, Math.round((stage.amount / maxAmount) * 100)),
    isBottleneck: stage.stage_id === bottleneckStage.value?.stage_id
  }));
});

const nextBestDeal = computed(() => topRiskDeals.value[0] ?? stuckDeals.value[0]);

const kpis = computed(() => [
  {
    panel: "forecast" as AnalyticsPanel,
    label: "Портфель",
    value: crmStore.money(forecast.value?.open_pipeline),
    trend: `${forecast.value?.open_deals ?? 0} сделок`,
    detail: "активная воронка",
    direction: "up"
  },
  {
    panel: "forecast" as AnalyticsPanel,
    label: "Выручка",
    value: crmStore.money(forecast.value?.weighted_revenue),
    trend: `${periodDays.value} дн.`,
    detail: "взвешенный прогноз",
    direction: "up"
  },
  {
    panel: "conversion" as AnalyticsPanel,
    label: "Вероятность успеха",
    value: `${goalProgress.value}%`,
    trend: `Scoring ${forecast.value?.scoring_coverage_rate ?? 0}%`,
    detail: "вероятность плана",
    direction: "up"
  },
  {
    panel: "sla" as AnalyticsPanel,
    label: "Средний цикл",
    value: avgResolution.value,
    trend: `${taskSla.value?.overdue ?? 0} просрочено`,
    detail: "скорость задач",
    direction: "down"
  }
]);

function generatedAt(value?: string) {
  return value ? new Intl.DateTimeFormat("ru-RU", { dateStyle: "short", timeStyle: "short" }).format(new Date(value)) : "—";
}

const detail = computed(() => {
  const panel = activePanel.value;
  if (!panel) return null;
  if (panel === "forecast") {
    return {
      eyebrow: "Прогноз выручки",
      title: "Воронка и прогноз",
      summary: `В прогноз на ${periodDays.value} дней входит ${forecast.value?.open_deals ?? 0} открытых сделок. Взвешенная выручка учитывает вероятность каждой сделки.`,
      metrics: [
        ["Открытая воронка", crmStore.money(forecast.value?.open_pipeline)],
        ["Закрытие в периоде", crmStore.money(forecast.value?.due_in_period)],
        ["Взвешенная выручка", crmStore.money(forecast.value?.weighted_revenue)],
        ["Просроченная выручка", crmStore.money(forecast.value?.overdue_revenue)],
        ["Покрытие scoring", `${forecast.value?.scoring_coverage_rate ?? 0}%`]
      ],
      rows: [
        ["Подтверждено", crmStore.money(forecast.value?.commit_revenue)],
        ["Лучший сценарий", crmStore.money(forecast.value?.best_case_revenue)],
        ["Воронка", crmStore.money(forecast.value?.pipeline_revenue)],
        ["Выиграно", crmStore.money(forecast.value?.won_revenue)],
        ["Без opportunity score", `${forecastQuality.value?.missing_opportunity_score ?? 0}`]
      ],
      link: "/deals",
      linkLabel: "Открыть сделки"
    };
  }
  if (panel === "conversion") {
    return {
      eyebrow: "Диагностика воронки",
      title: "Конверсия по этапам",
      summary: bottleneckStage.value
        ? `Главное узкое место — «${formatStageName(bottleneckStage.value.stage_name)}»: ${bottleneckStage.value.stuck_count} зависших сделок, конверсия ${bottleneckStage.value.conversion_from_previous}%.`
        : "Недостаточно данных для определения узкого места.",
      metrics: [
        ["Этапов", `${stageHealth.value.length}`],
        ["Узкое место", bottleneckStage.value ? formatStageName(bottleneckStage.value.stage_name) : "—"],
        ["Зависших сделок", `${bottleneckStage.value?.stuck_count ?? 0}`],
        ["От первого этапа", `${bottleneckStage.value?.conversion_from_first ?? 0}%`]
      ],
      rows: stageHealth.value.map((stage) => [
        `${stage.pipeline_name} · ${formatStageName(stage.stage_name)}`,
        `${stage.conversion_from_previous}% · ${stage.deal_count} deals · ${crmStore.money(stage.amount)}`
      ]),
      link: "/deals",
      linkLabel: "Открыть воронку"
    };
  }
  if (panel === "sla") {
    return {
      eyebrow: "Качество работы",
      title: "SLA задач",
      summary: `${taskSla.value?.overdue ?? 0} задач просрочено. SLA команды — ${taskSla.value?.sla_rate ?? 0}%, среднее время выполнения — ${avgResolution.value}.`,
      metrics: [
        ["Всего", `${taskSla.value?.total ?? 0}`],
        ["Завершено", `${taskSla.value?.completed ?? 0}`],
        ["Просрочено", `${taskSla.value?.overdue ?? 0}`],
        ["SLA", `${taskSla.value?.sla_rate ?? 0}%`]
      ],
      rows: (taskSla.value?.by_owner ?? []).map((owner) => [
        owner.owner_name,
        `${owner.sla_rate}% SLA · ${owner.overdue} overdue · ${owner.completed}/${owner.total} done`
      ]),
      link: "/tasks",
      linkLabel: "Открыть задачи"
    };
  }
  if (panel === "risk") {
    return {
      eyebrow: "Карта рисков AI",
      title: "Сделки под риском",
      summary: `${riskMap.value?.high ?? 0} сделок имеют высокий риск. Суммарная выручка под риском — ${crmStore.money(riskMap.value?.revenue_at_risk)}.`,
      metrics: [
        ["Высокий", `${riskMap.value?.high ?? 0}`],
        ["Средний", `${riskMap.value?.medium ?? 0}`],
        ["Низкий", `${riskMap.value?.low ?? 0}`],
        ["Выручка под риском", crmStore.money(riskMap.value?.revenue_at_risk)]
      ],
      rows: (riskMap.value?.deals ?? []).map((deal) => [
        `${deal.company_name} · ${deal.title}`,
        `${deal.score}% · ${crmStore.money(deal.amount)} · ${deal.reasons.join(", ")}`
      ]),
      link: "/deals",
      linkLabel: "Открыть риски"
    };
  }
  if (panel === "activity") {
    return {
      eyebrow: "Эффективность менеджеров",
      title: "Активность команды",
      summary: `За период команда провела ${meetingsThisWeek.value} встреч и выполнила ${completedTasks.value} задач.`,
      metrics: [
        ["Менеджеров", `${managerActivity.value.length}`],
        ["Встреч", `${meetingsThisWeek.value}`],
        ["Завершено задач", `${completedTasks.value}`],
        ["SLA команды", `${taskSla.value?.sla_rate ?? 0}%`]
      ],
      rows: managerActivity.value.map((manager) => [
        manager.manager_name,
        `${manager.activities} activities · ${manager.calls} calls · ${manager.emails} emails · ${manager.meetings} meetings`
      ]),
      link: "/tasks",
      linkLabel: "Открыть задачи команды"
    };
  }
  const companyRisk = unhealthyCompanies.value[0];
  return {
    eyebrow: "Управленческая сводка",
    title: "Сводка AI",
    summary: `Взвешенный прогноз составляет ${crmStore.money(forecast.value?.weighted_revenue)} при открытом pipeline ${crmStore.money(forecast.value?.open_pipeline)}. Под риском находится ${crmStore.money(riskMap.value?.revenue_at_risk)}.`,
    metrics: [
      ["Взвешенный прогноз", crmStore.money(forecast.value?.weighted_revenue)],
      ["Сделки высокого риска", `${riskMap.value?.high ?? 0}`],
      ["Просроченные задачи", `${taskSla.value?.overdue ?? 0}`],
      ["SLA команды", `${taskSla.value?.sla_rate ?? 0}%`]
    ],
    rows: [
      ["Приоритет 1", bottleneckStage.value ? `Разобрать зависшие сделки этапа «${formatStageName(bottleneckStage.value.stage_name)}»` : "Проверить структуру воронки"],
      ["Приоритет 2", nextBestDeal.value ? `Связаться с ${nextBestDeal.value.company_name}: риск ${crmStore.money(nextBestDeal.value.amount)}` : "Назначить следующий шаг по ключевым сделкам"],
      ["Приоритет 3", taskSla.value?.overdue ? `Закрыть ${taskSla.value.overdue} просроченных задач` : "Сохранить текущий уровень SLA"],
      ["Фокус по компаниям", companyRisk ? `${companyRisk.company_name}: ${companyRisk.reasons.join(" · ") || companyRisk.label}` : "Критических компаний нет"]
    ],
    link: "/deals",
    linkLabel: "Перейти к сделкам"
  };
});

function openPanel(panel: AnalyticsPanel) {
  activePanel.value = panel;
}

function closePanel() {
  activePanel.value = null;
}

function handleEscape(event: KeyboardEvent) {
  if (event.key === "Escape") closePanel();
}

onMounted(() => window.addEventListener("keydown", handleEscape));
onBeforeUnmount(() => window.removeEventListener("keydown", handleEscape));
</script>

<template>
  <section class="analytics-page">
    <header class="analytics-head">
      <div>
        <p class="eyebrow">Обновлено {{ generatedAt(data?.generated_at) }}</p>
        <h2>Обзор показателей</h2>
      </div>
      <div class="analytics-actions">
        <button type="button" class="secondary" :disabled="loading || !data" @click="openPanel('summary')">Сводка AI</button>
        <button type="button" aria-label="Обновить аналитику" :disabled="loading" @click="loadAnalytics">
          <span v-if="loading">…</span><UiIcon v-else name="refresh" :size="17" />
        </button>
      </div>
    </header>

    <p v-if="loadError" class="analytics-error">{{ loadError }}</p>

    <section class="analytics-top-grid">
      <article
        v-for="kpi in kpis"
        :key="kpi.label"
        class="analytics-kpi interactive-card"
        role="button"
        tabindex="0"
        @click="openPanel(kpi.panel)"
        @keydown.enter.space.prevent="openPanel(kpi.panel)"
      >
        <span>{{ kpi.label }}</span>
        <strong>{{ kpi.value }}</strong>
        <small :class="kpi.direction">{{ kpi.trend }} · {{ kpi.detail }}</small>
      </article>

      <article class="ai-summary-card interactive-card" role="button" tabindex="0" @click="openPanel('summary')" @keydown.enter.space.prevent="openPanel('summary')">
        <span>Выводы AI</span>
        <strong>
          Этап «{{ bottleneckStage ? formatStageName(bottleneckStage.stage_name) : "КП" }}» требует внимания
        </strong>
        <small>
          {{ topRiskDeals.length || stuckDeals.length }} сделки в зоне риска · экспозиция
          {{ crmStore.money(riskMap?.revenue_at_risk ?? 0) }}
        </small>
        <div class="goal-line">
          <span>Взвешенная цель</span>
          <b>{{ goalProgress }}%</b>
        </div>
        <div class="goal-track"><i :style="{ width: `${goalProgress}%` }"></i></div>
      </article>
    </section>

    <section class="forecast-breakdowns">
      <section class="analytics-panel">
        <div class="panel-title"><div><p class="eyebrow">Прогноз по командам</p><h3>Ответственность за результат</h3></div><span>{{ forecastTeams.length }}</span></div>
        <article v-for="item in forecastTeams" :key="item.scope_id || 'none'" class="forecast-scope-row"><div><strong>{{ item.scope_name }}</strong><small>{{ item.open_deals }} сделок · commit {{ crmStore.money(item.commit_revenue) }}</small></div><b>{{ crmStore.money(item.weighted_revenue) }}</b></article>
        <p v-if="!forecastTeams.length" class="empty">Команды не назначены.</p>
      </section>
      <section class="analytics-panel">
        <div class="panel-title"><div><p class="eyebrow">Прогноз по менеджерам</p><h3>Взвешенная выручка</h3></div><span>{{ forecastOwners.length }}</span></div>
        <article v-for="item in forecastOwners.slice(0, 8)" :key="item.scope_id || 'none'" class="forecast-scope-row"><div><strong>{{ item.scope_name }}</strong><small>{{ crmStore.money(item.open_pipeline) }} в работе · просрочено {{ crmStore.money(item.overdue_revenue) }}</small></div><b>{{ crmStore.money(item.weighted_revenue) }}</b></article>
      </section>
      <section class="analytics-panel forecast-quality">
        <div class="panel-title"><div><p class="eyebrow">Качество прогноза</p><h3>{{ forecastQuality?.completeness_rate ?? 0 }}% заполнено</h3></div></div>
        <dl><div><dt>Нет даты закрытия</dt><dd>{{ forecastQuality?.missing_close_date ?? 0 }}</dd></div><div><dt>Нет вероятности</dt><dd>{{ forecastQuality?.missing_probability ?? 0 }}</dd></div><div><dt>Нет категории</dt><dd>{{ forecastQuality?.missing_forecast_category ?? 0 }}</dd></div><div><dt>Нет владельца</dt><dd>{{ forecastQuality?.missing_owner ?? 0 }}</dd></div></dl>
      </section>
    </section>

    <section class="analytics-main-grid">
      <section class="analytics-panel forecast-panel interactive-card" role="button" tabindex="0" @click="openPanel('forecast')" @keydown.enter.space.prevent="openPanel('forecast')">
        <div class="panel-title">
          <div>
            <p class="eyebrow">Прогноз выручки</p>
            <h3>{{ crmStore.money(forecast?.weighted_revenue) }}</h3>
          </div>
          <span>{{ periodDays }} дней</span>
        </div>
        <div class="chart-frame">
          <svg viewBox="0 0 296 160" preserveAspectRatio="none" role="img" aria-label="Динамика прогноза выручки">
            <defs>
              <linearGradient id="forecastFill" x1="0" x2="0" y1="0" y2="1">
                <stop offset="0%" stop-color="var(--chart-primary)" stop-opacity="0.24" />
                <stop offset="100%" stop-color="var(--chart-primary)" stop-opacity="0" />
              </linearGradient>
            </defs>
            <path :d="`M10,148 L${forecastPoints} L290,148 Z`" fill="url(#forecastFill)" />
            <polyline :points="forecastPoints" fill="none" stroke="var(--chart-primary)" stroke-width="4" stroke-linecap="round" stroke-linejoin="round" vector-effect="non-scaling-stroke" />
            <line x1="10" y1="148" x2="290" y2="148" stroke="var(--chart-grid)" vector-effect="non-scaling-stroke" />
          </svg>
        </div>
        <div class="forecast-legend">
          <span>Подтверждено: {{ crmStore.money(forecast?.commit_revenue) }}</span>
          <span>Воронка: {{ crmStore.money(forecast?.pipeline_revenue) }}</span>
        </div>
      </section>

      <section class="analytics-panel health-panel interactive-card" role="button" tabindex="0" @click="openPanel('conversion')" @keydown.enter.space.prevent="openPanel('conversion')">
        <div class="panel-title">
          <div>
            <p class="eyebrow">Состояние воронки</p>
            <h3>Конверсия по этапам</h3>
          </div>
          <span>{{ bottleneckStage ? formatStageName(bottleneckStage.stage_name) : "Нет узкого места" }}</span>
        </div>
        <div class="funnel-list">
          <article v-for="stage in stageHealth" :key="stage.stage_id" :class="{ bottleneck: stage.isBottleneck }">
            <span>{{ formatStageName(stage.stage_name) }}</span>
            <div><i :style="{ width: `${stage.width}%` }"></i></div>
            <small>{{ stage.deal_count }} · {{ crmStore.money(stage.amount) }}</small>
          </article>
          <p v-if="!stageHealth.length" class="empty">Данных по воронке пока нет</p>
        </div>
      </section>
    </section>

    <section class="analytics-main-grid lower">
      <section class="analytics-panel risk-panel interactive-card" role="button" tabindex="0" @click="openPanel('risk')" @keydown.enter.space.prevent="openPanel('risk')">
        <div class="panel-title">
          <div>
            <p class="eyebrow">Главные риски</p>
            <h3>Сделки под риском</h3>
          </div>
          <span>Выручка под риском: {{ crmStore.money(riskMap?.revenue_at_risk ?? 0) }}</span>
        </div>
        <RouterLink v-for="deal in topRiskDeals" :key="deal.deal_id" to="/deals" class="risk-row" @click.stop>
          <i :class="deal.level"></i>
          <span>{{ deal.company_name }}</span>
          <small>Индекс риска {{ deal.score }}/100</small>
          <strong>{{ crmStore.money(deal.amount) }}</strong>
        </RouterLink>
        <RouterLink v-for="deal in stuckDeals" v-if="!topRiskDeals.length" :key="deal.deal_id" to="/deals" class="risk-row" @click.stop>
          <i :class="deal.risk_level"></i>
          <span>{{ deal.company_name }}</span>
          <small>{{ deal.days_in_stage }} дней</small>
          <strong>{{ crmStore.money(deal.amount) }}</strong>
        </RouterLink>
        <p v-if="!topRiskDeals.length && !stuckDeals.length" class="empty compact">Открытых сделок под риском нет</p>
      </section>

      <section class="analytics-panel activity-panel interactive-card" role="button" tabindex="0" @click="openPanel('activity')" @keydown.enter.space.prevent="openPanel('activity')">
        <div class="panel-title">
          <div>
            <p class="eyebrow">Активность команды</p>
            <h3>Скорость работы</h3>
          </div>
          <span>{{ taskSla?.sla_rate ?? 0 }}% SLA</span>
        </div>
        <dl>
          <div>
            <dt>Завершено задач</dt>
            <dd>{{ completedTasks }}</dd>
          </div>
          <div>
            <dt>Время ответа</dt>
            <dd>{{ avgResolution }}</dd>
          </div>
          <div>
            <dt>Встреч за период</dt>
            <dd>{{ meetingsThisWeek }}</dd>
          </div>
        </dl>
        <div class="ask-analytics">
          <span>Спросить аналитику</span>
          <button type="button" @click.stop="openPanel('conversion')">Почему упала конверсия?</button>
          <button type="button" @click.stop="openPanel('risk')">Какие сделки требуют внимания?</button>
        </div>
      </section>
    </section>

    <section v-if="unhealthyCompanies.length" class="analytics-panel company-strip">
      <div class="panel-title">
        <div>
          <p class="eyebrow">Состояние компаний</p>
          <h3>Компании, требующие внимания</h3>
        </div>
        <span>Показано: {{ unhealthyCompanies.length }}</span>
      </div>
      <RouterLink v-for="company in unhealthyCompanies" :key="company.company_id" :to="`/companies/${company.company_id}`" class="company-row">
        <i :class="company.risk_level">{{ company.score }}</i>
        <div>
          <strong>{{ company.company_name }}</strong>
          <small>{{ company.reasons.join(" · ") || company.label }}</small>
        </div>
        <b>{{ crmStore.money(company.pipeline_amount) }}</b>
      </RouterLink>
    </section>

    <section class="next-action">
      <div>
        <p class="eyebrow">Рекомендация AI</p>
        <strong>
          Свяжитесь с {{ nextBestDeal?.company_name ?? "ключевым клиентом" }} сегодня.
          Это снизит риск потери {{ crmStore.money(nextBestDeal?.amount ?? riskMap?.revenue_at_risk ?? 0) }}.
        </strong>
      </div>
      <RouterLink class="button-link" :to="nextBestDeal ? '/deals' : '/companies'">Открыть сделку →</RouterLink>
    </section>

    <CustomFieldReportPanel />

    <div v-if="detail" class="analytics-modal-backdrop" @click.self="closePanel">
      <section class="analytics-modal" role="dialog" aria-modal="true" :aria-label="detail.title">
        <header>
          <div>
            <p class="eyebrow">{{ detail.eyebrow }}</p>
            <h3>{{ detail.title }}</h3>
          </div>
          <button type="button" class="analytics-modal-close" aria-label="Закрыть детали аналитики" @click="closePanel"><UiIcon name="close" :size="19" /></button>
        </header>
        <p class="analytics-modal-summary">{{ detail.summary }}</p>
        <dl class="analytics-modal-metrics">
          <div v-for="metric in detail.metrics" :key="metric[0]">
            <dt>{{ metric[0] }}</dt>
            <dd>{{ metric[1] }}</dd>
          </div>
        </dl>
        <div class="analytics-modal-rows">
          <article v-for="row in detail.rows" :key="`${row[0]}-${row[1]}`">
            <strong>{{ row[0] }}</strong>
            <span>{{ row[1] }}</span>
          </article>
          <p v-if="!detail.rows.length" class="empty">Подробных данных за период нет</p>
        </div>
        <footer>
          <span>Обновлено {{ generatedAt(data?.generated_at) }}</span>
          <RouterLink class="button-link" :to="detail.link" @click="closePanel">{{ detail.linkLabel }} →</RouterLink>
        </footer>
      </section>
    </div>
  </section>
</template>

<style scoped>
.analytics-page {
  display: grid;
  gap: 14px;
  font-size: 13px;
  line-height: 1.35;
}

.analytics-head,
.next-action,
.analytics-kpi,
.ai-summary-card,
.analytics-panel {
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--surface-solid);
  box-shadow: var(--shadow-soft);
}

.analytics-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 14px 18px;
}

.analytics-head h2,
.panel-title h3 {
  margin: 0;
  color: var(--text);
}

.analytics-head h2 {
  font-size: 17px;
  line-height: 1.2;
}

.analytics-actions {
  display: flex;
  gap: 8px;
}

.analytics-actions button:last-child {
  width: 38px;
  padding: 0;
}

.analytics-error {
  margin: 0;
  border-radius: 8px;
  padding: 10px 14px;
  color: var(--danger);
  background: var(--color-danger-soft);
}

.analytics-top-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(112px, 1fr)) minmax(260px, 1.25fr);
  gap: 12px;
}

.analytics-kpi,
.ai-summary-card,
.analytics-panel {
  min-width: 0;
  color: var(--text);
  text-align: left;
}

.analytics-kpi,
.ai-summary-card {
  display: grid;
  gap: 6px;
  padding: 13px 14px;
}

.analytics-kpi span,
.ai-summary-card > span,
.forecast-legend,
.risk-row small,
.activity-panel dt,
.ask-analytics button,
.company-row small {
  color: var(--muted);
}

.interactive-card {
  cursor: pointer;
  transition: border-color 150ms ease, box-shadow 150ms ease, transform 150ms ease;
}

.interactive-card::after {
  content: "Открыть детали";
  display: block;
  margin-top: 12px;
  color: var(--color-primary);
  font-size: var(--font-size-meta);
  line-height: var(--line-height-meta);
  font-weight: 700;
}

.interactive-card:hover,
.interactive-card:focus-visible {
  border-color: color-mix(in srgb, var(--brand) 45%, var(--line));
  box-shadow: 0 8px 24px rgb(15 23 42 / 10%);
  outline: none;
  transform: translateY(-1px);
}

.analytics-kpi span {
  font-size: 13px;
  line-height: 1.2;
}

.analytics-kpi strong {
  font-size: clamp(18px, 1.25vw, 21px);
  line-height: 1.08;
  overflow-wrap: anywhere;
}

.analytics-kpi small,
.ai-summary-card small {
  font-size: 11.5px;
  line-height: 1.3;
}

.analytics-kpi small.up {
  color: var(--success);
}

.analytics-kpi small.down {
  color: var(--brand);
}

.ai-summary-card > span {
  font-size: 10.5px;
  font-weight: 800;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}

.ai-summary-card strong {
  font-size: 13.5px;
  line-height: 1.25;
}

.goal-line,
.forecast-legend,
.panel-title,
.risk-row,
.activity-panel dl div,
.company-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.goal-line {
  font-size: 12.5px;
}

.goal-track {
  height: 8px;
  overflow: hidden;
  border-radius: 999px;
  background: var(--surface-muted);
}

.goal-track i,
.funnel-list i {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: var(--brand);
}

.analytics-main-grid {
  display: grid;
  grid-template-columns: minmax(0, 0.92fr) minmax(0, 1.08fr);
  gap: 12px;
}

.analytics-main-grid.lower {
  grid-template-columns: minmax(0, 0.9fr) minmax(0, 1.1fr);
}

.analytics-panel {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 14px;
  padding: 16px;
}

.analytics-panel > * {
  min-width: 0;
  width: 100%;
}

.panel-title {
  align-items: flex-start;
}

.panel-title > span {
  width: auto;
  max-width: 48%;
  border-radius: 999px;
  padding: 5px 9px;
  color: var(--brand-strong);
  background: var(--brand-soft);
  font-size: 11.5px;
  font-weight: 700;
  line-height: 1.15;
  overflow-wrap: anywhere;
}

.panel-title h3 {
  font-size: 16px;
  line-height: 1.15;
}

.panel-title .eyebrow {
  margin-bottom: 2px;
  font-size: 10.5px;
}

.chart-frame {
  width: 100%;
  min-width: 0;
}

.forecast-panel svg {
  display: block;
  width: 100%;
  height: 210px;
}

.forecast-legend {
  font-size: 12px;
}

.funnel-list {
  display: grid;
  gap: 10px;
  width: 100%;
}

.funnel-list article {
  display: grid;
  grid-template-columns: minmax(92px, 0.55fr) minmax(160px, 1fr) minmax(102px, 0.5fr);
  gap: 14px;
  align-items: center;
  min-width: 0;
  width: 100%;
  font-size: 12.5px;
}

.funnel-list article > span {
  min-width: 0;
  overflow-wrap: anywhere;
  line-height: 1.18;
}

.funnel-list div {
  width: 100%;
  height: 10px;
  overflow: hidden;
  border-radius: 999px;
  background: var(--surface-muted);
}

.funnel-list small {
  color: var(--muted);
  font-size: 12px;
  text-align: right;
}

.funnel-list .bottleneck span,
.funnel-list .bottleneck small {
  color: var(--warning);
  font-weight: 700;
}

.funnel-list .bottleneck i,
.risk-row i.medium {
  background: var(--warning);
}

.risk-panel,
.activity-panel {
  align-content: start;
}

.risk-row,
.company-row {
  min-height: 42px;
  border-top: 1px solid var(--line-soft);
  padding-top: 10px;
  color: inherit;
  font-size: 12.5px;
  text-decoration: none;
}

.risk-row i {
  width: 10px;
  height: 10px;
  border-radius: 999px;
  background: var(--success);
}

.risk-row i.high {
  background: var(--danger);
}

.risk-row span,
.company-row div {
  flex: 1;
  min-width: 0;
}

.risk-row span,
.company-row strong,
.company-row small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.risk-row strong {
  flex: 0 0 auto;
  font-size: 13px;
}

.activity-panel dl {
  display: grid;
  gap: 0;
  width: 100%;
  margin: 0;
}

.activity-panel dl div {
  border-top: 1px solid var(--line-soft);
  padding: 11px 0;
  font-size: 12.5px;
}

.activity-panel dd {
  margin: 0;
  font-size: 15px;
  font-weight: 800;
}

.ask-analytics {
  display: grid;
  gap: 6px;
  width: 100%;
  border-radius: 8px;
  padding: 12px;
  background: var(--color-surface-muted);
}

.ask-analytics span {
  font-size: 12.5px;
  font-weight: 800;
}

.ask-analytics button {
  width: 100%;
  border: 0;
  padding: 0;
  color: var(--muted);
  background: transparent;
  font-size: 12px;
  line-height: 1.25;
  text-align: left;
}

.ask-analytics button:hover,
.ask-analytics button:focus-visible {
  color: var(--brand);
  text-decoration: underline;
}

.company-strip {
  grid-template-columns: minmax(220px, 0.6fr) repeat(3, minmax(0, 1fr));
  align-items: center;
}

.company-strip .panel-title {
  width: auto;
}

.company-row {
  border-top: 0;
  padding-top: 0;
}

.company-row i {
  display: grid;
  flex: 0 0 34px;
  height: 34px;
  place-items: center;
  border-radius: 50%;
  color: #ffffff;
  background: var(--success);
  font-style: normal;
  font-weight: 800;
}

.company-row i.medium {
  background: var(--warning);
}

.company-row i.high {
  background: var(--danger);
}

.next-action {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  padding: 16px 18px;
}

.next-action strong {
  display: block;
  margin-top: 4px;
  font-size: 13.5px;
  line-height: 1.35;
  font-weight: 700;
}

.next-action .button-link {
  flex: 0 0 auto;
  white-space: nowrap;
}

.analytics-modal-backdrop {
  position: fixed;
  z-index: 1000;
  inset: 0;
  display: grid;
  place-items: center;
  padding: 24px;
  background: rgb(15 23 42 / 38%);
  backdrop-filter: blur(4px);
}

.analytics-modal {
  display: grid;
  gap: 18px;
  width: min(760px, 100%);
  max-height: min(820px, calc(100vh - 48px));
  overflow: auto;
  border: 1px solid var(--line);
  border-radius: 14px;
  padding: 22px;
  background: var(--surface-solid);
  box-shadow: 0 30px 80px rgb(15 23 42 / 24%);
}

.analytics-modal > header,
.analytics-modal > footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.analytics-modal h3,
.analytics-modal p {
  margin: 0;
}

.analytics-modal h3 {
  font-size: 20px;
}

.analytics-modal-close {
  display: grid;
  width: 36px;
  height: 36px;
  place-items: center;
  border-radius: 50%;
  padding: 0;
  font-size: 24px;
  line-height: 1;
}

.analytics-modal-summary {
  color: var(--text);
  font-size: 14px;
  line-height: 1.55;
}

.analytics-modal-metrics {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  margin: 0;
}

.analytics-modal-metrics div {
  min-width: 0;
  border-radius: 10px;
  padding: 12px;
  background: var(--surface-muted);
}

.analytics-modal-metrics dt,
.analytics-modal > footer {
  color: var(--muted);
  font-size: 11px;
}

.analytics-modal-metrics dd {
  margin: 5px 0 0;
  font-size: 15px;
  font-weight: 800;
  overflow-wrap: anywhere;
}

.analytics-modal-rows {
  display: grid;
  gap: 0;
  border-top: 1px solid var(--line-soft);
}

.analytics-modal-rows article {
  display: grid;
  grid-template-columns: minmax(130px, 0.42fr) minmax(0, 1fr);
  gap: 16px;
  border-bottom: 1px solid var(--line-soft);
  padding: 12px 2px;
}

.analytics-modal-rows span {
  color: var(--muted);
  overflow-wrap: anywhere;
}

.empty {
  margin: 0;
  padding: 16px;
  color: var(--muted);
  text-align: center;
}

.empty.compact {
  padding: 8px 0 0;
  text-align: left;
}

.forecast-breakdowns {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr)) minmax(240px, .7fr);
  gap: 14px;
}

.forecast-breakdowns > .analytics-panel {
  display: grid;
  align-content: start;
  gap: 10px;
}

.forecast-scope-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  border-top: 1px solid var(--color-border-subtle);
  padding-top: 10px;
}

.forecast-scope-row div {
  display: grid;
  gap: 3px;
}

.forecast-scope-row small {
  color: var(--color-text-muted);
}

.forecast-quality dl {
  display: grid;
  gap: 8px;
  margin: 0;
}

.forecast-quality dl div {
  display: flex;
  justify-content: space-between;
  gap: 12px;
}

@media (max-width: 1320px) {
  .analytics-top-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .ai-summary-card {
    grid-column: span 2;
  }

  .company-strip {
    grid-template-columns: 1fr;
  }

  .forecast-breakdowns {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .forecast-quality {
    grid-column: 1 / -1;
  }
}

@media (max-width: 860px) {
  .analytics-head,
  .next-action {
    align-items: stretch;
    flex-direction: column;
  }

  .analytics-main-grid,
  .analytics-main-grid.lower {
    grid-template-columns: 1fr;
  }

  .forecast-breakdowns {
    grid-template-columns: 1fr;
  }

  .forecast-quality {
    grid-column: auto;
  }

  .analytics-actions,
  .next-action .button-link {
    width: 100%;
  }

  .analytics-actions button {
    flex: 1;
  }

  .funnel-list article {
    grid-template-columns: 1fr;
  }

  .funnel-list small {
    text-align: left;
  }
}

@media (max-width: 560px) {
  .analytics-top-grid {
    grid-template-columns: 1fr;
  }

  .ai-summary-card {
    grid-column: auto;
  }

  .analytics-modal-backdrop {
    align-items: end;
    padding: 0;
  }

  .analytics-modal {
    width: 100%;
    max-height: 92vh;
    border-radius: 16px 16px 0 0;
    padding: 18px;
  }

  .analytics-modal-metrics {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .analytics-modal-rows article {
    grid-template-columns: 1fr;
    gap: 4px;
  }
}
</style>
