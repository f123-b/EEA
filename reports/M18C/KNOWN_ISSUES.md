# M18C Known Issues

## Non-blocking pre-existing environment issue

Two existing M5 sandbox tests fail only in the current Windows sandbox environment:

- `test_structured_command_is_allowlisted_and_shell_free`
- `test_structured_command_enforces_timeout_output_and_secret_boundaries`

Classification: `PRE-EXISTING / ENVIRONMENT-SPECIFIC / NON-BLOCKING`.
No M18C code or contract change was made to hide, weaken, or reclassify these failures.

## Acceptance boundary

No M18C implementation blocker remains in the local verification listed in
`TEST_REPORT.md`. The source workspace is the only editable source-byte authority;
database rows retain metadata, manifests, proposals, ownership, and recovery markers,
not a second editable source tree.

M18C is accepted at reviewed final HEAD
`6cc9b7057c5c210396ae4b2fcfdf5c5e6cd4baac`. M18D is not started.
