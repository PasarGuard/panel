import react from '@vitejs/plugin-react'
import autoprefixer from 'autoprefixer'
import tailwindcss from 'tailwindcss'
import { defineConfig } from 'vite'
import svgr from 'vite-plugin-svgr'
import tsconfigPaths from 'vite-tsconfig-paths'
import path from 'path'
import { VitePWA } from 'vite-plugin-pwa'

export default defineConfig({
  base: process.env.BASE_URL,
  clearScreen: false,
  server: {
    host: true,
  },
  css: {
    postcss: {
      plugins: [tailwindcss, autoprefixer],
    },
  },
  build: {
    outDir: 'build',
    assetsDir: 'statics',
    rollupOptions: {
      output: {
        manualChunks(id) {
          const normalizedId = id.replace(/\\/g, '/')

          if (
            normalizedId.includes('/node_modules/react/') ||
            normalizedId.includes('/node_modules/react-dom/') ||
            normalizedId.includes('/node_modules/scheduler/') ||
            normalizedId.includes('react-dom/index.js?commonjs-es-import')
          ) {
            return 'react'
          }

          if (normalizedId.includes('/node_modules/react-router/') || normalizedId.includes('/node_modules/react-router-dom/')) {
            return 'react-router'
          }

          if (normalizedId.includes('/node_modules/@tanstack/react-query/') || normalizedId.includes('/node_modules/@tanstack/query-core/')) {
            return 'react-query'
          }

          if (normalizedId.includes('/node_modules/recharts/')) {
            return 'recharts'
          }

          if (normalizedId.includes('/node_modules/@radix-ui/react-slot/')) {
            return 'radix-slot'
          }

          if (
            normalizedId.includes('/node_modules/@radix-ui/react-dialog/') ||
            normalizedId.includes('/node_modules/@radix-ui/react-alert-dialog/') ||
            normalizedId.includes('/node_modules/@radix-ui/react-toast/')
          ) {
            return 'radix-dialog'
          }

          if (
            normalizedId.includes('/node_modules/@radix-ui/react-popover/') ||
            normalizedId.includes('/node_modules/@radix-ui/react-dropdown-menu/') ||
            normalizedId.includes('/node_modules/@radix-ui/react-hover-card/') ||
            normalizedId.includes('/node_modules/@radix-ui/react-tooltip/') ||
            normalizedId.includes('/node_modules/@radix-ui/react-select/')
          ) {
            return 'radix-popover'
          }

          if (
            normalizedId.includes('/node_modules/@radix-ui/react-tabs/') ||
            normalizedId.includes('/node_modules/@radix-ui/react-accordion/') ||
            normalizedId.includes('/node_modules/@radix-ui/react-collapsible/')
          ) {
            return 'radix-navigation'
          }

          if (
            normalizedId.includes('/node_modules/@radix-ui/react-checkbox/') ||
            normalizedId.includes('/node_modules/@radix-ui/react-radio-group/') ||
            normalizedId.includes('/node_modules/@radix-ui/react-switch/') ||
            normalizedId.includes('/node_modules/@radix-ui/react-label/')
          ) {
            return 'radix-forms'
          }

          if (
            normalizedId.includes('/node_modules/@radix-ui/react-scroll-area/') ||
            normalizedId.includes('/node_modules/@radix-ui/react-separator/') ||
            normalizedId.includes('/node_modules/@radix-ui/react-progress/') ||
            normalizedId.includes('/node_modules/@radix-ui/react-avatar/')
          ) {
            return 'radix-layout'
          }

          if (
            normalizedId.includes('/node_modules/@radix-ui/react-toggle/') ||
            normalizedId.includes('/node_modules/@radix-ui/react-toggle-group/')
          ) {
            return 'radix-toggle'
          }

          if (normalizedId.includes('/node_modules/zustand/')) {
            return 'zustand'
          }

          if (
            normalizedId.includes('/node_modules/i18next/') ||
            normalizedId.includes('/node_modules/react-i18next/') ||
            normalizedId.includes('/node_modules/i18next-browser-languagedetector/') ||
            normalizedId.includes('/node_modules/i18next-http-backend/')
          ) {
            return 'i18n'
          }

          if (normalizedId.includes('/node_modules/lodash.debounce/')) {
            return 'lodash'
          }

          if (normalizedId.includes('/node_modules/dayjs/')) {
            return 'dayjs'
          }

          if (
            normalizedId.includes('/node_modules/clsx/') ||
            normalizedId.includes('/node_modules/uuid/') ||
            normalizedId.includes('/node_modules/date-fns/') ||
            normalizedId.includes('/node_modules/date-fns-jalali/')
          ) {
            return 'utils'
          }
        },
      },
    },
  },
  resolve: {
    alias: [
      {
        find: '@',
        replacement: path.resolve(__dirname, 'src'),
      },
    ],
  },
  plugins: [
    react(),
    svgr(),
    tsconfigPaths(),
    VitePWA({
      registerType: 'autoUpdate',
      injectRegister: false,
      workbox: {
        navigateFallback: '/index.html',
        globPatterns: ['**/*.{js,css,html,ico,png,svg,woff2}'],
        skipWaiting: true,
        clientsClaim: true,
        runtimeCaching: [
          {
            urlPattern: /^https:\/\/fonts\.googleapis\.com\/.*/i,
            handler: 'CacheFirst',
            options: {
              cacheName: 'google-fonts-cache',
              expiration: {
                maxEntries: 10,
                maxAgeSeconds: 60 * 60 * 24 * 365,
              },
            },
          },
        ],
      },
    }),
  ],
})
