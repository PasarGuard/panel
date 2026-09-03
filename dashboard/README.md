# Dashboard UI for pasarguard

Web UI for [PasarGuard](https://github.com/PasarGuard/panel): large-scale proxy management that supports both [Xray-core](https://github.com/XTLS/Xray-core) and
[WireGuard](https://www.wireguard.com/).

## Requirements

For development, you will only need Node.js installed on your environement.

### Node

Use Node.js >= 22.18.0. The form contract tests use Node's native TypeScript loading.

## Install

    Install the latest LTS version of Node.js
    git clone https://github.com/PasarGuard/panel.git
    `bash cd panel/dashboard`
    `bash curl -fsSL https://bun.sh/install | bash`
    `bash bun install`

### Configure app

Copy `example.env` to `.env` then set the backend api address:

    VITE_BASE_API=https://somewhere.com/

#### Environment variables

| Name          | Description                                                                                 |
| ------------- | ------------------------------------------------------------------------------------------- |
| VITE_BASE_API | The api url of the deployed backend ([PasarGuard](https://github.com/PasarGuard/panel.git)) |

## Start development server

    bun dev

## Simple build for production

    bun build

## Contribution

### Form regression checks

Run from `dashboard/` after `bun install`:

```sh
npm run typecheck -- --force --pretty false
npm run test:form-contracts
npm run build -- --outDir ./dist/form-check
npx playwright install chromium
npm run test:form-submissions -- ./dist/form-check
```

The browser check uses the Playwright development dependency and mocks all API and external requests.
To use an installed Edge or Chrome instead of downloading Chromium, set `PLAYWRIGHT_CHANNEL=msedge` or `PLAYWRIGHT_CHANNEL=chrome`.
Use a fresh output directory for each build.

Feel free to contribute. Go on and fork the project. After commiting the changes, make a PR. It means a lot to us.
