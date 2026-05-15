import CoreEditorPage from '@/features/core-editor/routes/core-editor-page'
import { useParams } from 'react-router'

export default function CoresCoreEditorRoute() {
  const { coreId } = useParams()
  return <CoreEditorPage key={coreId} />
}
