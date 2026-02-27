import AceEditor from 'react-ace'
import ace from 'ace-builds/src-noconflict/ace'
import 'ace-builds/src-noconflict/mode-json'
import 'ace-builds/src-noconflict/theme-monokai'
import 'ace-builds/src-noconflict/theme-tomorrow_night'
import workerJsonUrl from 'ace-builds/src-noconflict/worker-json?url'

ace.config.setModuleUrl('ace/mode/json_worker', workerJsonUrl)

interface MobileJsonAceEditorProps {
  value: string
  theme?: string
  onChange: (value: string) => void
  onLoad?: (editor: any) => void
}

export default function MobileJsonAceEditor({ value, theme, onChange, onLoad }: MobileJsonAceEditorProps) {
  return (
    <AceEditor
      mode="json"
      theme={theme === 'dark' ? 'monokai' : 'textmate'}
      name="core-config-mobile-ace-editor"
      width="100%"
      height="100%"
      value={value}
      onChange={onChange}
      onLoad={onLoad}
      editorProps={{ $blockScrolling: true }}
      setOptions={{
        useWorker: true,
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
        enableBasicAutocompletion: false,
        enableLiveAutocompletion: false,
        enableSnippets: false,
      }}
    />
  )
}
