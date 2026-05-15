import { WireGuardCoreForm } from '@/features/core-editor/components/wg/wireguard-form'
import { XrayAdvancedSection } from '@/features/core-editor/components/xray/xray-advanced-section'
import { useCoreEditorStore } from '@/features/core-editor/state/core-editor-store'
import type { WgCoreSection } from '@/features/core-editor/state/core-editor-store'

export function WireGuardCoreEditor() {
  const section = useCoreEditorStore(s => s.activeSection) as WgCoreSection

  return (
    <div className="space-y-8">
      {section === 'interface' && <WireGuardCoreForm />}
      {section === 'advanced' && <XrayAdvancedSection />}
    </div>
  )
}
