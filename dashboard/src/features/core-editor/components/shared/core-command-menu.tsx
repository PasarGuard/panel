import { CommandDialog, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList, CommandSeparator } from '@/components/ui/command'
import { selectCoreEditorHasActualChanges } from '@/features/core-editor/kit/core-editor-change-state'
import { useCoreEditorStore } from '@/features/core-editor/state/core-editor-store'
import type { XrayCoreSection, WgCoreSection } from '@/features/core-editor/state/core-editor-store'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'

const xraySections: { id: XrayCoreSection; labelKey: string; defaultLabel: string }[] = [
  { id: 'inbounds', labelKey: 'coreEditor.section.inbounds', defaultLabel: 'Inbounds' },
  { id: 'outbounds', labelKey: 'coreEditor.section.outbounds', defaultLabel: 'Outbounds' },
  { id: 'routing', labelKey: 'coreEditor.section.routing', defaultLabel: 'Routing' },
  { id: 'balancers', labelKey: 'coreEditor.section.balancers', defaultLabel: 'Balancers' },
  { id: 'dns', labelKey: 'coreEditor.section.dns', defaultLabel: 'DNS' },
  { id: 'bindings', labelKey: 'coreEditor.section.bindings', defaultLabel: 'Bindings' },
  { id: 'advanced', labelKey: 'coreEditor.section.advanced', defaultLabel: 'Advanced (JSON)' },
]

const wgSections: { id: WgCoreSection; labelKey: string; defaultLabel: string }[] = [
  { id: 'interface', labelKey: 'coreEditor.section.interface', defaultLabel: 'Interface' },
  { id: 'advanced', labelKey: 'coreEditor.section.advanced', defaultLabel: 'Advanced (JSON)' },
]

export function CoreCommandMenu() {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const kind = useCoreEditorStore(s => s.kind)
  const setActiveSection = useCoreEditorStore(s => s.setActiveSection)
  const discardDraft = useCoreEditorStore(s => s.discardDraft)
  const hasActualChanges = useCoreEditorStore(selectCoreEditorHasActualChanges)
  const syncMonacoFromDraft = useCoreEditorStore(s => s.syncMonacoFromDraft)

  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if ((e.key === 'k' || e.key === 'K') && (e.metaKey || e.ctrlKey)) {
        e.preventDefault()
        setOpen(o => !o)
      }
    }
    window.addEventListener('keydown', down)
    return () => window.removeEventListener('keydown', down)
  }, [])

  const sections = useMemo(() => (kind === 'wg' ? wgSections : xraySections), [kind])

  const go = useCallback(
    (id: XrayCoreSection | WgCoreSection) => {
      setActiveSection(id)
      setOpen(false)
    },
    [setActiveSection],
  )

  return (
    <CommandDialog open={open} onOpenChange={setOpen}>
      <CommandInput placeholder={t('coreEditor.command.placeholder', { defaultValue: 'Jump to section…' })} />
      <CommandList>
        <CommandEmpty>{t('coreEditor.command.empty', { defaultValue: 'No results.' })}</CommandEmpty>
        <CommandGroup heading={t('coreEditor.command.sections', { defaultValue: 'Sections' })}>
          {sections.map(s => (
            <CommandItem key={s.id} value={s.defaultLabel} onSelect={() => go(s.id)}>
              {t(s.labelKey, { defaultValue: s.defaultLabel })}
            </CommandItem>
          ))}
        </CommandGroup>
        <CommandSeparator />
        <CommandGroup heading={t('coreEditor.command.actions', { defaultValue: 'Actions' })}>
          <CommandItem
            value="discard"
            disabled={!hasActualChanges}
            onSelect={() => {
              discardDraft()
              setOpen(false)
            }}
          >
            {t('coreEditor.command.discard', { defaultValue: 'Discard unsaved changes' })}
          </CommandItem>
          <CommandItem
            value="sync json"
            onSelect={() => {
              syncMonacoFromDraft()
              setOpen(false)
            }}
          >
            {t('coreEditor.command.syncJson', { defaultValue: 'Refresh JSON preview from draft' })}
          </CommandItem>
        </CommandGroup>
      </CommandList>
    </CommandDialog>
  )
}
