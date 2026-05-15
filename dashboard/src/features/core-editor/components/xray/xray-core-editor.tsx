import { XrayInboundTagSelectors } from '@/features/core-editor/components/shared/xray-inbound-tag-selectors'
import { XrayAdvancedSection } from '@/features/core-editor/components/xray/xray-advanced-section'
import { XrayBalancersSection } from '@/features/core-editor/components/xray/xray-balancers-section'
import { XrayDnsSection } from '@/features/core-editor/components/xray/xray-dns-section'
import { XrayInboundsSection } from '@/features/core-editor/components/xray/xray-inbounds-section'
import { XrayOutboundsSection } from '@/features/core-editor/components/xray/xray-outbounds-section'
import { XrayRoutingSection } from '@/features/core-editor/components/xray/xray-routing-section'
import type { SectionHeaderAddPulse } from '@/features/core-editor/hooks/use-section-header-add-pulse'
import { useCoreEditorStore } from '@/features/core-editor/state/core-editor-store'
import type { XrayCoreSection } from '@/features/core-editor/state/core-editor-store'

interface XrayCoreEditorProps {
  headerAddPulse?: SectionHeaderAddPulse
  headerAddEpoch?: number
}

export function XrayCoreEditor({ headerAddPulse, headerAddEpoch }: XrayCoreEditorProps) {
  const section = useCoreEditorStore(s => s.activeSection) as XrayCoreSection
  const fallbacks = useCoreEditorStore(s => s.fallbacksInboundTags)
  const excludes = useCoreEditorStore(s => s.excludeInboundTags)
  const setFallbacks = useCoreEditorStore(s => s.setFallbacksInboundTags)
  const setExcludes = useCoreEditorStore(s => s.setExcludeInboundTags)
  const profile = useCoreEditorStore(s => s.xrayProfile)
  const inboundTags = profile?.inbounds.flatMap(i => (i.tag != null ? [i.tag] : [])) ?? []

  return (
    <div className="space-y-8">
      {section === 'inbounds' && <XrayInboundsSection headerAddPulse={headerAddPulse} headerAddEpoch={headerAddEpoch} />}
      {section === 'outbounds' && <XrayOutboundsSection headerAddPulse={headerAddPulse} headerAddEpoch={headerAddEpoch} />}
      {section === 'routing' && <XrayRoutingSection headerAddPulse={headerAddPulse} headerAddEpoch={headerAddEpoch} />}
      {section === 'balancers' && <XrayBalancersSection headerAddPulse={headerAddPulse} headerAddEpoch={headerAddEpoch} />}
      {section === 'dns' && <XrayDnsSection headerAddPulse={headerAddPulse} headerAddEpoch={headerAddEpoch} />}
      {section === 'bindings' && (
        <XrayInboundTagSelectors
          inboundTags={inboundTags}
          fallbackTags={fallbacks}
          excludedTags={excludes}
          onFallbackChange={setFallbacks}
          onExcludedChange={setExcludes}
        />
      )}
      {section === 'advanced' && <XrayAdvancedSection />}
    </div>
  )
}
