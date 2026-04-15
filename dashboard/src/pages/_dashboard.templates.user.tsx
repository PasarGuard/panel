import UserTemplate from '../components/templates/user-template'
import { useBulkDeleteUserTemplates, useBulkDisableUserTemplates, useBulkEnableUserTemplates, useGetUserTemplates, useModifyUserTemplate, UserTemplateResponse } from '@/service/api'
import { Skeleton } from '@/components/ui/skeleton'
import { Card, CardContent } from '@/components/ui/card'
import UserTemplateModal from '@/components/dialogs/user-template-modal'
import { createUserTemplateFormResolver, userTemplateFormDefaultValues, type UserTemplatesFromValueInput } from '@/components/forms/user-template-form'
import { useState, useMemo, useEffect } from 'react'
import { useForm } from 'react-hook-form'
import { queryClient } from '@/utils/query-client.ts'
import { toast } from 'sonner'
import { useTranslation } from 'react-i18next'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Power, PowerOff, RefreshCw, Search, Trash2, X } from 'lucide-react'
import useDirDetection from '@/hooks/use-dir-detection'
import { cn } from '@/lib/utils'
import ViewToggle from '@/components/common/view-toggle'
import { ListGenerator } from '@/components/common/list-generator'
import { useUserTemplatesListColumns } from '@/components/templates/use-user-templates-list-columns'
import { usePersistedViewMode } from '@/hooks/use-persisted-view-mode'
import { bytesToFormGigabytes } from '@/utils/formatByte'
import { BulkActionItem, BulkActionsBar } from '@/components/users/bulk-actions-bar'
import { BulkActionAlertDialog } from '@/components/users/bulk-action-alert-dialog'

type BulkUserTemplateActionType = 'delete' | 'disable' | 'enable'

interface BulkActionDialogConfig {
  title: string
  description: string
  actionLabel: string
  onConfirm: () => Promise<void>
  isPending: boolean
  destructive?: boolean
}

