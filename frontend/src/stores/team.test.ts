import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { crmStore } from "./crm";
import { teamStore } from "./team";

function response(data: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: new Headers(),
    json: vi.fn().mockResolvedValue(data),
    text: vi.fn().mockResolvedValue(typeof data === "string" ? data : JSON.stringify(data))
  };
}

beforeEach(() => {
  crmStore.token.value = "token-1";
  crmStore.tenantId.value = "tenant-1";
  crmStore.me.value = {
    user_id: "owner-user",
    email: "owner@example.test",
    full_name: "Owner",
    tenant_id: "tenant-1",
    role: "owner",
    permissions: ["crm:read", "crm:write", "members:manage", "assignments:manage"]
  };
  teamStore.members.value = [];
  teamStore.invitations.value = [];
  teamStore.teams.value = [];
  teamStore.queues.value = [];
  teamStore.territories.value = [];
  teamStore.assignmentRules.value = [];
  teamStore.invitationLinks.value = {};
  teamStore.clearMessages();
});

afterEach(() => vi.unstubAllGlobals());

describe("team store", () => {
  it("loads only permission-backed team management lists", async () => {
    const fetchMock = vi.fn().mockImplementation((url: string) => response([]));
    vi.stubGlobal("fetch", fetchMock);

    await teamStore.refreshAll();

    expect(fetchMock).toHaveBeenCalledTimes(6);
    const urls = fetchMock.mock.calls.map(([url]) => String(url));
    expect(urls).toEqual(expect.arrayContaining([
      "/api/accounts/members",
      "/api/accounts/invitations",
      "/api/accounts/teams",
      "/api/accounts/queues",
      "/api/accounts/territories",
      "/api/accounts/assignment-rules"
    ]));
  });

  it("does not request protected lists without /me permissions", async () => {
    crmStore.me.value = { ...crmStore.me.value!, role: "viewer", permissions: ["crm:read"] };
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    await teamStore.refreshAll();

    expect(fetchMock).not.toHaveBeenCalled();
    expect(teamStore.canOpen.value).toBe(false);
  });

  it("keeps owner access when an older /me response omits new permission strings", async () => {
    crmStore.me.value = {
      user_id: "owner-1",
      email: "owner@example.com",
      full_name: "Owner",
      tenant_id: "tenant-1",
      role: "owner",
      permissions: ["crm:read", "crm:write"]
    };
    const fetchMock = vi.fn().mockResolvedValue(response([]));
    vi.stubGlobal("fetch", fetchMock);

    await teamStore.refreshAll();

    expect(teamStore.canManageMembers.value).toBe(true);
    expect(teamStore.canManageAssignments.value).toBe(true);
    expect(fetchMock).toHaveBeenCalledTimes(6);
  });

  it("keeps one-time invitation link after list refresh", async () => {
    const invitation = {
      id: "invite-1",
      email: "rep@example.test",
      role: "sales_rep",
      team_id: null,
      manager_membership_id: null,
      expires_at: "2026-08-01T00:00:00Z",
      accepted_at: null,
      revoked_at: null,
      created_at: "2026-07-19T00:00:00Z",
      token: "tenant-1.one-time-token-value-long-enough"
    };
    const fetchMock = vi.fn().mockImplementation((_url: string, options: RequestInit) =>
      options.method === "POST" ? response(invitation, 201) : response([{ ...invitation, token: null }])
    );
    vi.stubGlobal("fetch", fetchMock);

    await teamStore.createInvitation({ email: invitation.email, role: "sales_rep", expires_in_hours: 72 });

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(teamStore.invitationLinks.value[invitation.id]).toContain("/accept-invitation?token=");
    expect(teamStore.invitations.value[0].token).toBeNull();
  });

  it("sends mandatory replacement user during deactivation", async () => {
    const member = {
      id: "membership-1",
      user_id: "user-1",
      email: "rep@example.test",
      full_name: "Rep",
      role: "sales_rep",
      is_active: false,
      team_id: null,
      manager_membership_id: null,
      deactivated_at: "2026-07-19T00:00:00Z",
      created_at: "2026-01-01T00:00:00Z"
    };
    const fetchMock = vi.fn().mockImplementation((_url: string, options: RequestInit) =>
      options.method === "PATCH" ? response(member) : response([member])
    );
    vi.stubGlobal("fetch", fetchMock);

    await teamStore.updateMemberStatus(member.id, false, "replacement-user");

    expect(JSON.parse(String(fetchMock.mock.calls[0][1].body))).toEqual({
      is_active: false,
      reassign_to_user_id: "replacement-user"
    });
    expect(teamStore.members.value[0].is_active).toBe(false);
  });

  it("normalizes conflict errors and does not hide HTTP status meaning", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response({ detail: "Manager hierarchy cycle" }, 409)));

    await expect(teamStore.updateMemberStructure("member-1", null, "member-2")).rejects.toMatchObject({ status: 409 });

    expect(teamStore.error.value).toBe("Конфликт данных: Manager hierarchy cycle");
  });

  it("accepts invitation through public auth endpoint", async () => {
    const fetchMock = vi.fn().mockResolvedValue(response({
      access_token: "new-token",
      token_type: "bearer",
      user_id: "user-2",
      tenant_id: "tenant-2"
    }));
    vi.stubGlobal("fetch", fetchMock);

    const result = await teamStore.acceptInvitation({ token: "tenant.long-one-time-token", full_name: "New User", password: "Invitation-Password-2026!" });

    expect(result.tenant_id).toBe("tenant-2");
    expect(fetchMock.mock.calls[0][0]).toBe("/api/auth/invitations/accept");
    expect(fetchMock.mock.calls[0][1].headers).not.toHaveProperty("Authorization");
  });
});
