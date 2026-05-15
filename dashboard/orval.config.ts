/// <reference types="node" />
import { defineConfig } from 'orval'

export default defineConfig({
  app: {
    output: {
      client: 'react-query',
      target: './src/service/api/index.ts',
      mode: 'single',
      clean: false,
      headers: false,
      override: {
        fetch: {
          includeHttpResponseReturnType: false,
        },
        mutator: {
          path: './src/service/http.ts',
          name: 'orvalFetcher',
        },
      },
    },
    input: {
      target: `http://127.0.0.1:${process.env.UVICORN_PORT || 8000}/openapi.json`,
    },
  },
})
