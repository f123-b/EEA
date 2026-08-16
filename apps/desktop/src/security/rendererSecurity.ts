/** Renderer-side boundary for untrusted repository, Markdown, log and issue content. */

declare const sanitizedRenderContentBrand: unique symbol;
export type SanitizedRenderContent = string & {
  readonly [sanitizedRenderContentBrand]: "SanitizedRenderContent";
};

const dangerousUri = /(?:javascript\s*:|vbscript\s*:|data\s*:\s*text\/html)/giu;
const dangerousMarkup = /<\/?[a-z][^>]*>/giu;

function removeControlChars(value: string): string {
  return Array.from(value)
    .filter((character) => {
      const code = character.charCodeAt(0);
      return !(
        code <= 0x08 ||
        code === 0x0b ||
        code === 0x0c ||
        (code >= 0x0e && code <= 0x1f) ||
        code === 0x7f
      );
    })
    .join("");
}

/**
 * Convert untrusted markup to bounded plain text. React must render this only as a text child;
 * there is intentionally no HTML rendering escape hatch in the desktop application.
 */
export function sanitizeUntrustedContent(value: string, maxChars = 1_000_000): SanitizedRenderContent {
  if (typeof value !== "string" || maxChars < 1) {
    throw new Error("renderer content must be bounded text");
  }
  const text = removeControlChars(
    value.slice(0, maxChars + 1).replace(dangerousMarkup, "").replace(dangerousUri, "[blocked-url]")
  );
  const bounded = text.length > maxChars ? `${text.slice(0, maxChars)}\n[content truncated]` : text;
  return bounded as SanitizedRenderContent;
}

export type RendererSecurityPolicy = Readonly<{
  allowedExternalHosts: ReadonlySet<string>;
  allowRemoteJavascript: false;
  allowRemoteFrames: false;
}>;

export const rendererSecurityPolicy: RendererSecurityPolicy = Object.freeze({
  allowedExternalHosts: new Set<string>(),
  allowRemoteJavascript: false,
  allowRemoteFrames: false,
});

export function validateExternalLink(value: string, policy = rendererSecurityPolicy): string {
  const url = new URL(value);
  if (url.protocol !== "http:" && url.protocol !== "https:") {
    throw new Error("only HTTP(S) external links are allowed");
  }
  if (url.username || url.password || /javascript/i.test(url.hash)) {
    throw new Error("external link authority is not allowed");
  }
  if (!policy.allowedExternalHosts.has(url.hostname.toLowerCase())) {
    throw new Error("external link host is not allowlisted");
  }
  return url.toString();
}

/** Open through the OS browser; the main WebView never navigates to the URL. */
export async function openExternalLink(value: string): Promise<void> {
  const safeUrl = validateExternalLink(value);
  const { openUrl } = await import("@tauri-apps/plugin-opener");
  await openUrl(safeUrl);
}

export function safeExternalLinkProps(value: string): { href: string; target: "_blank"; rel: "noreferrer noopener" } {
  return { href: validateExternalLink(value), target: "_blank", rel: "noreferrer noopener" };
}
