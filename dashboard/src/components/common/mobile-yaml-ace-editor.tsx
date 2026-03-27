import AceEditor from 'react-ace'
import 'ace-builds/src-noconflict/mode-yaml'
import 'ace-builds/src-noconflict/theme-monokai'
import 'ace-builds/src-noconflict/theme-tomorrow_night'

interface MobileYamlAceEditorProps {
  value: string
  theme?: string
  onChange: (value: string) => void
  onLoad?: (editor: any) => void
}

export default function MobileYamlAceEditor({ value, theme, onChange, onLoad }: MobileYamlAceEditorProps) {
  return (
    <AceEditor
      mode="yaml"
      theme={theme === 'dark' ? 'monokai' : 'textmate'}
      name="client-template-mobile-yaml-ace-editor"
      width="100%"
      height="100%"
      value={value}
      onChange={onChange}
      onLoad={onLoad}
      editorProps={{ $blockScrolling: true }}
      setOptions={{
        useWorker: false,
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
