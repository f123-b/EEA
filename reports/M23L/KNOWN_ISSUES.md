# M23L Known Issues

- The original PR #15 contains the complete integrated development history and
  is intentionally not a direct merge candidate.
- Landing branches use additive compatibility migrations because the original
  integrated migration order was interleaved. Historical migration files are
  preserved and not rewritten.
- The local default `.eea/eea.db` may reference an older unavailable migration;
  clean temporary databases are used for landing verification.
- The local Windows MSI target rejects the existing nonnumeric `dev` prerelease
  segment; the required Windows NSIS and Linux AppImage CI artifacts remain the
  release contract.

No P0/P1 product or security issue is known after the landing repairs.
