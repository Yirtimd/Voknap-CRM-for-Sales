<script setup lang="ts">
import { computed, onMounted } from "vue";

import { crmStore } from "../stores/crm";
import type { Activity } from "../types";

onMounted(() => {
  void crmStore.refreshActivities();
});

const groupedActivities = computed(() => {
  const groups: Record<string, Activity[]> = {};
  for (const activity of crmStore.activities.value) {
    const label = dateLabel(activity.created_at);
    groups[label] = groups[label] ?? [];
    groups[label].push(activity);
  }
  return groups;
});

function dateLabel(value: string) {
  const date = new Date(value);
  const today = new Date();
  const yesterday = new Date();
  yesterday.setDate(today.getDate() - 1);

  if (date.toDateString() === today.toDateString()) return "Today";
  if (date.toDateString() === yesterday.toDateString()) return "Yesterday";
  return date.toLocaleDateString("ru-RU", { day: "2-digit", month: "long", year: "numeric" });
}

function icon(type: string) {
  const map: Record<string, string> = {
    EMAIL: "@",
    CALL: "C",
    MEETING: "M",
    TASK: "T",
    NOTE: "N",
    DEAL_STAGE_CHANGED: "D",
    FILE: "F",
    COMMENT: "C",
    SYSTEM: "S",
    AI_ACTION: "AI",
    CADENCE: "→"
  };
  return map[type] ?? "•";
}
</script>

<template>
  <section class="section-grid">
    <form class="panel" @submit.prevent="crmStore.createActivity">
      <h2>Добавить activity</h2>
      <label>Компания
        <select v-model="crmStore.activityForm.value.company_id" required>
          <option value="">Выбрать</option>
          <option v-for="company in crmStore.companies.value" :key="company.id" :value="company.id">{{ company.name }}</option>
        </select>
      </label>
      <label>Тип
        <select v-model="crmStore.activityForm.value.type">
          <option>EMAIL</option>
          <option>CALL</option>
          <option>MEETING</option>
          <option>TASK</option>
          <option>NOTE</option>
          <option>DEAL_STAGE_CHANGED</option>
          <option>FILE</option>
          <option>COMMENT</option>
          <option>SYSTEM</option>
          <option>AI_ACTION</option>
          <option>CADENCE</option>
        </select>
      </label>
      <label>Заголовок<input v-model="crmStore.activityForm.value.title" /></label>
      <label>Описание<textarea v-model="crmStore.activityForm.value.description"></textarea></label>
      <label>Контакт
        <select v-model="crmStore.activityForm.value.contact_id">
          <option value="">Без контакта</option>
          <option
            v-for="contact in crmStore.contacts.value.filter((item) => item.company_id === crmStore.activityForm.value.company_id)"
            :key="contact.id"
            :value="contact.id"
          >{{ contact.name }}</option>
        </select>
      </label>
      <label>Сделка
        <select v-model="crmStore.activityForm.value.deal_id">
          <option value="">Без сделки</option>
          <option
            v-for="deal in crmStore.deals.value.filter((item) => item.company_id === crmStore.activityForm.value.company_id)"
            :key="deal.id"
            :value="deal.id"
          >{{ deal.title }}</option>
        </select>
      </label>
      <button type="submit">Добавить</button>
    </form>

    <section class="panel wide">
      <h2>Timeline</h2>
      <div v-for="(items, group) in groupedActivities" :key="group" class="timeline-group">
        <h3>{{ group }}</h3>
        <article v-for="activity in items" :key="activity.id" class="timeline-item">
          <span class="timeline-icon">{{ icon(activity.type) }}</span>
          <div>
            <header>
              <strong>{{ activity.title }}</strong>
              <small>{{ activity.type }} · {{ new Date(activity.created_at).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" }) }}</small>
            </header>
            <p v-if="activity.description">{{ activity.description }}</p>
          </div>
        </article>
      </div>
      <p v-if="!crmStore.activities.value.length" class="empty">Timeline пуст</p>
    </section>
  </section>
</template>
