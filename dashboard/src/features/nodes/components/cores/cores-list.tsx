import { useBulkDeleteCores, useGetAllCores, useModifyCoreConfig } from '@/service/api'
import { CoreResponse } from '@/service/api'
import Core from './core'
import { lazy, Suspense, useState, useEffect, useMemo, useCallback } from 'react'
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
import { ListGeneratorGrid } from '@/components/common/list-generator-grid'
import { useCoresListColumns } from '@/features/nodes/components/cores/use-cores-list-columns'
import { usePersistedViewMode } from '@/hooks/use-persisted-view-mode'
import { BulkActionsBar } from '@/features/users/components/bulk-actions-bar'
import { BulkActionAlertDialog } from '@/features/users/components/bulk-action-alert-dialog'
import { useNavigate } from 'react-router'
import { zodResolver } from '@hookform/resolvers/zod'
import { useForm } from 'react-hook-form'
import { coreConfigFormDefaultValues, coreConfigFormSchema, type CoreBackendType, type CoreConfigFormValues } from '@/features/nodes/forms/core-config-form'
import { getCoresListUseConfigModal } from '@/utils/userPreferenceStorage'

const CoreConfigModal = lazy(() => import('@/features/nodes/dialogs/core-config-modal'))

interface CoresProps {
  cores?: CoreResponse[]
  onDuplicateCore?: (coreId: number | string) => void
  onDeleteCore?: (coreName: string, coreId: number) => void
}

export default function Cores({ cores, onDuplicateCore, onDeleteCore }: CoresProps) {
  const navigate = useNavigate()
  const [searchQuery, setSearchQuery] = useState('')
  const [viewMode, setViewMode] = usePersistedViewMode('view-mode:cores')
  const [selectedCoreIds, setSelectedCoreIds] = useState<number[]>([])
  const [bulkAction, setBulkAction] = useState<'delete' | null>(null)
  const [isCoreConfigModalOpen, setIsCoreConfigModalOpen] = useState(false)
  const [isEditingCoreInModal, setIsEditingCoreInModal] = useState(false)
  const [editingCoreIdInModal, setEditingCoreIdInModal] = useState<number | undefined>(undefined)
  const coreConfigForm = useForm<CoreConfigFormValues>({
    resolver: zodResolver(coreConfigFormSchema),
    defaultValues: coreConfigFormDefaultValues,
  })
  const { t } = useTranslation()
  const modifyCoreMutation = useModifyCoreConfig()
  const bulkDeleteCoresMutation = useBulkDeleteCores()
  const dir = useDirDetection()

  const { data: coresData, isLoading, isFetching, refetch } = useGetAllCores({})

  const openCoreConfigModalForCreate = useCallback(() => {
    setIsEditingCoreInModal(false)
    setEditingCoreIdInModal(undefined)
    setIsCoreConfigModalOpen(true)
  }, [])

  const openCoreConfigModalForEdit = useCallback(
    (core: CoreResponse) => {
      coreConfigForm.reset({
        name: core.name,
        type: (core.type ?? 'xray') as CoreBackendType,
        config: JSON.stringify(core.config ?? {}, null, 2),
        fallback_id: core.fallbacks_inbound_tags ?? [],
        excluded_inbound_ids: core.exclude_inbound_tags ?? [],
        restart_nodes: true,
      })
      setEditingCoreIdInModal(core.id)
      setIsEditingCoreInModal(true)
      setIsCoreConfigModalOpen(true)
    },
    [coreConfigForm],
  )

  const handleCoreConfigModalOpenChange = useCallback((open: boolean) => {
    setIsCoreConfigModalOpen(open)
    if (!open) {
      setIsEditingCoreInModal(false)
      setEditingCoreIdInModal(undefined)
    }
  }, [])

  useEffect(() => {
    const handleOpenDialog = () => {
      if (getCoresListUseConfigModal()) {
        openCoreConfigModalForCreate()
        return
      }
      navigate('/nodes/cores/new')
    }
    window.addEventListener('openCoreDialog', handleOpenDialog)
    return () => window.removeEventListener('openCoreDialog', handleOpenDialog)
  }, [navigate, openCoreConfigModalForCreate])

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
    } catch {
      toast.error(
        t('core.toggleFailed', {
          name: core.name,
        }),
      )
    }
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
    if (getCoresListUseConfigModal()) {
      openCoreConfigModalForEdit(core)
      return
    }
    navigate(`/nodes/cores/${core.id}`)
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
      {(isLoading || filteredCores.length > 0) &&
        (viewMode === 'grid' ? (
          <ListGeneratorGrid
            data={filteredCores}
            getRowId={core => core.id}
            isLoading={isLoading}
            loadingRows={6}
            className="gap-4"
            enableSelection
            injectSelectionProps
            selectedRowIds={selectedCoreIds}
            onSelectionChange={ids => setSelectedCoreIds(ids.map(id => Number(id)))}
            showEmptyState={false}
            renderItem={core => (
              <Core
                core={core}
                onEdit={() => handleRowEdit(core)}
                onToggleStatus={handleToggleStatus}
                onDuplicate={onDuplicateCore ? () => onDuplicateCore(core.id) : undefined}
                onDelete={onDeleteCore ? () => onDeleteCore(core.name, core.id) : undefined}
              />
            )}
            renderSkeleton={i => (
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
        ) : (
          <ListGenerator
            data={filteredCores}
            columns={listColumns}
            getRowId={core => core.id}
            isLoading={isLoading}
            loadingRows={6}
            className="gap-3"
            onRowClick={handleRowEdit}
            enableSelection
            selectedRowIds={selectedCoreIds}
            onSelectionChange={ids => setSelectedCoreIds(ids.map(id => Number(id)))}
            showEmptyState={false}
          />
        ))}

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

      {isCoreConfigModalOpen && (
        <Suspense fallback={null}>
          <CoreConfigModal
            isDialogOpen={isCoreConfigModalOpen}
            onOpenChange={handleCoreConfigModalOpenChange}
            form={coreConfigForm}
            editingCore={isEditingCoreInModal}
            editingCoreId={editingCoreIdInModal}
          />
        </Suspense>
      )}
    </div>
  )
}
