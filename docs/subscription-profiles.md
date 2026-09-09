# Xray and Sing-box server-group generators

Server-group generators are an optional configuration source in
**Applications**, alongside native routing documents. They
replace a *single* Xray or Sing-box subscription response. A host remains an endpoint (address,
transport and inbound); the generator owns pools, country groups, health
checks and automatic choice. Existing Clash, Xray and Sing-box subscription
URLs are not changed.

## Create a profile

Open an application in **Applications**, then choose a new **Xray
server-group generator** or **Sing-box server-group generator** as its
configuration. Routing and DNS parameters, optional server pools, preview and
saving belong to the same application page. Saved generators also appear in
the configuration library. See [Client routing](client-routing.md) for the
shared document and assignment workflow.
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
    "timeout": "30m",
    "probe_timeout": "5s"
  },
  "publish_endpoint_configs": true
}
```

Pool IDs are stable lowercase machine identifiers, not display names. Each
enabled pool is optional for a particular user and is omitted when that user
has no eligible endpoint in it. The default pool is the exception: it must
contain an eligible endpoint and at least one endpoint that is allowed in
automatic groups. The default and referenced fallback pools must be enabled.

## Classify endpoints

In a host's **Client profile classification** section set the `pool` and
optional ISO two-letter `country`. `subscription_templates.profile.priority`
overrides the host priority for profile ordering; leave it empty to use the
host priority. **Exclude from automatic groups** removes the endpoint from
pool/country health checks. Sing-box still exposes it in the pool selector,
and `publish_endpoint_configs` still exposes its individual Xray config.

Changing the host remark, randomized address, port, or SNI has no effect on
profile membership. Xray derives deterministic `pg-proxy-*` tags from the
stable host ID. Sing-box uses the remark as the endpoint label, reserving
group names first and disambiguating endpoint labels when necessary.

## Give a user one profile

The ordinary workflow is to save the generator together with its application
assignment and use the user's existing subscription URL. The first matching
delivery rule selects this configuration. A rule can select one generator
or one native document, never both.

The explicit public endpoint is:

```text
/{SUBSCRIPTION_PATH}/{token}/profile/{profile_id}
```

It produces JSON based only on endpoints currently eligible for that user.
Disabled hosts and inactive users are rejected before grouping. Admin preview
is `GET /api/user/{user_id}/subscription/profile/{profile_id}`; it is protected
by the normal user and client-template read permissions and sends
`Cache-Control: no-store`. The public profile response contains credentials and
sends `Cache-Control: private, no-store`.

## Example: primary, fallback, and a country choice

1. Create an Xray server-group generator with `primary` as `default_pool` and
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
routing balancer per pool/country. A pool's `fallback_pool` is emitted as the
Xray balancer's `fallbackTag`, which must name a concrete outbound rather than
another balancer. The generator deterministically chooses the first automatic
endpoint in the fallback pool. If that pool has no automatic endpoint for this
user, no `fallbackTag` is emitted. Sing-box has no equivalent strict failover.

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

Three Xray knobs shape automatic selection:

| Field | Default | Notes |
|---|---|---|
| `balancer_strategy` | `random` | `random`, `roundRobin`, `leastPing`, `leastLoad`. |
| `balancer_settings` | unset | Xray-only `expected` and `baselines` tuning for `leastPing`/`leastLoad`. |
| `health_check.burst` | `false` | Emits `burstObservatory` with a `pingConfig` instead of `observatory`.  `leastPing` and `leastLoad` require it: plain `observatory` only tracks alive/dead for `fallbackTag`. |

Sing-box profiles create selectors for non-empty pools and a separate `urltest`
only when that pool has automatic endpoints, then a top-level `proxy` selector.
A Sing-box client displays an outbound's tag verbatim, so those tags double as
the labels in its group picker: a pool becomes `<title or id>` with
`<title or id> · Auto` beside it, and a country becomes `DE` with `DE · Auto`.
Group names are reserved before endpoint labels. Conflicting pool titles are
rejected, so a host rename cannot redirect a group rule to a single endpoint.
Use stable routing targets: `pool.id` for a manual pool,
`pg-auto-<pool>` for its automatic group, and `pg-country-<country>` (lowercase
country code) for an automatic country group. The generator translates these
targets to the labels displayed by Sing-box. Existing unambiguous display-name
targets remain supported.
This deliberately does **not** claim strict
`primary -> fallback` failover: Sing-box `urltest` chooses among the outbounds
in its own pool and has no Xray-style `fallbackTag`.  Users can still choose a
fallback pool explicitly.

For Sing-box, `health_check.timeout` is its `urltest.idle_timeout`; it must be
at least as long as `interval` (the default is `30m` for the default `3m`
interval). It controls how long an idle test connection may remain open, not a
per-request HTTP timeout.

For Xray burst probes, `health_check.probe_timeout` is the timeout of one probe
(default `5s`). It is independent from the Sing-box idle timeout and is emitted
only with `health_check.burst: true`.

The **Generator JSON** mode preserves advanced fields
such as `dns`, `routing_rules`, `domain_strategy`, `client` and response-header
options for existing API users. This is the generator's parameter document;
the resulting native client configuration is shown by preview. Rules for a valid generated pool/country group that is
absent for one user are omitted from that user's output; arbitrary unknown
targets remain validation errors rather than silently changing routing.

Validate generated files with the deployed core versions before publishing:

```sh
xray run -test -config profile-xray.json
sing-box check -c profile-sing-box.json
```

The generator validation fixtures were last checked with the official Windows
amd64 releases Xray-core `v26.3.27` and Sing-box `v1.14.0`. To rerun the
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

Xray burst probe behavior follows the official
[observatory configuration](https://xtls.github.io/en/config/observatory.html).
