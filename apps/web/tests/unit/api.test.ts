import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiFetch, ApiError, getAccessToken, setAccessToken } from "@/lib/api";

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

beforeEach(() => {
  setAccessToken(null);
  vi.restoreAllMocks();
});

describe("apiFetch", () => {
  it("prefixes /api/v1 and attaches the bearer token", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ ok: true }));
    vi.stubGlobal("fetch", fetchMock);
    setAccessToken("tok123");

    const result = await apiFetch<{ ok: boolean }>("/cases");
    expect(result).toEqual({ ok: true });

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/v1/cases");
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer tok123");
  });

  it("transparently refreshes on 401 and retries", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ detail: "expired" }, 401)) // original
      .mockResolvedValueOnce(jsonResponse({ access_token: "fresh" }, 200)) // refresh
      .mockResolvedValueOnce(jsonResponse({ ok: true }, 200)); // retry
    vi.stubGlobal("fetch", fetchMock);
    setAccessToken("stale");

    const result = await apiFetch<{ ok: boolean }>("/cases");
    expect(result).toEqual({ ok: true });
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(getAccessToken()).toBe("fresh");
    // the refresh hit the right endpoint
    expect(fetchMock.mock.calls[1][0]).toBe("/api/v1/auth/refresh");
  });

  it("throws ApiError carrying the server detail", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ detail: "not allowed" }, 403)));
    const err = (await apiFetch("/cases").catch((e) => e)) as ApiError;
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(403); // Error.message is non-enumerable, so assert fields directly
    expect(err.message).toBe("not allowed");
  });

  it("does not attempt refresh for auth endpoints", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ detail: "bad creds" }, 401));
    vi.stubGlobal("fetch", fetchMock);
    await expect(apiFetch("/auth/login", { method: "POST", body: {} })).rejects.toMatchObject({
      status: 401,
    });
    expect(fetchMock).toHaveBeenCalledTimes(1); // no refresh retry
  });
});
