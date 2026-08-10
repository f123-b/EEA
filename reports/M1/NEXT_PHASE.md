# M1 Next Phase

## Target

M2 AI Provider Foundation.

## Scope

- `AIProvider` Port
- LiteLLM Adapter behind the Port
- `SecretService` boundary
- versioned Prompt Registry
- `StructuredGenerationService`
- Pydantic output validation
- usage and budget accounting
- provider failure, timeout, budget, and secret-leak tests

M2 does not include full LangGraph/multi-agent orchestration; that remains M28.

## Dependencies

- Accepted M1 Core entities, schema registry, JobStatus, Permission, and engineering errors
- Security and Secret rules in `docs/07_SECURITY_PERMISSION_SPEC.md`
- AI Provider layering in `docs/01_TECHNICAL_SPEC.md`

## V1.3.1 sequencing

FIX-02 Canonical Unit remains scheduled with M3 and must pass before M7. No later FIX is pulled
forward into M2 without its first-use dependency.

## Blockers

None for a mock-provider-backed M2 contract and tests. A real provider integration will require a
user-configured secret but must remain optional and must not block the deterministic test suite.
