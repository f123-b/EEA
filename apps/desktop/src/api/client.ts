/** Loopback API client; the launch credential is held in closure state only. */

export type BackendClient = Readonly<{
  request: (path: string, init?: RequestInit) => Promise<Response>;
}>;

function validateLoopbackBaseUrl(value: string): string {
  const url = new URL(value);
  if (url.protocol !== "http:" || !["127.0.0.1", "[::1]", "localhost"].includes(url.hostname)) {
    throw new Error("backend must use an HTTP loopback URL");
  }
  return url.toString().replace(/\/$/u, "");
}

/** No localStorage, DOM attribute, query parameter, log, or telemetry receives the token. */
export function createBackendClient(baseUrl: string, launchToken: string): BackendClient {
  const safeBaseUrl = validateLoopbackBaseUrl(baseUrl);
  if (!launchToken || /[\r\n]/u.test(launchToken)) {
    throw new Error("backend launch token is invalid");
  }
  return Object.freeze({
    request: async (path: string, init: RequestInit = {}): Promise<Response> => {
      if (!path.startsWith("/") || path.includes("?token=") || path.includes("#token=")) {
        throw new Error("backend request path is invalid");
      }
      const headers = new Headers(init.headers);
      headers.set("Authorization", `Bearer ${launchToken}`);
      headers.set("Accept", "application/json");
      return fetch(`${safeBaseUrl}${path}`, { ...init, headers });
    },
  });
}
