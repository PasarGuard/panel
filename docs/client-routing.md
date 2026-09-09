# Application routing

Open **Applications**, choose Happ, Mihomo / Clash, Sing-box or Xray, then edit
**Routing** and **DNS**. Preview the subscription for a user before saving.
Host settings are not required for this workflow.

An assigned configuration opens directly in the editor. The configuration name
appears once beside the application name. **Configuration options** contains
reuse information, the option to make a separate copy and a link to saved configurations.

- **Applications** is the normal entry point.
- **Saved configurations** opens the library of stored documents.
- **Application matching order** controls the global order of User-Agent rules.

The latter two are secondary links below the application list. Each application's
**Subscription delivery** section edits its matching conditions and links to the
global matching order. Leaving an editor with unsaved changes requires confirmation.

These views use the same documents and rules. The old `/templates/client` route
redirects to the configuration library for workspace users. Administrators who
can read templates but cannot read settings retain the legacy template page;
settings-only administrators retain the existing delivery-rule form. User
templates still create users.

## Documents and visual editing

| Application | Source document |
| --- | --- |
| Happ | Happ routing JSON, delivered alongside a server list |
| Happ, full Xray mode | Xray subscription JSON |
| Xray | Xray subscription JSON |
| Sing-box | Sing-box subscription JSON |
| Mihomo / Clash | Clash subscription YAML, optionally containing Jinja |

**Visual** and **Code** edit the same source. Switching views does not rewrite
it. Visual editing changes supported routing and DNS fields while preserving
unrecognized fields and untouched source sections. Advanced rules remain visible
and can be opened in code. A section containing dynamic Jinja is edited in code;
it is not converted into a static document.

For Xray, Sing-box and Mihomo, rules are ordered and the first match wins. A new
rule selects an existing outbound or group from the document. Use exact domains,
domains with subdomains, or IP/CIDR conditions. Happ's routing profile instead has
separate direct, proxy and block lists, plus its default traffic policy.

Field-level **Apply** updates the local document draft. **Save** persists the
document and its assignment together. Invalid input and version conflicts leave
the draft available. Navigation warns before discarding unsaved changes.

Changing an application that uses a system/default template creates its own copy.
Other applications continue using the default. Editing a deliberately shared
document affects every rule referencing it; its uses are listed in configuration
options. Copy it first to separate one application's behavior.

## Delivery

The first matching User-Agent rule still determines the response. The optional
`ui_application` field organizes the editor; it is not a matching or access rule.

An explicit `template_id` selects the whole native document for that request.
For Xray this takes precedence over individual host template overrides. Without
an explicit assignment, existing defaults and host overrides retain their
behavior. Explicit format URLs retain their format-selection semantics.

Happ assignments reference a `happ_routing` document. Its JSON `Name` identifies
the profile on the device independently of the library record's display name.
Keep `Name` stable for updates to the same profile.

The default transport adds a UTF-8/Base64 `happ://routing/onadd/...` line to a plain
server-list subscription. This follows the
[Happ routing contract](https://github.com/HappDev/happ_su/blob/main/dev-docs/routing.md).
Header delivery is also available, limited to 2048 bytes for the complete value.
Oversized values are rejected, never truncated. Body delivery cannot be combined
with an outer Base64 subscription wrapper.

Managed Happ routing owns the `routing` and `routing-enable` headers for its rule.
Conflicting manually configured names are rejected without regard to case.
Existing manual headers are not automatically converted. Full Xray mode edits the
Xray document directly; a standard Happ profile does not rewrite it. See
[Happ's JSON subscription behavior](https://github.com/HappDev/happ_su/blob/main/dev-docs/examples-of-links-and-parameters.md).

## Storage and API

Documents are stored in the existing `client_templates` database table, and
assignments are stored in the subscription settings JSON. There is no separately
maintained routing file on the panel server. Code view provides the editable
source document.

All workspace endpoints are under `/api/client_template`:

| Method and path | Purpose |
| --- | --- |
| `GET /workspace` | Documents, subscription settings and current revision |
| `POST /apply` | Atomically save a document and its rule assignments |
| `POST /preview` | Render a saved or draft assignment for a selected user |

`apply` accepts `expected_revision`, `rules`, an optional `template` and optional
zero-based `bind_rule_indices`. Those indices bind rules to the created/edited
document in the same transaction. A stale revision returns `409`; missing or
incompatible documents are rejected. Deleting a referenced document is blocked,
including bulk deletion.

Workspace reads require settings and client-template read permissions. Saving
requires settings update permission and the corresponding template create/update
permission. Preview additionally requires access to the selected user.

## Verification limits

Preview shows the matched rule, effective source and format, response body,
Happ payload and detected generation/reference errors. It does not register an
HWID device, update subscription activity, test device admission or send traffic
through the configuration. Validate the output with the relevant core and test
import, update and routing in the actual application before rollout.

This feature edits native documents and works independently of automatic
subscription-profile generators. It does not add host pools, inactive-user
notices or status-based rule matching.
