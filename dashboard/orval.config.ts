/// <reference types="node" />
import { defineConfig } from 'orval'

export default defineConfig({
  app: {
    output: {
      client: 'react-query',
      target: './src/service/api/index.ts',
      mode: 'single',
      clean: false,
      prettier: true,
      tslint: true,
      headers: false,
      override: {
        fetch: {
          // The custom fetcher returns the JSON body and throws on HTTP errors.
          includeHttpResponseReturnType: false,
        },
        mutator: {
          path: './src/service/http.ts',
          name: 'orvalFetcher',
        },
      },
    },
    input: {
      // Prefer a pre-extracted schema file (offline generation) when provided,
      // otherwise fall back to the running server's live endpoint.
      target: process.env.OPENAPI_INPUT || `http://127.0.0.1:${process.env.UVICORN_PORT || 8000}/openapi.json`,
    },
  },
})
