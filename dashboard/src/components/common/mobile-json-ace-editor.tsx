import type { MobileCodeAceEditorProps } from '@/components/common/mobile-code-ace-editor'
import MobileCodeAceEditor from '@/components/common/mobile-code-ace-editor'

/** @deprecated Prefer {@link MobileCodeAceEditor} with `language="json"`. */
export default function MobileJsonAceEditor(props: Omit<MobileCodeAceEditorProps, 'language' | 'aceMode'>) {
  return <MobileCodeAceEditor {...props} language="json" />
}
