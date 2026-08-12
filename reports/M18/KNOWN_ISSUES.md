# M18 Known Issues

Date: 2026-08-12

## M18 implementation

No M18-specific automated test failures are known after the focused and full
verification gates.

The graph provider registry is intentionally explicit and fail-closed. Entity
types not registered by the application are not dynamically imported or queried;
their state remains unknown and requires a future explicit provider addition.

## Environment notes

The repository contains pre-existing Windows sandbox subprocess coverage that is
environment-sensitive when launched through the `uv` interpreter redirector.
That behavior is outside the M18 change surface, was not changed here, and the
authoritative Python 3.12.13 full suite passed with the existing sandbox tests.

No M18 acceptance or M18A readiness claim is made in this file.
