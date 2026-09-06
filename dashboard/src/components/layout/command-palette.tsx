import { CommandDialog, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList, CommandSeparator, CommandShortcut } from '@/components/ui/command'
import { useCommandPaletteStore, type CommandCreateTarget } from '@/hooks/use-command-palette-store'
import { useAdmin } from '@/hooks/use-admin'
import useDirDetection from '@/hooks/use-dir-detection'
import { useTheme } from '@/app/providers/theme-provider'
import { canReadResourcePage, hasPermission, isOwner } from '@/utils/rbac'
import { selectCoreEditorHasActualChanges } from '@/features/core-editor/kit/core-editor-change-state'
import { useCoreEditorStore } from '@/features/core-editor/state/core-editor-store'
import type { WgCoreSection, XrayCoreSection } from '@/features/core-editor/state/core-editor-store'
import {
  Cpu,
  FileUser,
  Group,
  LayoutDashboardIcon,
  ListTodo,
  Monitor,
  Moon,
  Palette,
  PieChart,
  Plus,
  Settings,
  Share2Icon,
  Sun,
  UserCog,
  UsersIcon,
} from 'lucide-react'
import { useCallback, useEffect, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { useLocation, useNavigate } from 'react-router'

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

const createRoutes: Record<CommandCreateTarget, string> = {
  user: '/users',
  group: '/groups',
  host: '/hosts',
  node: '/nodes',
  admin: '/admins',
  template: '/templates/user',
  core: '/nodes/cores/new',
}

function searchValue(...parts: Array<string | undefined>) {
  return parts
    .filter((part): part is string => Boolean(part))
    .map(part => part.replace(/[./]+/g, ' '))
    .join(' ')
    .replace(/\s+/g, ' ')
    .trim()
}

export function CommandPalette() {
  const { t } = useTranslation()
  const dir = useDirDetection()
  const navigate = useNavigate()
  const location = useLocation()
  const { admin } = useAdmin()
  const { setTheme } = useTheme()
  const open = useCommandPaletteStore(s => s.open)
  const setOpen = useCommandPaletteStore(s => s.setOpen)
  const requestCreate = useCommandPaletteStore(s => s.requestCreate)
  const kind = useCoreEditorStore(s => s.kind)
  const setActiveSection = useCoreEditorStore(s => s.setActiveSection)
  const discardDraft = useCoreEditorStore(s => s.discardDraft)
  const hasActualChanges = useCoreEditorStore(selectCoreEditorHasActualChanges)
  const syncMonacoFromDraft = useCoreEditorStore(s => s.syncMonacoFromDraft)

  const isCoreEditor = /^\/nodes\/cores\/[^/]+/.test(location.pathname)
  const coreSections = useMemo(() => (kind === 'wg' ? wgSections : xraySections), [kind])

  const navItems = useMemo(() => {
    const items: { title: string; url: string; icon: typeof UsersIcon }[] = []
    if (hasPermission(admin, 'system', 'read')) items.push({ title: 'dashboard', url: '/', icon: LayoutDashboardIcon })
    if (hasPermission(admin, 'users', 'read')) items.push({ title: 'users', url: '/users', icon: UsersIcon })
    if (hasPermission(admin, 'nodes', 'stats')) items.push({ title: 'statistics', url: '/statistics', icon: PieChart })
    if (canReadResourcePage(admin, 'hosts')) items.push({ title: 'hosts', url: '/hosts', icon: ListTodo })
    if (canReadResourcePage(admin, 'groups')) items.push({ title: 'groups', url: '/groups', icon: Group })
    if (canReadResourcePage(admin, 'admins')) items.push({ title: 'admins.title', url: '/admins', icon: UserCog })
    if (canReadResourcePage(admin, 'nodes')) items.push({ title: 'nodes.title', url: '/nodes', icon: Share2Icon })
    if (canReadResourcePage(admin, 'cores')) items.push({ title: 'settings.cores.title', url: '/nodes/cores', icon: Cpu })
    if (canReadResourcePage(admin, 'templates')) items.push({ title: 'templates.userTemplates', url: '/templates/user', icon: FileUser })
    if (isOwner(admin) || hasPermission(admin, 'system', 'update')) items.push({ title: 'settings.title', url: '/settings', icon: Settings })
    return items
  }, [admin])

  const createItems = useMemo(() => {
    const items: { target: CommandCreateTarget; title: string; icon: typeof Plus }[] = []
    if (hasPermission(admin, 'users', 'create')) items.push({ target: 'user', title: 'createUser', icon: UsersIcon })
    if (hasPermission(admin, 'groups', 'create')) items.push({ target: 'group', title: 'createGroup', icon: Group })
    if (hasPermission(admin, 'hosts', 'create')) items.push({ target: 'host', title: 'hostsDialog.addHost', icon: ListTodo })
    if (hasPermission(admin, 'nodes', 'create')) items.push({ target: 'node', title: 'nodes.addNode', icon: Share2Icon })
    if (hasPermission(admin, 'admins', 'create')) items.push({ target: 'admin', title: 'admins.createAdmin', icon: UserCog })
    if (hasPermission(admin, 'templates', 'create')) items.push({ target: 'template', title: 'templates.addTemplate', icon: FileUser })
    if (hasPermission(admin, 'cores', 'create')) items.push({ target: 'core', title: 'settings.cores.addCore', icon: Cpu })
    return items
  }, [admin])

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.repeat || event.altKey || !(event.metaKey || event.ctrlKey)) return
      if (event.code !== 'KeyK' && event.key !== 'k' && event.key !== 'K') return
      event.preventDefault()
      event.stopPropagation()
      setOpen(value => !value)
    }
    window.addEventListener('keydown', onKeyDown, true)
    return () => window.removeEventListener('keydown', onKeyDown, true)
  }, [setOpen])

  const go = useCallback(
    (url: string) => {
      setOpen(false)
      if (location.pathname !== url) navigate(url)
    },
    [location.pathname, navigate, setOpen],
  )

  const create = useCallback(
    (target: CommandCreateTarget) => {
      setOpen(false)
      requestCreate(target)
      const url = createRoutes[target]
      if (location.pathname !== url) navigate(url)
    },
    [location.pathname, navigate, requestCreate, setOpen],
  )

  return (
    <CommandDialog open={open} onOpenChange={setOpen}>
      <div dir={dir}>
        <CommandInput placeholder={t('commandPalette.placeholder', { defaultValue: 'Search pages, actions, theme…' })} />
        <CommandList>
          <CommandEmpty>{t('commandPalette.empty', { defaultValue: 'No results.' })}</CommandEmpty>
          <CommandGroup heading={t('commandPalette.navigate', { defaultValue: 'Navigate' })}>
            {navItems.map(item => {
              const label = t(item.title)
              return (
                <CommandItem key={item.url} value={searchValue(label, item.title, item.url, 'navigate')} onSelect={() => go(item.url)}>
                  <item.icon />
                  {label}
                </CommandItem>
              )
            })}
          </CommandGroup>
          {createItems.length > 0 && (
            <>
              <CommandSeparator />
              <CommandGroup heading={t('commandPalette.create', { defaultValue: 'Create' })}>
                {createItems.map(item => {
                  const label = t(item.title)
                  return (
                    <CommandItem key={item.target} value={searchValue(label, item.title, item.target, 'create', 'new', 'add')} onSelect={() => create(item.target)}>
                      <item.icon />
                      {label}
                    </CommandItem>
                  )
                })}
              </CommandGroup>
            </>
          )}
          <CommandSeparator />
          <CommandGroup heading={t('commandPalette.theme', { defaultValue: 'Theme' })}>
            <CommandItem
              value={searchValue(t('theme.light', { defaultValue: 'Light' }), 'theme light')}
              onSelect={() => {
                setTheme('light')
                setOpen(false)
              }}
            >
              <Sun />
              {t('theme.light', { defaultValue: 'Light' })}
            </CommandItem>
            <CommandItem
              value={searchValue(t('theme.dark', { defaultValue: 'Dark' }), 'theme dark')}
              onSelect={() => {
                setTheme('dark')
                setOpen(false)
              }}
            >
              <Moon />
              {t('theme.dark', { defaultValue: 'Dark' })}
            </CommandItem>
            <CommandItem
              value={searchValue(t('theme.system', { defaultValue: 'System' }), 'theme system')}
              onSelect={() => {
                setTheme('system')
                setOpen(false)
              }}
            >
              <Monitor />
              {t('theme.system', { defaultValue: 'System' })}
            </CommandItem>
            <CommandItem value={searchValue(t('settings.theme.title', { defaultValue: 'Theme settings' }), 'theme settings appearance')} onSelect={() => go('/settings/theme')}>
              <Palette />
              {t('settings.theme.title', { defaultValue: 'Theme settings' })}
            </CommandItem>
          </CommandGroup>
          {isCoreEditor && (
            <>
              <CommandSeparator />
              <CommandGroup heading={t('coreEditor.command.sections', { defaultValue: 'Sections' })}>
                {coreSections.map(section => {
                  const label = t(section.labelKey, { defaultValue: section.defaultLabel })
                  return (
                    <CommandItem
                      key={section.id}
                      value={searchValue(label, section.defaultLabel, section.id, 'section')}
                      onSelect={() => {
                        setActiveSection(section.id)
                        setOpen(false)
                      }}
                    >
                      {label}
                    </CommandItem>
                  )
                })}
              </CommandGroup>
              <CommandGroup heading={t('coreEditor.command.actions', { defaultValue: 'Actions' })}>
                <CommandItem
                  value={searchValue(t('coreEditor.command.discard', { defaultValue: 'Discard unsaved changes' }), 'discard')}
                  disabled={!hasActualChanges}
                  onSelect={() => {
                    discardDraft()
                    setOpen(false)
                  }}
                >
                  {t('coreEditor.command.discard', { defaultValue: 'Discard unsaved changes' })}
                </CommandItem>
                <CommandItem
                  value={searchValue(t('coreEditor.command.syncJson', { defaultValue: 'Refresh JSON preview from draft' }), 'sync json preview')}
                  onSelect={() => {
                    syncMonacoFromDraft()
                    setOpen(false)
                  }}
                >
                  {t('coreEditor.command.syncJson', { defaultValue: 'Refresh JSON preview from draft' })}
                </CommandItem>
              </CommandGroup>
            </>
          )}
        </CommandList>
      </div>
      <div className="text-muted-foreground flex items-center justify-end border-t px-3 py-2 text-xs">
        <CommandShortcut>⌘K</CommandShortcut>
      </div>
    </CommandDialog>
  )
}
