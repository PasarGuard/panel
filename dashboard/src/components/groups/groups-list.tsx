import { useGetAllGroups, useModifyGroup } from '@/service/api'
import { GroupResponse } from '@/service/api'
import Group from './group'
import { useState, useMemo } from 'react'
import GroupModal, { groupFormSchema, GroupFormValues } from '@/components/dialogs/group-modal'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { ScrollArea } from '@/components/ui/scroll-area'
import { toast } from 'sonner'
import { useTranslation } from 'react-i18next'
import { queryClient } from '@/utils/query-client'
import useDirDetection from '@/hooks/use-dir-detection'
import { Skeleton } from '@/components/ui/skeleton'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { RefreshCw, Search, X } from 'lucide-react'
import { cn } from '@/lib/utils'

const initialDefaultValues: Partial<GroupFormValues> = {
  name: '',
  inbound_tags: [],
  is_disabled: false,
}

interface GroupsListProps {
  isDialogOpen: boolean
  onOpenChange: (open: boolean) => void
}

export default function GroupsList({ isDialogOpen, onOpenChange }: GroupsListProps) {
  const [editingGroup, setEditingGroup] = useState<GroupResponse | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const { t } = useTranslation()
  const modifyGroupMutation = useModifyGroup()
  const dir = useDirDetection()
  const { data: groupsData, isLoading, isFetching, refetch } = useGetAllGroups({})

  const form = useForm<GroupFormValues>({
    resolver: zodResolver(groupFormSchema),
    defaultValues: initialDefaultValues,
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

  return (
    <div className="w-full flex-1 space-y-4">
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
        <Button
          size="icon-md"
          variant="ghost"
          onClick={handleRefresh}
          className={cn('border', isFetching && 'opacity-70')}
          aria-label={t('autoRefresh.refreshNow')}
          title={t('autoRefresh.refreshNow')}
        >
          <RefreshCw className={cn('h-4 w-4', isFetching && 'animate-spin')} />
        </Button>
      </div>
      <ScrollArea className="h-[calc(100vh-8rem)]">
        <div dir={dir} className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
          {isLoading
            ? [...Array(6)].map((_, i) => (
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
              ))
            : filteredGroups?.map(group => <Group key={group.id} group={group} onEdit={handleEdit} onToggleStatus={handleToggleStatus} />)}
        </div>
      </ScrollArea>

      <GroupModal
        isDialogOpen={isDialogOpen}
        onOpenChange={(open: boolean) => {
          if (!open) {
            setEditingGroup(null)
            form.reset(initialDefaultValues)
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
