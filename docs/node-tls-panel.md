# Panel node TLS configuration

The panel stores two verification fields and no mode field. A nonempty
`certificate_sha256` selects leaf certificate pinning, otherwise a nonempty
`server_ca` selects legacy PEM verification. With neither field, verification
uses system trust. There is no trial-and-error fallback.

## Bridge release prerequisite

The currently locked `pasarguard-node-bridge` 0.10.0 does **not** implement the
migration's fingerprint or empty-PEM system trust policies. The panel preserves
legacy PEM operation with that release, but refuses to construct connections
for the two new policies and reports an explicit bridge upgrade error. This
also applies when both PEM and a pin are saved: it never ignores the pin.

Before enabling the new policies in production, release and lock a bridge
that accepts the keyword-only `certificate_sha256` argument and implements
section 4 of `node-tls-migration-plan.md`. Upgrade every panel worker. Real TLS
acceptance tests for REST, gRPC, maintenance, streams, and supported proxies
must pass against that bridge. These transport guarantees cannot be validated
with 0.10.0; this panel change does not implement them inside the transport
library or claim an unavailable release version.

## API and dashboard

Create requests may omit PEM and the fingerprint. Fingerprints accept 64 hex
characters or 32 colon-separated byte pairs, case-insensitively, and are stored
as lowercase hex. They identify the complete leaf certificate DER, not its key.
Invalid nonempty PEM and fingerprints are rejected even when both fields are
provided.

On updates, omitted verification fields retain their saved values.
`certificate_sha256: null` or `""` clears a pin. `server_ca: ""` clears PEM;
`server_ca: null` retains PEM for compatibility. Clearing a pin while retaining
PEM restores legacy verification.

The dashboard infers its selector using fingerprint precedence and saves:

| Selection | `server_ca` | `certificate_sha256` |
| --- | --- | --- |
| Trusted certificate | `""` | `null` |
| SHA-256 fingerprint | `""` | Normalized fingerprint |
| Legacy PEM certificate | PEM | `null` |

For records with both fields, PEM is inactive. Saving the fingerprint form
clears it. Status and bulk actions preserve both saved fields. Verification
changes replace the bridge object and retire the old local connections.

All panel connections target TLS endpoints. When a reverse proxy terminates
TLS, the configured address and separate main/maintenance ports identify that
frontend. Pinned frontends must present the same leaf certificate on both
ports. The bridge must check its dates and SAN identity before sending
credentials. Plaintext node backends are configured in the node repository;
the panel has no plaintext or ignore-errors option.

## Migration and rollback

The additive migration adds only nullable `nodes.certificate_sha256` (64
characters). It does not contact nodes, rewrite PEM, or derive pins.
Back up existing PEM before explicitly moving to system trust. Publicly
trusted ACME certificates should use system trust so renewal does not require
panel updates. Before running an older panel, restore usable PEM and remove
reliance on pin-only or system-trust-only records.
# TODO — on hold pending bridge implementation

Panel implementation is paused at the user's request until the bridge side
of `node-tls-migration-plan.md` is implemented. Preserve the current working
changes; do not release this migration as complete yet.

- [ ] Implement and publish bridge TLS policy support, including the optional
  keyword-only `certificate_sha256` argument and empty-PEM system trust.
- [ ] Update the panel bridge dependency and lockfile to that release.
- [ ] Verify pin precedence, certificate dates and SANs, system trust, redirects,
  and credential withholding on actual REST, gRPC, maintenance, streaming,
  reconnect, and supported proxy connections.
- [ ] Finish panel API/database regression tests and dashboard type checking;
  the previous verification run was interrupted and is not a completed pass.
- [ ] Review the compatibility guard in `app/node/bridge.py` against the final
  bridge API, then validate the complete migration before release.

