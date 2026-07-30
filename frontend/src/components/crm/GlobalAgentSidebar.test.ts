import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { crmStore } from "../../stores/crm";
import GlobalAgentSidebar from "./GlobalAgentSidebar.vue";


beforeEach(() => {
  crmStore.knowledgeDocuments.value = [{
    id: "document-1",
    title: "Коммерческие условия",
    source_type: "pdf",
    visibility: "global",
    status: "ready",
    created_at: "2026-07-30T00:00:00Z",
    chunks_count: 3,
    download_url: "/knowledge/documents/document-1/download"
  }];
  crmStore.agentContext.value = {
    type: "document",
    company_id: null,
    deal_id: null,
    document_id: "document-1",
    include_global: false,
    page_path: "/knowledge"
  };
  crmStore.agentHistory.value = [{
    id: "message-1",
    role: "assistant",
    content: "Оплата производится за десять рабочих дней.",
    intent: "knowledge",
    context: crmStore.agentContext.value,
    query_id: "query-1",
    created_at: "2026-07-30T00:00:00Z",
    sources: [{
      document_id: "document-1",
      document_title: "Коммерческие условия",
      document_scope: "global",
      company_id: null,
      deal_id: null,
      chunk_id: "chunk-1",
      chunk_index: 0,
      page_number: 4,
      score: 0.91,
      text: "Оплата производится за десять рабочих дней.",
      retrieval_method: "hybrid",
      download_url: "/knowledge/documents/document-1/download"
    }]
  }];
  crmStore.agentActions.value = [];
  crmStore.agentForm.value.message = "";
  crmStore.isLoading.value = false;
});

afterEach(() => vi.restoreAllMocks());

describe("GlobalAgentSidebar", () => {
  it("shows active document context, citations and feedback", async () => {
    vi.spyOn(crmStore, "refreshAgent").mockResolvedValue();
    const feedback = vi.spyOn(crmStore, "sendAgentFeedback").mockResolvedValue();
    const wrapper = mount(GlobalAgentSidebar, { props: { open: true } });
    await flushPromises();

    expect(wrapper.text()).toContain("Коммерческие условия");
    expect(wrapper.text()).toContain("стр. 4");
    expect(wrapper.text()).toContain("Ответ полезен?");

    const feedbackButtons = wrapper.findAll(".agent-feedback button");
    await feedbackButtons[0].trigger("click");
    expect(feedback).toHaveBeenCalledWith("query-1", "up");
  });

  it("gives chat most space and hides starter prompts after messages exist", async () => {
    vi.spyOn(crmStore, "refreshAgent").mockResolvedValue();
    const wrapper = mount(GlobalAgentSidebar, { props: { open: true } });
    await flushPromises();

    expect(wrapper.text()).toContain("AI-ассистент");
    expect(wrapper.find(".agent-messages").exists()).toBe(true);
    expect(wrapper.find(".agent-starters").exists()).toBe(false);
    expect(wrapper.find(".agent-summary").exists()).toBe(false);

    await wrapper.get('[aria-label="Новый чат"]').trigger("click");
    expect(wrapper.find(".agent-starters").exists()).toBe(true);
    expect(wrapper.text()).toContain("Сделай выжимку документа");
  });

  it("opens actions in a separate view and supports wide mode", async () => {
    crmStore.agentActions.value = [{
      id: "action-1",
      action_type: "create_task",
      status: "pending",
      payload: { title: "Позвонить клиенту", due_at: "2026-08-01" },
      result: null,
      created_at: "2026-07-30T00:00:00Z",
      confirmed_at: null
    }];
    vi.spyOn(crmStore, "refreshAgent").mockResolvedValue();
    const wrapper = mount(GlobalAgentSidebar, { props: { open: true } });
    await flushPromises();

    const actionsTab = wrapper.findAll('[role="tab"]').find((item) => item.text().includes("Действия"));
    await actionsTab!.trigger("click");
    expect(wrapper.text()).toContain("Позвонить клиенту");
    expect(wrapper.text()).toContain("Подтвердить действие");
    expect(wrapper.find(".agent-composer").exists()).toBe(false);

    await wrapper.get('[aria-label="Развернуть AI-ассистента"]').trigger("click");
    expect(wrapper.get(".agent-sidebar").classes()).toContain("is-wide");
  });
});
