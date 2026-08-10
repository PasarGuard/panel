# Multi-client subscription profiles

Subscription profiles are an opt-in replacement for a *single* legacy Xray or
Sing-box subscription response.  A host remains an endpoint (address,
transport and inbound); a profile owns client-side grouping, automatic choice
and routing.  Existing Clash, Xray and Sing-box subscription URLs are not
changed.

## Create a profile

In **Client templates**, create either **Xray Profile** or **Sing-box Profile**.
Its JSON is validated before it is saved.  The built-in starting point creates
`primary` and `fallback` pools:

```json
{
  "schema_version": 1,
  "default_pool": "primary",
  "pools": [
    { "id": "primary", "fallback_pool": "fallback" },
    { "id": "fallback" }
  ],
  "health_check": {
    "url": "https://www.gstatic.com/generate_204",
    "interval": "3m",
    "tolerance": 50,
    "timeout": "30m"
  },
  "routing_rules": [],
  "client": "generic"
}
```

Pool IDs are stable lowercase machine identifiers, not display names.  Each
enabled pool must contain at least one endpoint available to the previewed
user.  The default and fallback pools must be enabled.

## Classify endpoints

In a host's **Client profile classification** section set the `pool` and
optional ISO two-letter `country`.  The host's existing priority controls its
order inside that pool.  **Exclude from automatic groups** keeps an endpoint
visible in the pool selector while omitting it from health-tested auto groups.

Changing the host remark, randomized address, port, or SNI has no effect on
profile membership or generated tags.  The generator derives deterministic
`pg-proxy-*` tags from the stable host ID rather than a user-visible string.

## Give a user one profile

The explicit public endpoint is:

```text
/{SUBSCRIPTION_PATH}/{token}/profile/{profile_id}
```

It produces JSON based only on endpoints currently eligible for that user.
Disabled hosts and inactive users are rejected before grouping.  Admin preview
is `GET /api/user/{user_id}/subscription/profile/{profile_id}`; it is protected
by the normal user read permission and sends `Cache-Control: no-store`.

## Example: primary, fallback, and a country choice

1. Create an Xray Profile with `primary` as `default_pool` and
   `fallback_pool: "fallback"` on the primary pool.
2. On each host, set **Client profile classification** to `primary` or
   `fallback`, set `country` (for example `DE` or `FI`), and keep maintenance
   endpoints out of automatic probes with **Exclude from automatic groups**.
3. Preview the profile for one user, download
   `/{SUBSCRIPTION_PATH}/{token}/profile/{profile_id}`, and import that single
   JSON URL into an Xray/Sing-box client. The client receives `pg-auto-primary`
   and country groups such as `pg-country-de`; choose a specific Xray
   pool/country with a routing rule.
4. To return to the old subscription, remove `profile_id` from the matching
   subscription rule (or use the ordinary legacy URL). No host data or legacy
   template is converted or deleted; the next refresh uses the previous
   link/Xray/Sing-box/Clash generator unchanged.

## Output behavior

Xray profiles create one outbound per eligible endpoint, `observatory`, and a
routing balancer per pool/country.  A pool's `fallback_pool` is emitted as the
Xray balancer's `fallbackTag`, which must name a concrete fallback endpoint.
Xray has no Sing-box-style selector outbound; choose a pool/country by adding a
routing rule that points to `pg-auto-<pool>` or `pg-country-<country>`.

Sing-box profiles create selectors for non-empty pools and a separate `urltest`
only when that pool has automatic endpoints, then a top-level `proxy` selector.
This deliberately does **not** claim strict
`primary -> fallback` failover: Sing-box `urltest` chooses among the outbounds
in its own pool and has no Xray-style `fallbackTag`.  Users can still choose a
fallback pool explicitly.

For Sing-box, `health_check.timeout` is its `urltest.idle_timeout`; it must be
at least as long as `interval` (the default is `30m` for the default `3m`
interval). It controls how long an idle test connection may remain open, not a
per-request HTTP timeout.

Validate generated files with the deployed core versions before publishing:

```sh
xray run -test -config profile-xray.json
sing-box check -c profile-sing-box.json
```

The generator validation fixtures were last checked with the official Windows
amd64 releases Xray-core `v26.3.27` and Sing-box `v1.13.16`.  To rerun the
same executable-backed tests, point `XRAY_BINARY` and `SING_BOX_BINARY` at the
downloaded official binaries and run:

```sh
pytest tests/test_subscription_profiles.py -q
```

The executable-backed cases skip when their environment variable is absent,
so ordinary developer test runs do not acquire or execute an unpinned binary.
The fixture uses Reality with RAW/TCP, gRPC, and xHTTP, and TLS with WebSocket:
Xray `v26.3.27` rejects Reality over WebSocket.  Sing-box does not support the
Xray xHTTP transport, so that combination is rejected with an explicit profile
validation error instead of being silently omitted.

## Optional Happ / Incy / v2rayN path

The profile's `client` value (`generic`, `happ`, `incy`, or `v2rayn`) remains
opt-in. Add `profile_id` to an existing ordered subscription rule to select that
client-template profile when its User-Agent regex matches. Without `profile_id`,
the rule continues to use the legacy `target` generator.

For example, if client template `42` is an Xray profile intended for Happ:

```json
{
  "pattern": "(?i)^happ",
  "target": "xray",
  "profile_id": 42,
  "response_headers": {
    "x-provider-id": "PasarGuard",
    "profile-title": "Happ {USERNAME}"
  }
}
```

Use the same contract with `(?i)^incy` or `(?i)^v2rayn` and a profile whose
`client` is `incy` or `v2rayn`. `profile_id` is valid only for `xray` and
`sing_box` rules, and the selected template type must match `target`. Unknown
clients and rules without a profile keep the ordinary subscription behavior.

### Happ routing/deeplink example

The current public Remnawave response-rule example detects Happ using a
case-insensitive User-Agent condition, selects a named Xray template, and adds
response headers. PasarGuard maps that approach to its existing regex rule,
numeric client-template ID, and `response_headers` fields. A Happ profile can
also set routing metadata directly:

```json
{
  "schema_version": 1,
  "default_pool": "primary",
  "pools": [{ "id": "primary" }],
  "client": "happ",
  "happ_deeplink": "happ://routing/add/eyJOYW1lIjoiUGFzYXJHdWFyZCJ9"
}
```

When this profile is selected, PasarGuard sends the deeplink in the `routing`
response header. An explicit `routing` value in the matched rule's
`response_headers` takes precedence. Never put bearer subscription URLs or
reusable proxy credentials into metadata headers.

The Happ deeplink schema is client-version-sensitive. The official Remnawave
builder currently emits `happ://routing/add/<base64>`, while the maintained
DigneZzZ example currently uses `happ://routing/onadd/<base64>`; PasarGuard
accepts both schemes but does not interpret or rewrite the encoded payload.
Validate the selected routing JSON in the target Happ release. Incy has a
similar community `incy://routing/onadd/...` asset, but it is not emitted from
`happ_deeplink`; supply Incy-specific metadata explicitly in the rule if the
target client version requires it.

References:

- [Remnawave Response Rules](https://docs.rw/learn-en/routing-rules/)
- [Remnawave Templates](https://docs.rw/learn-en/templates/)
- [Remnawave Happ Routing Builder](https://utils.docs.rw/happ-rb)
- [DigneZzZ routing Happ/Incy example](https://github.com/dignezzz/routing)
- [DigneZzZ Happ default deeplink](https://github.com/DigneZzZ/routing/blob/main/v2ray/happ/default_deeplink.txt)
