#!/usr/bin/env bash
# Run locally AFTER railway login + railway init/link. Never use an account token
# in source, and never bypass the user's review of the infrastructure plan.
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
command -v railway >/dev/null || { echo 'Install @railway/cli@5.71.0 first.' >&2; exit 1; }
node -e 'if (+process.versions.node.split(".")[0] < 22) { console.error("Node.js 22+ required"); process.exit(1); }'
npm ci --prefix .railway --ignore-scripts --no-audit --no-fund
npm run --prefix .railway check
npm run --prefix .railway render:test
printf '\nReview the linked project/environment and resource costs before approving.\n'
railway config plan
# Intentionally interactive: no --yes or --confirm-destructive.
railway config apply
printf '\nCreating the public HTTPS endpoint for panel:8080.\n'
railway domain --service panel --port 8080
printf '\nFollow docs/RAILWAY-fa.md to retrieve the private initial Owner credentials.\n'
