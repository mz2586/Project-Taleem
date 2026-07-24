import { afterEach, describe, expect, it, vi } from "vitest";

import { createApiClient } from "../apiClient";
import { ApiError } from "../student/types";

const BASE = "http://api.test";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("createApiClient", () => {
  it("attaches the bearer token and parses JSON", async () => {
    const fetchMock = vi.fn(
      async (_url: string, _init?: RequestInit) =>
        new Response(JSON.stringify({ ok: 1 }), { status: 200 }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const client = createApiClient(BASE, () => "tok-123");
    const body = await client.get<{ ok: number }>("/v1/guardian/me");
    expect(body.ok).toBe(1);
    const call = fetchMock.mock.calls[0]!;
    expect(call[0]).toBe(`${BASE}/v1/guardian/me`);
    expect(call[1]?.headers).toMatchObject({ authorization: "Bearer tok-123" });
  });

  it("omits the auth header when there is no token", async () => {
    const fetchMock = vi.fn(
      async (_url: string, _init?: RequestInit) => new Response("{}", { status: 200 }),
    );
    vi.stubGlobal("fetch", fetchMock);
    await createApiClient(BASE, () => "").get("/x");
    const headers = fetchMock.mock.calls[0]![1]?.headers as Record<string, string>;
    expect(headers.authorization).toBeUndefined();
  });

  it("throws a status-0 ApiError on network failure (offline)", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => {
      throw new TypeError("network down");
    }));
    const client = createApiClient(BASE, () => "t");
    await expect(client.get("/x")).rejects.toMatchObject({ status: 0 });
  });

  it("surfaces a problem+json error with its status", async () => {
    vi.stubGlobal("fetch", vi.fn(async () =>
      new Response(JSON.stringify({ code: "FORBIDDEN" }), { status: 403 }),
    ));
    const client = createApiClient(BASE, () => "t");
    await expect(client.get("/x")).rejects.toBeInstanceOf(ApiError);
    await expect(client.get("/x")).rejects.toMatchObject({ status: 403 });
  });

  it("returns undefined for 204 No Content", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(null, { status: 204 })));
    const client = createApiClient(BASE, () => "t");
    expect(await client.post("/x")).toBeUndefined();
  });
});
