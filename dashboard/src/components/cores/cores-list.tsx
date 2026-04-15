import { useBulkDeleteCores, useGetAllCores, useModifyCoreConfig } from '@/service/api'
import { CoreResponse } from '@/service/api'
import Core from './core'
import { useState, useEffect, useMemo } from 'react'
import CoreConfigModal from '@/components/dialogs/core-config-modal'
import { coreConfigFormDefaultValues, coreConfigFormSchema, type CoreConfigFormValues } from '@/components/forms/core-config-form'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
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
import ViewToggle from '@/components/common/view-toggle'
import { ListGenerator } from '@/components/common/list-generator'
import { useCoresListColumns } from '@/components/cores/use-cores-list-columns'
import { usePersistedViewMode } from '@/hooks/use-persisted-view-mode'
import { BulkActionsBar } from '@/components/users/bulk-actions-bar'
import { BulkActionAlertDialog } from '@/components/users/bulk-action-alert-dialog'

interface CoresProps {
  isDialogOpen?: boolean
  onOpenChange?: (open: boolean) => void
  cores?: CoreResponse[]
  onEditCore?: (coreId: number | string) => void
  onDuplicateCore?: (coreId: number | string) => void
  onDeleteCore?: (coreName: string, coreId: number) => void
}

export default function Cores({ isDialogOpen, onOpenChange, cores, onEditCore, onDuplicateCore, onDeleteCore }: CoresProps) {
  const [editingCore, setEditingCore] = useState<CoreResponse | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [viewMode, setViewMode] = usePersistedViewMode('view-mode:cores')
  const [selectedCoreIds, setSelectedCoreIds] = useState<number[]>([])
  const [bulkAction, setBulkAction] = useState<'delete' | null>(null)
  const { t } = useTranslation()
  const modifyCoreMutation = useModifyCoreConfig()
  const bulkDeleteCoresMutation = useBulkDeleteCores()
  const dir = useDirDetection()

  const { data: coresData, isLoading, isFetching, refetch } = useGetAllCores({})
  const shouldRenderLocalModal = !onEditCore

  useEffect(() => {
    const handleOpenDialog = () => onOpenChange?.(true)
    window.addEventListener('openCoreDialog', handleOpenDialog)
    return () => window.removeEventListener('openCoreDialog', handleOpenDialog)
  }, [onOpenChange])

  const form = useForm<CoreConfigFormValues>({
    resolver: zodResolver(coreConfigFormSchema),
    defaultValues: coreConfigFormDefaultValues,
  })

  const handleEdit = (core: CoreResponse) => {
    setEditingCore(core)
    form.reset({
      name: core.name,
      type: core.type || 'xray',
      config: JSON.stringify(core.config, null, 2),
      fallback_id: core.fallbacks_inbound_tags
        ? core.fallbacks_inbound_tags
            .join(',')
            .split(',')
            .map((id: string) => id.trim())
            .filter((id: string) => id.trim() !== '')
        : [],
      excluded_inbound_ids: core.exclude_inbound_tags
        ? core.exclude_inbound_tags
            .join(',')
            .split(',')
            .map((id: string) => id.trim())
            .filter((id: string) => id.trim() !== '')
        : [],
    })
    onOpenChange?.(true)
  }

  const handleToggleStatus = async (core: CoreResponse) => {
    try {
      await modifyCoreMutation.mutateAsync({
        coreId: core.id,
        data: {
          name: core.name,
          config: core.config,
          exclude_inbound_tags: core.exclude_inbound_tags,
        },
        params: {
          restart_nodes: true,
        },
      })

      toast.success(
        t('core.toggleSuccess', {
          name: core.name,
        }),
      )

      queryClient.invalidateQueries({
        queryKey: ['/api/cores'],
      })
      queryClient.invalidateQueries({
        queryKey: ['/api/cores/simple'],
      })
    } catch (error) {
      toast.error(
        t('core.toggleFailed', {
          name: core.name,
        }),
      )
    }
  }

  const handleModalClose = (open: boolean) => {
    if (!open) {
      setEditingCore(null)
      form.reset(coreConfigFormDefaultValues)
      // Refresh cores data when modal closes
      refetch()
    }
    onOpenChange?.(open)
  }

  const coresList = cores || coresData?.cores || []

  const filteredCores = useMemo(() => {
    if (!searchQuery.trim()) return coresList
    const query = searchQuery.toLowerCase().trim()
    return coresList.filter((core: CoreResponse) => core.name?.toLowerCase().includes(query))
  }, [coresList, searchQuery])

  const handleRefreshClick = async () => {
    await refetch()
  }

  const clearSelection = () => {
    setSelectedCoreIds([])
  }

  const handleRowEdit = (core: CoreResponse) => {
    if (onEditCore) {
      onEditCore(core.id)
      return
    }
    handleEdit(core)
  }

  const handleBulkDelete = async () => {
    if (!selectedCoreIds.length) return

    try {
      const response = await bulkDeleteCoresMutation.mutateAsync({
        data: {
          ids: selectedCoreIds,
        },
      })
      toast.success(t('success', { defaultValue: 'Success' }), {
        description: t('core.bulkDeleteSuccess', {
          count: response.count,
          defaultValue: '{{count}} cores deleted successfully.',
        }),
      })
      clearSelection()
      setBulkAction(null)
      queryClient.invalidateQueries({ queryKey: ['/api/cores'] })
      queryClient.invalidateQueries({ queryKey: ['/api/cores/simple'] })
    } catch (error: any) {
      toast.error(t('error', { defaultValue: 'Error' }), {
        description:
          error?.data?.detail ||
          error?.message ||
          t('core.bulkDeleteFailed', {
            defaultValue: 'Failed to delete selected cores.',
          }),
      })
    }
  }

  const listColumns = useCoresListColumns({
    onEdit: handleRowEdit,
    onDuplicate: onDuplicateCore,
    onDelete: onDeleteCore,
  })

  return (
    <div className={cn('flex w-full flex-col gap-4 pt-4', dir === 'rtl' && 'rtl')}>
      <div className="flex items-center gap-2 md:gap-3">
        {/* Search Input */}
        <div className="relative min-w-0 flex-1 md:w-[calc(100%/3-10px)] md:flex-none" dir={dir}>
          <Search className={cn('absolute', dir === 'rtl' ? 'right-2' : 'left-2', 'top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground')} />
          <Input placeholder={t('search')} value={searchQuery} onChange={e => setSearchQuery(e.target.value)} className={cn('pl-8 pr-10', dir === 'rtl' && 'pl-10 pr-8')} />
          {searchQuery && (
            <button type="button" onClick={() => setSearchQuery('')} className={cn('absolute', dir === 'rtl' ? 'left-2' : 'right-2', 'top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground')}>
              <X className="h-4 w-4" />
            </button>
          )}
        </div>
        <div className="flex flex-shrink-0 items-center gap-2">
          <Button
            type="button"
            size="icon-md"
            variant="ghost"
            onClick={handleRefreshClick}
            className={cn('h-9 w-9 rounded-lg border', isFetching && 'opacity-70')}
            aria-label={t('autoRefresh.refreshNow')}
            title={t('autoRefresh.refreshNow')}
          >
            <RefreshCw className={cn('h-4 w-4', isFetching && 'animate-spin')} />
          </Button>
          <ViewToggle value={viewMode} onChange={setViewMode} />
        </div>
      </div>
      <BulkActionsBar selectedCount={selectedCoreIds.length} onClear={clearSelection} onDelete={selectedCoreIds.length > 0 ? () => setBulkAction('delete') : undefined} />
      {(isLoading || filteredCores.length > 0) && (
        <ListGenerator
          data={filteredCores}
          columns={listColumns}
          getRowId={core => core.id}
          isLoading={isLoading}
          loadingRows={6}
          className="gap-3"
          onRowClick={handleRowEdit}
          mode={viewMode}
          enableSelection
          enableGridSelection
          selectedRowIds={selectedCoreIds}
          onSelectionChange={ids => setSelectedCoreIds(ids.map(id => Number(id)))}
          showEmptyState={false}
          renderGridItem={core => (
            <Core
              core={core}
              onEdit={onEditCore ? () => onEditCore(core.id) : () => handleEdit(core)}
              onToggleStatus={handleToggleStatus}
              onDuplicate={onDuplicateCore ? () => onDuplicateCore(core.id) : undefined}
              onDelete={onDeleteCore ? () => onDeleteCore(core.name, core.id) : undefined}
            />
          )}
          renderGridSkeleton={i => (
            <Card key={i} className="px-4 py-5">
              <div className="flex items-center gap-2 sm:gap-3">
                <Skeleton className="h-2 w-2 shrink-0 rounded-full" />
                <Skeleton className="h-5 w-24 sm:w-32" />
                <div className="ml-auto shrink-0">
                  <Skeleton className="h-8 w-8" />
                </div>
              </div>
            </Card>
          )}
        />
      )}

      {shouldRenderLocalModal && <CoreConfigModal isDialogOpen={!!isDialogOpen} onOpenChange={handleModalClose} form={form} editingCore={!!editingCore} editingCoreId={editingCore?.id} />}
      <BulkActionAlertDialog
        open={bulkAction === 'delete'}
        onOpenChange={open => setBulkAction(open ? 'delete' : null)}
        title={t('core.bulkDeleteTitle', { defaultValue: 'Delete Selected Cores' })}
        description={t('core.bulkDeletePrompt', {
          count: selectedCoreIds.length,
          defaultValue: 'Are you sure you want to delete {{count}} selected cores? This action cannot be undone.',
        })}
        actionLabel={t('delete')}
        onConfirm={handleBulkDelete}
        isPending={bulkDeleteCoresMutation.isPending}
        destructive
      />
    </div>
  )
}
