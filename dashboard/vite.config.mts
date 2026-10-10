import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { defineConfig } from 'vite'
import svgr from 'vite-plugin-svgr'
import path from 'path'
import { VitePWA } from 'vite-plugin-pwa'

const shellJavaScript = new Set<string>()

export default defineConfig({
  base: process.env.BASE_URL,
  clearScreen: false,
  server: {
    host: true,
    watch: {
      ignored: ['**/build/**'],
    },
  },
  build: {
    outDir: 'build',
    assetsDir: 'statics',
    emptyOutDir: false,
    // Let the bundler preserve lazy import boundaries; manual vendor groups
    // pulled chart and dialog dependencies into the initial app shell.
  },
  resolve: {
    dedupe: ['react', 'react-dom'],
    tsconfigPaths: true,
    alias: [
      {
        find: '@',
        replacement: path.resolve(import.meta.dirname, 'src'),
      },
    ],
  },
  optimizeDeps: {
    holdUntilCrawlEnd: false,
    entries: ['index.html'],
    include: [
      'react',
      'react-dom',
      'react/jsx-runtime',
      'react/jsx-dev-runtime',
      '@tanstack/react-query',
      'dayjs',
      'lodash.debounce',
      'react-use-websocket',
    ],
    exclude: ['monaco-editor', '@monaco-editor/react', 'ace-builds', 'react-ace', 'lucide-react'],
  },
  plugins: [
    tailwindcss(),
    react(),
    svgr(),
    {
      name: 'collect-shell-precache',
      generateBundle(_, bundle) {
        shellJavaScript.clear()
        const visit = (fileName: string) => {
          const chunk = bundle[fileName]
          if (chunk?.type !== 'chunk' || shellJavaScript.has(fileName)) return
          shellJavaScript.add(fileName)
          chunk.imports.forEach(visit)
        }
        // Follow static imports only; route, dialog and editor chunks stay deferred.
        Object.values(bundle).forEach(chunk => {
          if (chunk.type === 'chunk' && chunk.isEntry) visit(chunk.fileName)
        })
      },
    },
    VitePWA({
      registerType: 'prompt',
      injectRegister: false,
      workbox: {
        navigateFallback: '/index.html',
        globPatterns: ['**/*.{js,css,html,ico,png,svg,woff2}'],
        globIgnores: ['statics/editor.api*.js', 'statics/ts.worker*.js'],
        // Preserve the shell offline without downloading every lazy chunk on install.
        manifestTransforms: [
          async entries => ({
            manifest: entries.filter(entry => !entry.url.endsWith('.js') || shellJavaScript.has(entry.url)),
            warnings: [],
          }),
        ],
        runtimeCaching: [
          {
            urlPattern: ({ request, url, sameOrigin }) => sameOrigin && request.destination === 'script' && /\/statics\/[^/]+\.js$/.test(url.pathname),
            handler: 'CacheFirst',
            options: {
              cacheName: 'pasarguard-lazy-javascript',
              cacheableResponse: { statuses: [200] },
              expiration: { maxEntries: 128, maxAgeSeconds: 30 * 24 * 60 * 60 },
            },
          },
        ],
        cleanupOutdatedCaches: false,
        skipWaiting: false,
        clientsClaim: false,
      },
    }),
  ],
})
