import { useGetAllGroups, useModifyGroup } from '@/service/api'
import { GroupResponse } from '@/service/api'
import Group from './group'
import { useState, useMemo } from 'react'
import GroupModal from '@/components/dialogs/group-modal'
import { groupFormDefaultValues, groupFormSchema, type GroupFormValues } from '@/components/forms/group-form'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { ScrollArea } from '@/components/ui/scroll-area'
import { toast } from 'sonner'
import { useTranslation } from 'react-i18next'
import { queryClient } from '@/utils/query-client'
import useDirDetection from '@/hooks/use-dir-detection'
import { Skeleton } from '@/components/ui/skeleton'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { RefreshCw, Search, X } from 'lucide-react'
import { cn } from '@/lib/utils'
import ViewToggle from '@/components/common/view-toggle'
import { ListGenerator } from '@/components/common/list-generator'
import { useGroupsListColumns } from '@/components/groups/use-groups-list-columns'
import { usePersistedViewMode } from '@/hooks/use-persisted-view-mode'

interface GroupsListProps {
  isDialogOpen: boolean
  onOpenChange: (open: boolean) => void
}

export default function GroupsList({ isDialogOpen, onOpenChange }: GroupsListProps) {
  const [editingGroup, setEditingGroup] = useState<GroupResponse | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [viewMode, setViewMode] = usePersistedViewMode('view-mode:groups')
  const { t } = useTranslation()
  const modifyGroupMutation = useModifyGroup()
  const dir = useDirDetection()
  const { data: groupsData, isLoading, isFetching, refetch } = useGetAllGroups({})

  const form = useForm<GroupFormValues>({
    resolver: zodResolver(groupFormSchema),
    defaultValues: groupFormDefaultValues,
  })

  const handleEdit = (group: GroupResponse) => {
    setEditingGroup(group)
    form.reset({
      name: group.name,
      inbound_tags: group.inbound_tags || [],
      is_disabled: group.is_disabled,
    })
    onOpenChange(true)
  }

  const handleToggleStatus = async (group: GroupResponse) => {
    try {
      await modifyGroupMutation.mutateAsync({
        groupId: group.id,
        data: {
          name: group.name,
          inbound_tags: group.inbound_tags,
          is_disabled: !group.is_disabled,
        },
      })

      toast.success(t('success', { defaultValue: 'Success' }), {
        description: t(group.is_disabled ? 'group.enableSuccess' : 'group.disableSuccess', {
          name: group.name,
          defaultValue: `Group "{name}" has been ${group.is_disabled ? 'enabled' : 'disabled'} successfully`,
        }),
      })

      // Invalidate the groups query to refresh the list
      queryClient.invalidateQueries({
        queryKey: ['/api/groups'],
      })
    } catch (error) {
      toast.error(t('error', { defaultValue: 'Error' }), {
        description: t(group.is_disabled ? 'group.enableFailed' : 'group.disableFailed', {
          name: group.name,
          defaultValue: `Failed to ${group.is_disabled ? 'enable' : 'disable'} group "{name}"`,
        }),
      })
    }
  }

  const filteredGroups = useMemo(() => {
    if (!groupsData?.groups || !searchQuery.trim()) return groupsData?.groups
    const query = searchQuery.toLowerCase().trim()
    return groupsData.groups.filter((group: GroupResponse) => group.name?.toLowerCase().includes(query))
  }, [groupsData?.groups, searchQuery])

  const handleRefresh = async () => {
    await refetch()
  }

  const listColumns = useGroupsListColumns({
    onEdit: handleEdit,
    onToggleStatus: handleToggleStatus,
  })

  const isCurrentlyLoading = isLoading || (isFetching && !groupsData)
  const isEmpty = !isCurrentlyLoading && (!filteredGroups || filteredGroups.length === 0) && !searchQuery.trim()
  const isSearchEmpty = !isCurrentlyLoading && (!filteredGroups || filteredGroups.length === 0) && searchQuery.trim() !== ''

  return (
    <div className={cn('w-full flex-1 space-y-4', dir === 'rtl' && 'rtl')}>
      {/* Search Input */}
      <div dir={dir} className="flex items-center gap-2 md:gap-4">
        <div className="relative min-w-0 flex-1 md:w-[calc(100%/3-10px)] md:flex-none">
          <Search className={cn('absolute', dir === 'rtl' ? 'right-2' : 'left-2', 'top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground')} />
          <Input placeholder={t('search')} value={searchQuery} onChange={e => setSearchQuery(e.target.value)} className={cn('pl-8 pr-10', dir === 'rtl' && 'pl-10 pr-8')} />
          {searchQuery && (
            <button onClick={() => setSearchQuery('')} className={cn('absolute', dir === 'rtl' ? 'left-2' : 'right-2', 'top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground')}>
              <X className="h-4 w-4" />
            </button>
          )}
        </div>
        <div className="flex flex-shrink-0 items-center gap-2">
          <Button
            size="icon-md"
            variant="ghost"
            onClick={handleRefresh}
            className={cn('h-9 w-9 rounded-lg border', isFetching && 'opacity-70')}
            aria-label={t('autoRefresh.refreshNow')}
            title={t('autoRefresh.refreshNow')}
          >
            <RefreshCw className={cn('h-4 w-4', isFetching && 'animate-spin')} />
          </Button>
          <ViewToggle value={viewMode} onChange={setViewMode} />
        </div>
      </div>
      {isEmpty && !isCurrentlyLoading && (
        <Card className="mb-12">
          <CardContent className="p-8 text-center">
            <div className="space-y-4">
              <h3 className="text-lg font-semibold">{t('group.noGroups')}</h3>
              <p className="mx-auto max-w-2xl text-muted-foreground">{t('group.noGroupsDescription')}</p>
            </div>
          </CardContent>
        </Card>
      )}
      {isSearchEmpty && !isCurrentlyLoading && (
        <Card className="mb-12">
          <CardContent className="p-8 text-center">
            <div className="space-y-4">
              <h3 className="text-lg font-semibold">{t('noResults')}</h3>
              <p className="mx-auto max-w-2xl text-muted-foreground">{t('group.noSearchResults')}</p>
            </div>
          </CardContent>
        </Card>
      )}
      {(isCurrentlyLoading || (!isEmpty && !isSearchEmpty)) && (
        <ScrollArea dir={dir} className="h-[calc(100vh-8rem)]">
          <ListGenerator
            data={filteredGroups || []}
            columns={listColumns}
            getRowId={group => group.id}
            isLoading={isCurrentlyLoading}
            loadingRows={6}
            className="gap-3"
            onRowClick={handleEdit}
            mode={viewMode}
            showEmptyState={false}
            renderGridItem={group => <Group group={group} onEdit={handleEdit} onToggleStatus={handleToggleStatus} />}
            renderGridSkeleton={i => (
              <Card key={i} className="px-4 py-5">
                <div className="flex items-center gap-2 sm:gap-3">
                  <Skeleton className="h-8 w-8 shrink-0 rounded-full" />
                  <div className="min-w-0 flex-1 space-y-2">
                    <Skeleton className="h-5 w-24 sm:w-32" />
                    <Skeleton className="h-4 w-20 sm:w-24" />
                  </div>
                  <Skeleton className="h-8 w-8 shrink-0" />
                </div>
              </Card>
            )}
          />
        </ScrollArea>
      )}

      <GroupModal
        isDialogOpen={isDialogOpen}
        onOpenChange={(open: boolean) => {
          if (!open) {
            setEditingGroup(null)
            form.reset(groupFormDefaultValues)
          }
          onOpenChange(open)
        }}
        form={form}
        editingGroup={!!editingGroup}
        editingGroupId={editingGroup?.id}
      />
    </div>
  )
}

