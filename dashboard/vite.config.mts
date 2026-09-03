import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { defineConfig } from 'vite'
import svgr from 'vite-plugin-svgr'
import path from 'path'
import { VitePWA } from 'vite-plugin-pwa'

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
    VitePWA({
      registerType: 'prompt',
      injectRegister: false,
      workbox: {
        navigateFallback: '/index.html',
        globPatterns: ['**/*.{js,css,html,ico,png,svg,woff2}'],
        // Monaco is loaded lazily in editor dialogs, so its largest chunks
        // should stay network-fetched instead of bloating the app shell precache.
        globIgnores: ['statics/editor.api*.js', 'statics/ts.worker*.js'],
        cleanupOutdatedCaches: false,
        skipWaiting: false,
        clientsClaim: false,
      },
    }),
  ],
})
