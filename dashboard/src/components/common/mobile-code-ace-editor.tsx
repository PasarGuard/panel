import { useEffect, useRef } from 'react'
import AceEditor from 'react-ace'
import ace from 'ace-builds/src-noconflict/ace'
import 'ace-builds/src-noconflict/mode-c_cpp'
import 'ace-builds/src-noconflict/mode-csharp'
import 'ace-builds/src-noconflict/mode-css'
import 'ace-builds/src-noconflict/mode-dockerfile'
import 'ace-builds/src-noconflict/mode-golang'
import 'ace-builds/src-noconflict/mode-graphqlschema'
import 'ace-builds/src-noconflict/mode-html'
import 'ace-builds/src-noconflict/mode-ini'
import 'ace-builds/src-noconflict/mode-java'
import 'ace-builds/src-noconflict/mode-javascript'
import 'ace-builds/src-noconflict/mode-json'
import 'ace-builds/src-noconflict/mode-less'
import 'ace-builds/src-noconflict/mode-markdown'
import 'ace-builds/src-noconflict/mode-php'
import 'ace-builds/src-noconflict/mode-plain_text'
import 'ace-builds/src-noconflict/mode-powershell'
import 'ace-builds/src-noconflict/mode-python'
import 'ace-builds/src-noconflict/mode-ruby'
import 'ace-builds/src-noconflict/mode-rust'
import 'ace-builds/src-noconflict/mode-scss'
import 'ace-builds/src-noconflict/mode-sh'
import 'ace-builds/src-noconflict/mode-sql'
import 'ace-builds/src-noconflict/mode-typescript'
import 'ace-builds/src-noconflict/mode-xml'
import 'ace-builds/src-noconflict/mode-yaml'
import 'ace-builds/src-noconflict/theme-monokai'
import 'ace-builds/src-noconflict/theme-textmate'
import workerJsonUrl from 'ace-builds/src-noconflict/worker-json?url'

import '@/components/common/ace-json-jinja-mode'
import { monacoLanguageToAceMode } from '@/components/common/code-editor-language'
import type { CodeEditorMarker } from '@/components/common/code-editor-panel'

ace.config.setModuleUrl('ace/mode/json_worker', workerJsonUrl)

export interface MobileCodeAceEditorProps {
  value: string
  /** Monaco language id (mapped to Ace mode). Overrides {@link aceMode} when set. */
  language?: string
  /** Ace mode name directly (e.g. `json`). Use when not mapping from Monaco. */
  aceMode?: string
  theme?: string
  onChange: (value: string) => void
  onLoad?: (editor: unknown) => void
  readOnly?: boolean
  /** Errors to show in the gutter, by 1-based line. */
  markers?: CodeEditorMarker[]
}

export default function MobileCodeAceEditor({ value, language, aceMode: aceModeProp, theme, onChange, onLoad, readOnly, markers }: MobileCodeAceEditorProps) {
  const mode = aceModeProp ?? monacoLanguageToAceMode(language)
  const editorRef = useRef<{ getSession: () => { clearAnnotations: () => void } } | null>(null)

  // Ace keeps the JSON worker's gutter annotations after it is switched off.
  const previousModeRef = useRef(mode)
  useEffect(() => {
    if (previousModeRef.current === 'json' && mode !== 'json') editorRef.current?.getSession().clearAnnotations()
    previousModeRef.current = mode
  }, [mode])

  return (
    <AceEditor
      mode={mode}
      theme={theme === 'dark' ? 'monokai' : 'textmate'}
      name={`mobile-ace-${mode}`}
      width="100%"
      height="100%"
      value={value}
      onChange={onChange}
      onLoad={editor => {
        editorRef.current = editor
        onLoad?.(editor)
      }}
      readOnly={readOnly}
      annotations={markers?.map(({ line, message }) => ({ row: line - 1, column: 0, type: 'error', text: message }))}
      editorProps={{ $blockScrolling: true }}
      setOptions={{
        useWorker: mode === 'json',
        tabSize: 2,
        wrap: true,
        useSoftTabs: true,
        fontSize: 14,
        fontFamily: 'ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, "Liberation Mono", monospace',
        showLineNumbers: true,
        highlightActiveLine: true,
        displayIndentGuides: true,
        scrollPastEnd: false,
        showPrintMargin: false,
        ...(mode === 'yaml'
          ? {
              enableBasicAutocompletion: false,
              enableLiveAutocompletion: false,
              enableSnippets: false,
            }
          : {}),
      }}
    />
  )
}
