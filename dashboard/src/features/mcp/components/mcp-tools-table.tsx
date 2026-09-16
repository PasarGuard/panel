import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ChevronDown, ShieldAlert } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { Skeleton } from '@/components/ui/skeleton'
import { Switch } from '@/components/ui/switch'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'
import type { MCPToolInfo } from '@/service/api'

interface McpToolsTableProps {
  tools: MCPToolInfo[]
  isLoading?: boolean
  disabledTools: string[]
  defaultDisabledTools: string[]
  readOnlyMode: boolean
  canUpdate: boolean
  onDisabledToolsChange: (next: string[]) => void
}

export function McpToolsTable({ tools, isLoading = false, disabledTools, defaultDisabledTools, readOnlyMode, canUpdate, onDisabledToolsChange }: McpToolsTableProps) {
  const { t } = useTranslation()

  const groups = useMemo(() => {
    const map = new Map<string, MCPToolInfo[]>()
    for (const tool of tools) {
      const list = map.get(tool.group) ?? []
      list.push(tool)
      map.set(tool.group, list)
    }
    return Array.from(map.entries())
  }, [tools])

  const disabledSet = useMemo(() => new Set(disabledTools), [disabledTools])
  const [openGroups, setOpenGroups] = useState<Record<string, boolean>>({})
  const allOpen = groups.length > 0 && groups.every(([group]) => openGroups[group])

  const setAllGroups = (open: boolean) => {
    setOpenGroups(Object.fromEntries(groups.map(([group]) => [group, open])))
  }

  const setGroupMode = (groupTools: MCPToolInfo[], mode: 'all' | 'read' | 'off') => {
    if (!canUpdate) return
    const next = new Set(disabledSet)
    for (const tool of groupTools) {
      const enabled = mode === 'all' || (mode === 'read' && tool.read_only)
      if (enabled) next.delete(tool.name)
      else next.add(tool.name)
    }
    onDisabledToolsChange(Array.from(next))
  }

  const modeOf = (groupTools: MCPToolInfo[]): 'all' | 'read' | 'off' | '' => {
    const enabled = groupTools.filter(tool => !disabledSet.has(tool.name))
    if (enabled.length === groupTools.length) return 'all'
    if (enabled.length === 0) return 'off'
    if (enabled.every(tool => tool.read_only) && groupTools.filter(tool => tool.read_only).every(tool => !disabledSet.has(tool.name))) return 'read'
    return ''
  }

  const setTools = (names: string[], enabled: boolean) => {
    if (!canUpdate) return
    const next = new Set(disabledSet)
    for (const name of names) {
      if (enabled) next.delete(name)
      else next.add(name)
    }
    onDisabledToolsChange(Array.from(next))
  }

  const permissionLabel = (tool: MCPToolInfo) => {
    if (tool.owner_only) return t('mcp.tools.ownerOnly')
    if (!tool.permissions.length) return '—'
    return tool.permissions
      .map(permission => {
        const resource = t(`adminRoles.resources.${permission.resource}`, { defaultValue: permission.resource })
        const action = t(`adminRoles.actions.${permission.resource}.${permission.action}`, {
          defaultValue: t(`adminRoles.actions.common.${permission.action}`, { defaultValue: permission.action }),
        })
        return `${resource} · ${action}`
      })
      .join(', ')
  }

  if (isLoading) {
    return (
      <div className="space-y-2">
        {[...Array(6)].map((_, index) => (
          <Skeleton key={index} className="h-10" />
        ))}
      </div>
    )
  }

  if (!tools.length) {
    return <div className="bg-muted/40 text-muted-foreground rounded-md border border-dashed px-3 py-6 text-center text-xs sm:text-sm">{t('mcp.tools.noTools')}</div>
  }

  return (
    <div className="space-y-3">
      <div className="flex justify-end gap-1">
        {canUpdate && (
          <Button type="button" size="sm" variant="ghost" className="h-7 px-2 text-xs" onClick={() => onDisabledToolsChange([...defaultDisabledTools])}>
            {t('mcp.tools.resetDefaults')}
          </Button>
        )}
        <Button type="button" size="sm" variant="ghost" className="h-7 px-2 text-xs" onClick={() => setAllGroups(!allOpen)}>
          {allOpen ? t('mcp.tools.collapseAll') : t('mcp.tools.expandAll')}
        </Button>
      </div>
      {groups.map(([group, groupTools]) => {
        const enabledCount = groupTools.filter(tool => !disabledSet.has(tool.name)).length
        const groupMode = modeOf(groupTools)
        const isOpen = !!openGroups[group]

        return (
          <Collapsible key={group} open={isOpen} onOpenChange={open => setOpenGroups(prev => ({ ...prev, [group]: open }))} className="bg-background rounded-md border">
            <div className={cn('flex items-center justify-between gap-2 px-3 py-2', isOpen && 'border-b')}>
              <CollapsibleTrigger asChild>
                <button type="button" className="flex min-w-0 flex-1 items-center gap-2 text-start">
                  <ChevronDown className={cn('text-muted-foreground h-4 w-4 shrink-0 transition-transform', !isOpen && '-rotate-90 rtl:rotate-90')} />
                  <span className="text-sm font-medium">{t(`mcp.groups.${group}`, { defaultValue: group })}</span>
                  <Badge variant={enabledCount === groupTools.length ? 'secondary' : enabledCount === 0 ? 'red' : 'yellow'} className="text-[10px]">
                    {enabledCount}/{groupTools.length}
                  </Badge>
                </button>
              </CollapsibleTrigger>
              {canUpdate && (
                <ToggleGroup type="single" value={groupMode} onValueChange={mode => mode && setGroupMode(groupTools, mode as 'all' | 'read' | 'off')} className="h-8 rounded-md border p-0.5">
                  <ToggleGroupItem value="all" size="sm" className="data-[state=on]:bg-primary data-[state=on]:text-primary-foreground h-7 px-2 text-xs">
                    {t('mcp.tools.modeAll')}
                  </ToggleGroupItem>
                  <ToggleGroupItem value="read" size="sm" className="data-[state=on]:bg-primary data-[state=on]:text-primary-foreground h-7 px-2 text-xs">
                    {t('mcp.tools.modeRead')}
                  </ToggleGroupItem>
                  <ToggleGroupItem value="off" size="sm" className="data-[state=on]:bg-primary data-[state=on]:text-primary-foreground h-7 px-2 text-xs">
                    {t('mcp.tools.modeOff')}
                  </ToggleGroupItem>
                </ToggleGroup>
              )}
            </div>
            <CollapsibleContent className="overflow-x-auto">
              <Table className="min-w-[640px] table-fixed">
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-[46%]">{t('mcp.tools.name')}</TableHead>
                    <TableHead className="w-[16%]">{t('mcp.tools.kind')}</TableHead>
                    <TableHead className="w-[26%]">{t('mcp.tools.permission')}</TableHead>
                    <TableHead className="w-[12%] text-end">{t('mcp.tools.enabled')}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {groupTools.map(tool => {
                    const isDisabled = disabledSet.has(tool.name)
                    const hiddenByReadOnly = readOnlyMode && !tool.read_only

                    return (
                      <TableRow key={tool.name} className={cn((isDisabled || hiddenByReadOnly) && 'opacity-60')}>
                        <TableCell>
                          <div className="flex flex-col gap-0.5" title={`${tool.method} ${tool.path}`}>
                            <span className="text-xs font-medium sm:text-sm">{tool.title}</span>
                            <span className="text-muted-foreground line-clamp-1 text-xs">{tool.description}</span>
                          </div>
                        </TableCell>
                        <TableCell>
                          <Badge variant={tool.destructive ? 'red' : tool.read_only ? 'secondary' : 'yellow'} className="text-[10px]">
                            {tool.destructive ? t('mcp.tools.destructive') : tool.read_only ? t('mcp.tools.readOnly') : t('mcp.tools.write')}
                          </Badge>
                        </TableCell>
                        <TableCell>
                          <span className="text-muted-foreground line-clamp-2 text-xs">{permissionLabel(tool)}</span>
                        </TableCell>
                        <TableCell className="text-end">
                          <div className="flex items-center justify-end gap-2">
                            {hiddenByReadOnly && !isDisabled && (
                              <Tooltip>
                                <TooltipTrigger asChild>
                                  <ShieldAlert className="text-muted-foreground h-4 w-4" />
                                </TooltipTrigger>
                                <TooltipContent>{t('mcp.tools.hiddenByReadOnly')}</TooltipContent>
                              </Tooltip>
                            )}
                            <Switch checked={!isDisabled} onCheckedChange={checked => setTools([tool.name], checked)} disabled={!canUpdate} aria-label={tool.name} />
                          </div>
                        </TableCell>
                      </TableRow>
                    )
                  })}
                </TableBody>
              </Table>
            </CollapsibleContent>
          </Collapsible>
        )
      })}
    </div>
  )
}
