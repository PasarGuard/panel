import { loader } from '@monaco-editor/react'
import * as monaco from 'monaco-editor'
import editorWorker from 'monaco-editor/esm/vs/editor/editor.worker?worker'
import jsonWorker from 'monaco-editor/esm/vs/language/json/json.worker?worker'

type MonacoInstance = NonNullable<Parameters<typeof loader.config>[0]['monaco']>

type MonacoWorkerFactory = (workerId: string, label: string) => Worker

type MonacoEnvironmentShape = {
  getWorker?: MonacoWorkerFactory
}

type MonacoGlobal = typeof globalThis & {
  MonacoEnvironment?: MonacoEnvironmentShape
}

const monacoGlobal = typeof self === 'undefined' ? null : (self as MonacoGlobal)

if (monacoGlobal && !monacoGlobal.MonacoEnvironment?.getWorker) {
  monacoGlobal.MonacoEnvironment = {
    ...monacoGlobal.MonacoEnvironment,
    getWorker(_, label) {
      if (label === 'json') {
        return new jsonWorker()
      }

      return new editorWorker()
    },
  }
}

// Bun exposes Monaco through a symlinked package path, which makes the loader's
// Monaco type and the imported Monaco value look different to TypeScript even
// though they are the same runtime module.
loader.config({ monaco: monaco as unknown as MonacoInstance })
