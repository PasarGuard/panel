import { useGetAllCores, useModifyCoreConfig } from '@/service/api'
import { CoreResponse } from '@/service/api'
import Core from './core'
import { useState, useEffect, useMemo } from 'react'
import CoreConfigModal from '@/components/dialogs/core-config-modal'
import { coreConfigFormSchema, type CoreConfigFormValues } from '@/components/forms/core-config-form'
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

const initialDefaultValues: Partial<CoreConfigFormValues> = {
  name: '',
  config: JSON.stringify({}, null, 2),
  excluded_inbound_ids: [],
  restart_nodes: true,
}

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
  const { t } = useTranslation()
  const modifyCoreMutation = useModifyCoreConfig()
  const dir = useDirDetection()

  const { data: coresData, isLoading, isFetching, refetch } = useGetAllCores({})

  useEffect(() => {
    const handleOpenDialog = () => onOpenChange?.(true)
    window.addEventListener('openCoreDialog', handleOpenDialog)
    return () => window.removeEventListener('openCoreDialog', handleOpenDialog)
  }, [onOpenChange])

  const form = useForm<CoreConfigFormValues>({
    resolver: zodResolver(coreConfigFormSchema),
    defaultValues: initialDefaultValues,
  })

  const handleEdit = (core: CoreResponse) => {
    setEditingCore(core)
    form.reset({
      name: core.name,
      config: JSON.stringify(core.config, null, 2),
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
      form.reset(initialDefaultValues)
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

  return (
    <div className={cn('flex w-full flex-col gap-4 pt-4', dir === 'rtl' && 'rtl')}>
      <div className="flex items-center gap-2 md:gap-3">
        {/* Search Input */}
        <div className="relative w-full md:w-[calc(100%/3-10px)]" dir={dir}>
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
          onClick={handleRefreshClick}
          className={cn('border', isFetching && 'opacity-70')}
          aria-label={t('autoRefresh.refreshNow')}
          title={t('autoRefresh.refreshNow')}
        >
          <RefreshCw className={cn('h-4 w-4', isFetching && 'animate-spin')} />
        </Button>
      </div>
      <ScrollArea dir={dir} className="h-[calc(100vh-8rem)]">
        <div className="grid w-full grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
          {isLoading
            ? [...Array(6)].map((_, i) => (
                <Card key={i} className="px-4 py-5">
                  <div className="flex items-center gap-2 sm:gap-3">
                    <Skeleton className="h-2 w-2 shrink-0 rounded-full" />
                    <Skeleton className="h-5 w-24 sm:w-32" />
                    <div className="ml-auto shrink-0">
                      <Skeleton className="h-8 w-8" />
                    </div>
                  </div>
                </Card>
              ))
            : filteredCores.map((core: CoreResponse) => (
                <Core
                  key={core.id}
                  core={core}
                  onEdit={onEditCore ? () => onEditCore(core.id) : () => handleEdit(core)}
                  onToggleStatus={handleToggleStatus}
                  onDuplicate={onDuplicateCore ? () => onDuplicateCore(core.id) : undefined}
                  onDelete={onDeleteCore ? () => onDeleteCore(core.name, core.id) : undefined}
                />
              ))}
        </div>
      </ScrollArea>

      <CoreConfigModal isDialogOpen={!!isDialogOpen} onOpenChange={handleModalClose} form={form} editingCore={!!editingCore} editingCoreId={editingCore?.id} />
    </div>
  )
}