export default function UserTemplates() {
  const [isDialogOpen, setIsDialogOpen] = useState(false)
  const [editingUserTemplate, setEditingUserTemplate] = useState<UserTemplateResponse | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [viewMode, setViewMode] = usePersistedViewMode('view-mode:templates')
  const [selectedTemplateIds, setSelectedTemplateIds] = useState<number[]>([])
  const [bulkAction, setBulkAction] = useState<BulkUserTemplateActionType | null>(null)
  const { data: userTemplates, isLoading, isFetching, refetch } = useGetUserTemplates()
  const { t } = useTranslation()
  const form = useForm<UserTemplatesFromValueInput>({
    resolver: useMemo(() => createUserTemplateFormResolver(t), [t]),
    defaultValues: userTemplateFormDefaultValues,
  })
  const modifyUserTemplateMutation = useModifyUserTemplate()
  const bulkDeleteUserTemplatesMutation = useBulkDeleteUserTemplates()
  const bulkDisableUserTemplatesMutation = useBulkDisableUserTemplates()
  const bulkEnableUserTemplatesMutation = useBulkEnableUserTemplates()
  const dir = useDirDetection()

  useEffect(() => {
    const handleOpenDialog = () => {
      setEditingUserTemplate(null)
      form.reset(userTemplateFormDefaultValues)
      setIsDialogOpen(true)
    }
    window.addEventListener('openUserTemplateDialog', handleOpenDialog)
    return () => window.removeEventListener('openUserTemplateDialog', handleOpenDialog)
  }, [form])

  const handleEdit = (userTemplate: UserTemplateResponse) => {
    setEditingUserTemplate(userTemplate)
    form.reset({
      name: userTemplate.name || undefined,
      status: userTemplate.status || undefined,
      data_limit: bytesToFormGigabytes(userTemplate.data_limit),
      expire_duration: userTemplate.expire_duration || undefined,
      method: userTemplate.extra_settings?.method || undefined,
      flow: userTemplate.extra_settings?.flow || undefined,
      groups: userTemplate.group_ids || undefined,
      username_prefix: userTemplate.username_prefix || undefined,
      username_suffix: userTemplate.username_suffix || undefined,
      on_hold_timeout: typeof userTemplate.on_hold_timeout === 'number' ? userTemplate.on_hold_timeout : undefined,
      data_limit_reset_strategy: userTemplate.data_limit_reset_strategy || undefined,
      reset_usages: userTemplate.reset_usages || false,
    })

    setIsDialogOpen(true)
  }

  const handleToggleStatus = async (template: UserTemplateResponse) => {
    try {
      await modifyUserTemplateMutation.mutateAsync({
        templateId: template.id,
        data: {
          name: template.name,
          data_limit: template.data_limit,
          expire_duration: template.expire_duration,
          username_prefix: template.username_prefix,
          username_suffix: template.username_suffix,
          group_ids: template.group_ids,
          status: template.status,
          reset_usages: template.reset_usages,
          is_disabled: !template.is_disabled,
          data_limit_reset_strategy: template.data_limit_reset_strategy,
          on_hold_timeout: template.on_hold_timeout,
          extra_settings: template.extra_settings,
        },
      })

      toast.success(t('success', { defaultValue: 'Success' }), {
        description: t(template.is_disabled ? 'templates.enableSuccess' : 'templates.disableSuccess', {
          name: template.name,
          defaultValue: `Template "{name}" has been ${template.is_disabled ? 'enabled' : 'disabled'} successfully`,
        }),
      })

      queryClient.invalidateQueries({
        queryKey: ['/api/user_templates'],
      })
    } catch {
      toast.error(t('error', { defaultValue: 'Error' }), {
        description: t(template.is_disabled ? 'templates.enableFailed' : 'templates.disableFailed', {
          name: template.name,
          defaultValue: `Failed to ${template.is_disabled ? 'enable' : 'disable'} Template "{name}"`,
        }),
      })
    }
  }

  const filteredTemplates = useMemo(() => {
    if (!userTemplates || !searchQuery.trim()) return userTemplates
    const query = searchQuery.toLowerCase().trim()
    return userTemplates.filter(
      (template: UserTemplateResponse) =>
        template.name?.toLowerCase().includes(query) || template.username_prefix?.toLowerCase().includes(query) || template.username_suffix?.toLowerCase().includes(query),
    )
  }, [userTemplates, searchQuery])

  const listColumns = useUserTemplatesListColumns({ onEdit: handleEdit, onToggleStatus: handleToggleStatus })
  const clearSelection = () => {
    setSelectedTemplateIds([])
  }

  const handleBulkDelete = async () => {
    if (!selectedTemplateIds.length) return

    try {
      const response = await bulkDeleteUserTemplatesMutation.mutateAsync({
        data: {
          ids: selectedTemplateIds,
        },
      })
      toast.success(t('success', { defaultValue: 'Success' }), {
        description: t('templates.bulkDeleteSuccess', {
          count: response.count,
          defaultValue: '{{count}} user templates deleted successfully.',
        }),
      })
      clearSelection()
      setBulkAction(null)
      queryClient.invalidateQueries({
        queryKey: ['/api/user_templates'],
      })
    } catch (error: any) {
      toast.error(t('error', { defaultValue: 'Error' }), {
        description:
          error?.data?.detail ||
          error?.message ||
          t('templates.bulkDeleteFailed', {
            defaultValue: 'Failed to delete selected user templates.',
          }),
      })
    }
  }

  const handleBulkDisable = async () => {
    if (!selectedDisableEligibleIds.length) return

    try {
      const response = await bulkDisableUserTemplatesMutation.mutateAsync({
        data: {
          ids: selectedDisableEligibleIds,
        },
      })
      toast.success(t('success', { defaultValue: 'Success' }), {
        description: t('templates.bulkDisableSuccess', {
          count: response.count,
          defaultValue: '{{count}} user templates disabled successfully.',
        }),
      })
      clearSelection()
      setBulkAction(null)
      queryClient.invalidateQueries({
        queryKey: ['/api/user_templates'],
      })
    } catch (error: any) {
      toast.error(t('error', { defaultValue: 'Error' }), {
        description: error?.data?.detail || error?.message || t('templates.bulkDisableFailed', { defaultValue: 'Failed to disable selected user templates.' }),
      })
    }
  }

  const handleBulkEnable = async () => {
    if (!selectedEnableEligibleIds.length) return

    try {
      const response = await bulkEnableUserTemplatesMutation.mutateAsync({
        data: {
          ids: selectedEnableEligibleIds,
        },
      })
      toast.success(t('success', { defaultValue: 'Success' }), {
        description: t('templates.bulkEnableSuccess', {
          count: response.count,
          defaultValue: '{{count}} user templates enabled successfully.',
        }),
      })
      clearSelection()
      setBulkAction(null)
      queryClient.invalidateQueries({
        queryKey: ['/api/user_templates'],
      })
    } catch (error: any) {
      toast.error(t('error', { defaultValue: 'Error' }), {
        description: error?.data?.detail || error?.message || t('templates.bulkEnableFailed', { defaultValue: 'Failed to enable selected user templates.' }),
      })
    }
  }

  const isCurrentlyLoading = isLoading || (isFetching && !userTemplates)
  const isEmpty = !isCurrentlyLoading && (!filteredTemplates || filteredTemplates.length === 0) && !searchQuery.trim()
  const isSearchEmpty = !isCurrentlyLoading && (!filteredTemplates || filteredTemplates.length === 0) && searchQuery.trim() !== ''
  const selectedCount = selectedTemplateIds.length
  const selectedTemplates = (userTemplates || []).filter(template => selectedTemplateIds.includes(template.id))
  const selectedEnableEligibleIds = selectedTemplates.filter(template => template.is_disabled).map(template => template.id)
  const selectedDisableEligibleIds = selectedTemplates.filter(template => !template.is_disabled).map(template => template.id)
  const enableEligibleCount = selectedEnableEligibleIds.length
  const disableEligibleCount = selectedDisableEligibleIds.length
  const bulkActions: BulkActionItem[] = selectedCount
    ? [
        {
          key: 'delete',
          label: t('delete'),
          icon: Trash2,
          onClick: () => setBulkAction('delete'),
          direct: true,
          destructive: true,
        },
        {
          key: 'enable',
          label: t('enable'),
          icon: Power,
          onClick: () => setBulkAction('enable'),
        },
        {
          key: 'disable',
          label: t('disable'),
          icon: PowerOff,
          onClick: () => setBulkAction('disable'),
        },
      ]
    : []
  const bulkActionConfigs: Record<BulkUserTemplateActionType, BulkActionDialogConfig> = {
    delete: {
      title: t('templates.bulkDeleteTitle', { defaultValue: 'Delete Selected User Templates' }),
      description: t('templates.bulkDeletePrompt', {
        count: selectedCount,
        defaultValue: 'Are you sure you want to delete {{count}} selected user templates? This action cannot be undone.',
      }),
      actionLabel: t('delete'),
      onConfirm: handleBulkDelete,
      isPending: bulkDeleteUserTemplatesMutation.isPending,
      destructive: true,
    },
    enable: {
      title: t('templates.bulkEnableTitle', { defaultValue: 'Enable Selected User Templates' }),
      description: t('templates.bulkEnablePrompt', {
        count: enableEligibleCount,
        defaultValue: 'Are you sure you want to enable {{count}} selected user templates?',
      }),
      actionLabel: t('enable'),
      onConfirm: handleBulkEnable,
      isPending: bulkEnableUserTemplatesMutation.isPending,
    },
    disable: {
      title: t('templates.bulkDisableTitle', { defaultValue: 'Disable Selected User Templates' }),
      description: t('templates.bulkDisablePrompt', {
        count: disableEligibleCount,
        defaultValue: 'Are you sure you want to disable {{count}} selected user templates?',
      }),
      actionLabel: t('disable'),
      onConfirm: handleBulkDisable,
      isPending: bulkDisableUserTemplatesMutation.isPending,
    },
  }
  const activeBulkActionConfig = bulkAction ? bulkActionConfigs[bulkAction] : null

  return (
    <div className="flex w-full flex-col items-start gap-2">
      <div className="w-full flex-1 space-y-4 px-4">
        <div dir={dir} className="flex items-center gap-2 pt-4 md:gap-4">
          <div className="relative min-w-0 flex-1 md:w-[calc(100%/3-10px)] md:flex-none">
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
              onClick={() => refetch()}
              className={cn('h-9 w-9 rounded-lg border', isFetching && 'opacity-70')}
              aria-label={t('autoRefresh.refreshNow')}
              title={t('autoRefresh.refreshNow')}
            >
              <RefreshCw className={cn('h-4 w-4', isFetching && 'animate-spin')} />
            </Button>
            <ViewToggle value={viewMode} onChange={setViewMode} />
          </div>
        </div>
        <BulkActionsBar selectedCount={selectedCount} onClear={clearSelection} actions={bulkActions} />

        {(isCurrentlyLoading || (filteredTemplates && filteredTemplates.length > 0)) && (
          <ListGenerator
            data={filteredTemplates || []}
            columns={listColumns}
            getRowId={template => template.id}
            isLoading={isCurrentlyLoading}
            loadingRows={6}
            className="gap-3"
            onRowClick={handleEdit}
            mode={viewMode}
            enableSelection
            enableGridSelection
            selectedRowIds={selectedTemplateIds}
            onSelectionChange={ids => setSelectedTemplateIds(ids.map(id => Number(id)))}
            showEmptyState={false}
            gridClassName="transform-gpu animate-slide-up"
            gridStyle={{ animationDuration: '500ms', animationDelay: '100ms', animationFillMode: 'both' }}
            renderGridItem={template => <UserTemplate onEdit={handleEdit} template={template} onToggleStatus={handleToggleStatus} />}
            renderGridSkeleton={i => (
              <Card key={i} className="px-4 py-5 sm:px-5 sm:py-6">
                <div className="flex items-start justify-between gap-2 sm:gap-3">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-x-2">
                      <Skeleton className="h-2 w-2 shrink-0 rounded-full" />
                      <Skeleton className="h-5 w-24 sm:w-32" />
                    </div>
                    <div className="space-y-2">
                      <Skeleton className="h-4 w-32 sm:w-40 md:w-48" />
                      <Skeleton className="h-4 w-28 sm:w-36 md:w-40" />
                    </div>
                  </div>
                  <Skeleton className="h-8 w-8 shrink-0" />
                </div>
              </Card>
            )}
          />
        )}
        {isEmpty && !isCurrentlyLoading && (
          <Card className="mb-12">
            <CardContent className="p-8 text-center">
              <div className="space-y-4">
                <h3 className="text-lg font-semibold">{t('templates.noTemplates')}</h3>
                <p className="mx-auto max-w-2xl text-muted-foreground">{t('templates.noTemplatesDescription')}</p>
              </div>
            </CardContent>
          </Card>
        )}
        {isSearchEmpty && !isCurrentlyLoading && (
          <Card className="mb-12">
            <CardContent className="p-8 text-center">
              <div className="space-y-4">
                <h3 className="text-lg font-semibold">{t('noResults')}</h3>
                <p className="mx-auto max-w-2xl text-muted-foreground">{t('templates.noSearchResults')}</p>
              </div>
            </CardContent>
          </Card>
        )}
      </div>

      <UserTemplateModal
        isDialogOpen={isDialogOpen}
        onOpenChange={open => {
          if (!open) {
            setEditingUserTemplate(null)
            form.reset(userTemplateFormDefaultValues)
          }
          setIsDialogOpen(open)
        }}
        form={form}
        editingUserTemplate={!!editingUserTemplate}
        editingUserTemplateId={editingUserTemplate?.id}
      />
      {activeBulkActionConfig && (
        <BulkActionAlertDialog
          open={!!bulkAction}
          onOpenChange={open => setBulkAction(open ? bulkAction : null)}
          title={activeBulkActionConfig.title}
          description={activeBulkActionConfig.description}
          actionLabel={activeBulkActionConfig.actionLabel}
          onConfirm={activeBulkActionConfig.onConfirm}
          isPending={activeBulkActionConfig.isPending}
          destructive={activeBulkActionConfig.destructive}
        />
      )}
    </div>
  )
}
