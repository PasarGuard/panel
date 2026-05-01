# HWID device limit — developer guide

This document describes how **HWID (hardware / client identifier) device limits** work in PasarGuard (PGpanel): subscription request flow, HTTP headers, stored fields, admin APIs, and how to run smoke checks.

HWID enforcement is **optional** and **off by default** (`subscription.hwid_device_limit_enabled = false`). When disabled, subscription URLs behave as before and clients do not need to send `x-hwid`.

---

## Where to configure (operators)

| Setting | Location |
|--------|----------|
| Enable HWID globally, fallback device limit | Dashboard **Settings → Subscriptions** (`hwid_device_limit_enabled`, `hwid_fallback_device_limit`) |
| Per-user device limit, “skip limit” for user | **Users** — edit user (Groups tab: HWID block) |
| Inspect / delete devices, manual register | Dashboard **Settings → HWID** |
| Server-side secret for hashing | Environment **`HWID_HASH_SALT`** (must be stable per deployment; changing it invalidates existing device rows) |

Effective limit for a user when HWID is enabled:

1. If the user has **“skip HWID limit”** (`hwid_limit_disabled`) → HWID is not enforced for that user.
2. Else if the user has **`hwid_device_limit`** set → that integer is the limit.
3. Else → **`hwid_fallback_device_limit`** from subscription settings. If that value is **0 or unset**, enforcement treats it as **no limit** (requests are allowed without registering against a positive cap — see backend `HWIDOperation.enforce_subscription_hwid`).

---

## Subscription HTTP API (client fetch)

HWID is evaluated on **token-based subscription GET** routes (same routes apps use to download the config).

**Path prefix** comes from config: `SUBSCRIPTION_PATH` / `XRAY_SUBSCRIPTION_PATH` (default URL segment is `sub` if unset). Examples below use `sub`.

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/{sub_prefix}/{token}/` | Resolve format from `User-Agent` + `Accept` |
| `GET` | `/{sub_prefix}/{token}/{client_type}` | Explicit format, e.g. `links`, `clash`, `xray` |

Relevant **`client_type`** values: `links`, `links_base64`, `xray`, `wireguard`, `sing_box`, `clash`, `clash_meta`, `outline` (must also be allowed in subscription **manual sub request** toggles).

### Request headers (case-insensitive)

FastAPI normalizes these to parameters; clients should send canonical names.

| Header | Required when HWID enforced | Stored / used |
|--------|----------------------------|----------------|
| **`x-hwid`** | Yes (non-empty, ≤ 256 chars after trim) | Hashed with HMAC-SHA256 using `HWID_HASH_SALT`; **raw value is not stored** |
| `x-device-os` | No | `device_os` (max 64) |
| `x-ver-os` | No | `os_version` (max 64) |
| `x-device-model` | No | `device_model` (max 128) |
| `User-Agent` | No | `user_agent` (max 512) |

**Client IP** is taken from the request (`request.client.host`) when present and stored as `request_ip` (max 64).

Invalid / missing `x-hwid` when enforcement applies is treated like an unsuccessful subscription fetch (**404**), with diagnostic headers (see below). Extremely long `x-hwid` is rejected the same way.

### Successful response headers

When global HWID is **enabled**, successful subscription responses include:

```http
x-hwid-active: true
```

### Denied responses (404)

To avoid leaking whether a user exists, failures use **404** where applicable (aligned with “invalid subscription” behaviour).

| Situation | Extra response headers |
|-----------|-------------------------|
| HWID required but header missing / empty / too long | `x-hwid-active: true`, `x-hwid-not-supported: true` |
| Device limit reached (new device would exceed limit) | `x-hwid-active: true`, `x-hwid-max-devices-reached: true`, `x-hwid-limit: true` |

### Behaviour summary

1. **HWID disabled globally** → allow; no HWID headers added.
2. **User bypasses HWID** → allow.
3. **No positive effective limit** → allow (no device registration pressure from limit).
4. Otherwise: require valid `x-hwid`; if hash already exists for user → update `last_seen_at` and metadata; if new hash and under limit → insert row; if at limit → 404 with limit headers.

Concurrency: registration is **not** “count then insert”; the implementation uses a **transaction and user row lock** so parallel requests with different new HWIDs cannot exceed the configured limit.

---

## Data model (`hwid_user_devices`)

| Field | Notes |
|-------|--------|
| `user_id` | Internal user id |
| `hwid_hash` | HMAC-SHA256 hex digest of normalized `x-hwid` |
| `device_os`, `os_version`, `device_model`, `user_agent`, `request_ip` | Optional metadata, clamped to max lengths |
| `first_seen_at`, `last_seen_at`, `created_at`, `updated_at` | Timestamps |

Unique constraint: **`(user_id, hwid_hash)`**.

---

## Admin API (authenticated dashboard / admin token)

Base path: **`/api/hwid/devices`**. All routes require admin auth (same as other `/api/*` admin routes).

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/hwid/devices` | Paginated list (`offset`, `limit`, optional `user_id`) |
| `GET` | `/api/hwid/devices/stats` | Aggregate stats (sudo) |
| `GET` | `/api/hwid/devices/top-users` | Top users by device count (sudo) |
| `GET` | `/api/hwid/devices/{user_id}` | Devices for one user |
| `POST` | `/api/hwid/devices` | Body: `{ "user_id", "hwid", ...optional metadata }` — register device from **raw** HWID (hashed server-side) |
| `POST` | `/api/hwid/devices/delete` | Body: `{ "user_id", "hwid_hash" }` |
| `POST` | `/api/hwid/devices/delete-all` | Body: `{ "user_id" }` |

List responses use enriched models where applicable (e.g. `username` on device rows).

---

## Security & privacy notes for integrators

- Treat **`x-hwid` as untrusted**; it is not authentication.
- Do not log raw HWIDs in client apps if logs are shared.
- Admin UI shows **hashes**, not raw values, for registered devices.
- Denial responses are deliberately **bland (404)** where possible.

---

## Smoke testing

See **`docs/hwid_subscription_smoke.sh`** in this repository: example `curl` calls with different `x-hwid` / metadata headers against `/{sub}/{token}/links`.

**Prerequisites:** a valid subscription token, correct `SUBSCRIPTION_PATH`, TLS flags if using self-signed certs, and (for limit tests) HWID enabled + fallback limit configured in the panel.

---

## Local Docker image (UI + API)

After changing the dashboard, run **`npm run build`** in `dashboard/` so `dashboard/build` is current, then from the **`PGpanel/`** repository root:

```bash
docker build -t pgpanel-local:hwid .
```

Run the container with your usual `env_file`, TLS cert mounts, and persistent DB volume (see project `.env.docker.local` / `local-certs/` if you use them). The shipped UI is the pre-built files under `dashboard/build` inside the image.

---

## Related source (for maintainers)

- Subscription routes & header wiring: `app/routers/subscription.py`
- Enforcement orchestration: `app/operation/subscription.py`, `app/operation/hwid.py`
- DB logic & hashing: `app/db/crud/hwid.py`
- Admin router: `app/routers/hwid.py`
- Models: `app/models/hwid.py`, subscription settings in `app/models/settings.py`
