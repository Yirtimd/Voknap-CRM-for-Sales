import { expect, test, type Page } from "@playwright/test";

async function mockApi(page: Page) {
  await page.addInitScript(() => {
    localStorage.setItem("cmr_token", "agent-visual-token");
    localStorage.setItem("cmr_tenant_id", "00000000-0000-0000-0000-000000000001");
    localStorage.setItem("cmr_sidebar_mode", "full");
  });
  await page.route("**/api/**", async (route) => {
    const pathname = new URL(route.request().url()).pathname;
    if (pathname.endsWith("/me")) {
      await route.fulfill({
        json: {
          user_id: "agent-user",
          tenant_id: "00000000-0000-0000-0000-000000000001",
          email: "agent@voknap.test",
          full_name: "Дмитрий Тестов",
          role: "owner",
          permissions: ["crm:read", "crm:write", "ai:use"]
        }
      });
      return;
    }
    if (pathname.endsWith("/ai-agent/history")) {
      await route.fulfill({
        json: [{
          id: "message-1",
          role: "assistant",
          content: "Нашёл три сделки без следующего шага.",
          intent: "workspace",
          context: { type: "workspace" },
          query_id: "query-1",
          created_at: "2026-07-30T10:00:00Z",
          sources: []
        }]
      });
      return;
    }
    if (pathname.endsWith("/ai-agent/actions")) {
      await route.fulfill({
        json: [{
          id: "action-1",
          action_type: "create_task",
          status: "pending",
          payload: { title: "Позвонить клиенту", due_at: "2026-08-01" },
          result: null,
          created_at: "2026-07-30T10:00:00Z",
          confirmed_at: null
        }]
      });
      return;
    }
    if (pathname.includes("/ai-agent/home/copilot")) {
      await route.fulfill({ json: null });
      return;
    }
    await route.fulfill({ json: [] });
  });
}

test("AI sidebar prioritizes chat and becomes overlay", async ({ page }) => {
  await mockApi(page);
  await page.goto("/home");
  await page.waitForLoadState("networkidle");

  const initialViewport = page.viewportSize();
  if (initialViewport && initialViewport.width > 920) {
    const leftSidebar = page.locator("aside.sidebar");
    await page.locator(".content").evaluate((element) => {
      (element as HTMLElement).style.minHeight = "200vh";
    });
    await page.evaluate(() => window.scrollTo(0, 500));
    expect(Math.round((await leftSidebar.boundingBox())?.y ?? -1)).toBe(0);
    await page.evaluate(() => window.scrollTo(0, 0));
  }

  const contentWidth = await page.locator(".content").evaluate((element) => element.getBoundingClientRect().width);
  await page.getByRole("button", { name: "Открыть AI агента", exact: true }).click();

  const sidebar = page.locator(".agent-sidebar");
  await expect(sidebar).toBeVisible();
  await expect(page.getByRole("heading", { name: "AI-ассистент", exact: true })).toBeVisible();
  await expect(page.locator(".agent-summary")).toHaveCount(0);
  await expect(page.locator(".agent-messages")).toBeVisible();
  expect(await page.locator(".content").evaluate((element) => element.getBoundingClientRect().width)).toBe(contentWidth);

  const viewport = page.viewportSize();
  const sidebarBox = await sidebar.boundingBox();
  if (viewport && viewport.width <= 640) {
    expect(Math.round(sidebarBox?.width ?? 0)).toBe(viewport.width);
  } else {
    expect(Math.round(sidebarBox?.width ?? 0)).toBe(430);
    await page.getByRole("button", { name: "Развернуть AI-ассистента", exact: true }).click();
    await page.waitForTimeout(220);
    expect(Math.round((await sidebar.boundingBox())?.width ?? 0)).toBe(640);
  }

  await page.getByRole("button", { name: "Новый чат", exact: true }).click();
  await expect(page.getByText("Дай сводку по CRM", { exact: true })).toBeVisible();
  await page.getByRole("tab", { name: "Действия 1", exact: true }).click();
  const actionsBox = await page.locator(".agent-actions").boundingBox();
  expect(Math.round(actionsBox?.height ?? 0)).toBeGreaterThan((viewport?.height ?? 0) - 180);
  await expect(page.getByText("Позвонить клиенту", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Подтвердить действие", exact: true })).toBeVisible();
});
