import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, createApiClient } from "./client";

afterEach(() => vi.unstubAllGlobals());

describe("API client", () => {
  it("adds the bearer token without overwriting caller headers", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const request = createApiClient({ baseUrl: "https://example.test", getToken: () => "token" });

    await request("/patients", { headers: { "X-Request-ID": "request-id" } });

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    const headers = init.headers as Headers;
    expect(headers.get("Authorization")).toBe("Bearer token");
    expect(headers.get("X-Request-ID")).toBe("request-id");
  });

  it("clears authentication and exposes a typed error on 401", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: "Expired" }), {
          status: 401,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );
    const onUnauthorized = vi.fn();
    const request = createApiClient({
      baseUrl: "https://example.test",
      getToken: () => "expired",
      onUnauthorized,
    });

    await expect(request("/patients")).rejects.toEqual(new ApiError(401, "Expired"));
    expect(onUnauthorized).toHaveBeenCalledOnce();
  });
});

