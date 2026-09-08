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
   JSON URL into an Xray/Sing-box client. An Xray client lists one entry per
   automatic group -- `Auto (primary)`, `Auto (DE)`, `Auto (ES)` -- and the
   user picks between them like any other server. Give a pool a friendlier
   label with `title`.
4. To return to the old subscription, remove `profile_id` from the matching
   subscription rule (or use the ordinary legacy URL). No host data or legacy
   template is converted or deleted; the next refresh uses the previous
   link/Xray/Sing-box/Clash generator unchanged.

## Output behavior

Xray profiles create one outbound per eligible endpoint, `observatory`, and a
routing balancer per pool/country.  A pool's `fallback_pool` is emitted as the
Xray balancer's `fallbackTag`, which must name a concrete fallback endpoint.

Xray has no Sing-box-style selector outbound, so a balancer cannot be chosen
from inside a config -- only a routing rule can point at one.  The profile is
therefore published as a JSON **array** (the same shape the legacy Xray
subscription already uses), holding one complete config per automatic group
whose catch-all rule targets that group's balancer.  Each entry carries a
`remarks` label, which is what the client displays: `title` when a pool sets
one, otherwise `Auto (<pool>)` and `Auto (<COUNTRY>)`.  Balancer tags stay
machine-readable (`pg-auto-<pool>`, `pg-country-<country>`) because
operator-authored routing rules address them.

Alongside the groups, `publish_endpoint_configs` (on by default) publishes one
entry per endpoint, named after the host remark, so a user can pick a single
server rather than only a group.  Those entries carry no balancer or
observatory; their catch-all rule names the endpoint's outbound directly.

Three knobs shape the generated routing:

| Field | Default | Notes |
|---|---|---|
| `domain_strategy` | `AsIs` | `AsIs` never resolves a domain, so `geoip:*` and CIDR rules only match traffic that already arrived as an IP.  Mixed domain/IP rulesets need `IPIfNonMatch`. |
| `balancer_strategy` | `random` | `random`, `roundRobin`, `leastPing`, `leastLoad`. |
| `health_check.burst` | `false` | Emits `burstObservatory` with a `pingConfig` instead of `observatory`.  `leastPing` and `leastLoad` require it: plain `observatory` only tracks alive/dead for `fallbackTag`. |

Per-client routing is expressed by binding different profiles to different
User-Agent rules through `SubRule.profile_id`: each profile carries its own
`routing_rules`, so Happ and a browser can receive different rulesets from one
subscription.  Clients that consume the full Xray JSON apply the config's own
`routing` section, so no `routing` response header is involved.

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

## Serving a routing ruleset per client

There are two independent ways to give a client routing rules, and which one
applies depends on what the client receives.

**Inside the config, for anything that gets JSON.** `routing_rules` is written
into the generated Xray `routing.rules` (or the Sing-box `route.rules`), so any
client consuming the profile applies them.  This is the primary mechanism and
it is client-agnostic.  It is also the only one that works for Happ when the
subscription serves a full Xray JSON config: Happ documents that such a config
is handed to the core as-is and that Happ's own routing rules are then *not*
applied.

Different clients get different rulesets by binding different profiles to
different User-Agent rules through `profile_id`:

```json
{
  "pattern": "(?i)^happ",
  "target": "xray",
  "profile_id": 42,
  "response_headers": { "profile-title": "Happ {USERNAME}" }
}
```

`profile_id` is valid only for `xray` and `sing_box` rules, and the selected
template type must match `target`.  A rule without a profile keeps the ordinary
subscription behaviour.

**Through the `routing` response header, for clients still on share links.**
Happ, INCY and v2rayTun all read a header named `routing`, but they disagree on
its value, so the profile has to declare which client it targets:

| `client` | `routing_payload` | Notes |
|---|---|---|
| `happ` | `happ://routing/add/<b64>`, `/onadd/<b64>` or `happ://routing/off` | `add` activates only if no other profile is active; `onadd` forces activation.  Both overwrite a profile with the same `Name`. |
| `incy` | the same Happ profile in base64, with or without a scheme — `incy://routing/…`, `happ://routing/…`, `://routing/…` or bare | INCY parses the link whatever the scheme, which is why a Happ header reaches it too. |
| `v2raytun` | bare base64 of an Xray `routing` object | A different schema entirely, exported from v2rayTun itself.  A deeplink here silently does nothing. |
| `generic` | not allowed | No header is sent. |

`routing_enabled: false` additionally sends `routing-enable: 0`, which switches
routing off in Happ regardless of any profile.  It is Happ-only.

v2rayNG, v2rayN and Streisand are deliberately absent: they have no mechanism
for importing routing rules from a subscription.

```json
{
  "schema_version": 1,
  "default_pool": "primary",
  "pools": [{ "id": "primary" }],
  "client": "happ",
  "routing_payload": "happ://routing/add/eyJOYW1lIjoiUGFzYXJHdWFyZCJ9"
}
```

`happ_deeplink` is still accepted as an alias for `routing_payload`, so profiles
written before the field was generalised keep working.

An explicit `routing` value in the matched rule's `response_headers` takes
precedence over the profile, and arbitrary headers can be set there for any
client without touching a profile at all.  Never put bearer subscription URLs
or reusable proxy credentials into metadata headers.

PasarGuard does not interpret or rewrite the encoded payload, and the Happ
schema is version-sensitive: validate the routing JSON against the target
client release.

References:

- [Remnawave Response Rules](https://docs.rw/learn-en/routing-rules/)
- [Remnawave Templates](https://docs.rw/learn-en/templates/)
- [Remnawave Happ Routing Builder](https://utils.docs.rw/happ-rb)
- [DigneZzZ routing Happ/Incy example](https://github.com/dignezzz/routing)
- [DigneZzZ Happ default deeplink](https://github.com/DigneZzZ/routing/blob/main/v2ray/happ/default_deeplink.txt)
