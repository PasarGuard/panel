import { cn } from '@/lib/utils'
import { useCoreEditorStore } from '@/features/core-editor/state/core-editor-store'
import { WG_CORE_SECTION_NAV, XRAY_CORE_SECTION_NAV } from '@/features/core-editor/kit/core-section-nav'
import { useTranslation } from 'react-i18next'

/** Horizontal section tabs — same spacing and triggers as `_dashboard.nodes` primary tabs. */
export function CoreSectionTabs({ className }: { className?: string }) {
  const { t } = useTranslation()
  const kind = useCoreEditorStore(s => s.kind)
  const active = useCoreEditorStore(s => s.activeSection)
  const setActive = useCoreEditorStore(s => s.setActiveSection)
  const items = kind === 'wg' ? WG_CORE_SECTION_NAV : XRAY_CORE_SECTION_NAV

  return (
    <div className={cn('flex w-full border-b px-4', className)} role="tablist" aria-label={t('coreEditor.section.label', { defaultValue: 'Section' })}>
      <div className="scrollbar-none flex min-w-0 flex-1 overflow-x-auto">
        {items.map(item => {
          const Icon = item.icon
          const isActive = active === item.id
          return (
            <button
              key={item.id}
              type="button"
              role="tab"
              aria-selected={isActive}
              onClick={() => setActive(item.id)}
              className={cn(
                'relative shrink-0 px-3 py-2 text-sm font-medium transition-colors',
                isActive ? 'border-b-2 border-primary text-foreground' : 'text-muted-foreground hover:text-foreground',
              )}
            >
              <span className="flex items-center gap-1.5 whitespace-nowrap">
                <Icon className="h-4 w-4 shrink-0" aria-hidden />
                {t(item.labelKey, { defaultValue: item.defaultLabel })}
              </span>
            </button>
          )
        })}
      </div>
    </div>
  )
}

/** Non-interactive tab strip matching {@link CoreSectionTabs} (loading / skeleton shell). */
export function CoreSectionTabsPlaceholder({
  kind,
  activeSectionId,
  className,
}: {
  kind: 'xray' | 'wg'
  /** Defaults: inbounds (xray) / interface (wg). */
  activeSectionId?: string
  className?: string
}) {
  const { t } = useTranslation()
  const items = kind === 'wg' ? WG_CORE_SECTION_NAV : XRAY_CORE_SECTION_NAV
  const active =
    activeSectionId ?? (kind === 'wg' ? 'interface' : 'inbounds')

  return (
    <div
      className={cn('flex w-full border-b px-4', className)}
      role="presentation"
      aria-busy="true"
      aria-label={t('coreEditor.section.label', { defaultValue: 'Section' })}
    >
      <div className="scrollbar-none flex min-w-0 flex-1 overflow-x-auto">
        {items.map(item => {
          const Icon = item.icon
          const isActive = active === item.id
          return (
            <div
              key={item.id}
              className={cn(
                'relative shrink-0 px-3 py-2 text-sm font-medium',
                isActive ? 'border-b-2 border-primary text-foreground' : 'text-muted-foreground',
              )}
            >
              <span className="flex items-center gap-1.5 whitespace-nowrap">
                <Icon className="h-4 w-4 shrink-0" aria-hidden />
                {t(item.labelKey, { defaultValue: item.defaultLabel })}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
