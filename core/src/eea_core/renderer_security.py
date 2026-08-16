"""Core-neutral renderer security contracts for untrusted engineering content."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import SplitResult, urlsplit


class RendererContentRejectedError(ValueError):
    """Raised when a renderer security policy cannot safely handle content or a URL."""


RendererContentRejected = RendererContentRejectedError


class SanitizedRenderContent(str):
    """Branded plain-text content safe to pass to a renderer as text children."""


class _PlainTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if tag.lower() in {"script", "style", "template", "iframe", "object", "embed"}:
            self._ignored_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "template", "iframe", "object", "embed"}:
            self._ignored_depth = max(0, self._ignored_depth - 1)

    def handle_data(self, data: str) -> None:
        if self._ignored_depth == 0:
            self.parts.append(data)


_DANGEROUS_URI = re.compile(r"(?:javascript\s*:|vbscript\s*:|data\s*:\s*text/html)", re.I)
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def sanitize_untrusted_content(value: str, *, max_chars: int = 1_000_000) -> SanitizedRenderContent:
    """Return bounded plain text; no HTML is ever emitted as executable markup."""

    if not isinstance(value, str):
        raise RendererContentRejected("untrusted renderer content must be text")
    if max_chars < 1:
        raise RendererContentRejected("renderer content limit must be positive")
    parser = _PlainTextParser()
    parser.feed(value[: max_chars + 1])
    parser.close()
    text = _CONTROL_CHARS.sub("", "".join(parser.parts)).replace("\r\n", "\n")
    text = _DANGEROUS_URI.sub("[blocked-url]", text)
    if len(text) > max_chars:
        text = text[:max_chars] + "\n[content truncated]"
    return SanitizedRenderContent(text)


@dataclass(frozen=True, slots=True)
class RendererSecurityPolicy:
    """The immutable security boundary shared by web and Tauri renderers."""

    allowed_external_hosts: frozenset[str] = field(default_factory=frozenset)
    allowed_external_schemes: frozenset[str] = field(
        default_factory=lambda: frozenset({"http", "https"})
    )
    localhost_hosts: frozenset[str] = field(
        default_factory=lambda: frozenset({"127.0.0.1", "::1", "localhost"})
    )
    remote_javascript_allowed: bool = False
    remote_frames_allowed: bool = False

    def validate(self) -> None:
        if self.remote_javascript_allowed or self.remote_frames_allowed:
            raise RendererContentRejected("remote renderer execution is prohibited")
        if not self.allowed_external_schemes <= {"http", "https"}:
            raise RendererContentRejected("external link schemes must be HTTP(S) only")
        if any(not host or host != host.lower() for host in self.allowed_external_hosts):
            raise RendererContentRejected("external host allowlist must contain lowercase hosts")

    def validate_external_link(self, value: str) -> SplitResult:
        self.validate()
        parsed = urlsplit(value)
        if parsed.scheme.lower() not in self.allowed_external_schemes:
            raise RendererContentRejected("external link scheme is not allowed")
        if not parsed.hostname or parsed.username or parsed.password:
            raise RendererContentRejected("external link authority is not allowed")
        host = parsed.hostname.lower().rstrip(".")
        if host not in self.allowed_external_hosts:
            raise RendererContentRejected("external link host is not allowlisted")
        if parsed.fragment and parsed.fragment.lower().startswith("javascript"):
            raise RendererContentRejected("external link fragment is not allowed")
        return parsed

    def validate_csp(self, csp: str) -> None:
        lowered = csp.lower()
        forbidden = ("connect-src *", "script-src *", "data:text/html")
        sources = lowered.replace(";", " ").split()
        broad_schemes = {"http:", "https:", "ws:", "wss:", "*"}
        remote_sources = tuple(
            source
            for source in sources
            if source.startswith(("http://", "https://", "ws://", "wss://"))
            and not source.startswith(
                ("http://127.0.0.1:", "http://[::1]:", "ws://127.0.0.1:", "ws://[::1]:")
            )
        )
        if (
            any(value in lowered for value in forbidden)
            or any(source in broad_schemes for source in sources)
            or remote_sources
        ):
            raise RendererContentRejected("CSP widens the renderer trust boundary")
        if "object-src 'none'" not in lowered or "frame-src 'none'" not in lowered:
            raise RendererContentRejected("CSP must deny object and frame navigation")


def default_renderer_csp() -> str:
    """Return the production CSP; loopback is the only backend connection target."""

    return (
        "default-src 'self'; base-uri 'self'; form-action 'self'; object-src 'none'; "
        "frame-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' blob:; "
        "connect-src 'self' http://127.0.0.1:* http://[::1]:* ws://127.0.0.1:* ws://[::1]:*"
    )


__all__ = [
    "RendererContentRejected",
    "RendererSecurityPolicy",
    "SanitizedRenderContent",
    "default_renderer_csp",
    "sanitize_untrusted_content",
]
