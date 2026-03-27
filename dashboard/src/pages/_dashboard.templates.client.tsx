import ClientTemplate from '@/components/templates/client-template'
import { useGetClientTemplates, ClientTemplateResponse } from '@/service/api'
import { Skeleton } from '@/components/ui/skeleton'
import { Card, CardContent } from '@/components/ui/card'
import ClientTemplateModal from '@/components/dialogs/client-template-modal'
import { clientTemplateFormDefaultValues, clientTemplateFormSchema, type ClientTemplateFormValues } from '@/components/forms/client-template-form'
import { useState, useMemo, useEffect } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { useTranslation } from 'react-i18next'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { RefreshCw, Search, X } from 'lucide-react'
import useDirDetection from '@/hooks/use-dir-detection'
import { cn } from '@/lib/utils'
import ViewToggle from '@/components/common/view-toggle'
import { ListGenerator } from '@/components/common/list-generator'
import { useClientTemplatesListColumns } from '@/components/templates/use-client-templates-list-columns'
import { usePersistedViewMode } from '@/hooks/use-persisted-view-mode'

export default function ClientTemplates() {
  const [isDialogOpen, setIsDialogOpen] = useState(false)
  const [editingTemplate, setEditingTemplate] = useState<ClientTemplateResponse | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [viewMode, setViewMode] = usePersistedViewMode('view-mode:client-templates')
  const { data, isLoading, isFetching, refetch } = useGetClientTemplates()
  const form = useForm<ClientTemplateFormValues>({
    resolver: zodResolver(clientTemplateFormSchema),
    defaultValues: clientTemplateFormDefaultValues as ClientTemplateFormValues,
  })
  const { t } = useTranslation()
  const dir = useDirDetection()

  useEffect(() => {
    const handleOpenDialog = () => {
      setEditingTemplate(null)
      form.reset(clientTemplateFormDefaultValues as ClientTemplateFormValues)
      setIsDialogOpen(true)
    }
    window.addEventListener('openClientTemplateDialog', handleOpenDialog)
    return () => window.removeEventListener('openClientTemplateDialog', handleOpenDialog)
  }, [form])

  const handleEdit = (template: ClientTemplateResponse) => {
    setEditingTemplate(template)
    form.reset({
      name: template.name,
      template_type: template.template_type,
      content: template.content,
      is_default: template.is_default,
    })
    setIsDialogOpen(true)
  }

  const filteredTemplates = useMemo(() => {
    const templates = data?.templates || []
    if (!searchQuery.trim()) return templates
    const query = searchQuery.toLowerCase().trim()
    return templates.filter((t: ClientTemplateResponse) => t.name?.toLowerCase().includes(query) || t.template_type?.toLowerCase().includes(query))
  }, [data, searchQuery])

  const listColumns = useClientTemplatesListColumns({ onEdit: handleEdit })

  const isCurrentlyLoading = isLoading || (isFetching && !data)
  const isEmpty = !isCurrentlyLoading && filteredTemplates.length === 0 && !searchQuery.trim()
  const isSearchEmpty = !isCurrentlyLoading && filteredTemplates.length === 0 && searchQuery.trim() !== ''

  return (
    <div className="flex w-full flex-col items-start gap-2">
      <div className="w-full flex-1 space-y-4 px-4">
        <div dir={dir} className="flex items-center gap-2 pt-4 md:gap-4">
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

        {(isCurrentlyLoading || filteredTemplates.length > 0) && (
          <ListGenerator
            data={filteredTemplates}
            columns={listColumns}
            getRowId={template => template.id}
            isLoading={isCurrentlyLoading}
            loadingRows={6}
            className="gap-3"
            onRowClick={handleEdit}
            mode={viewMode}
            showEmptyState={false}
            gridClassName="transform-gpu animate-slide-up"
            gridStyle={{ animationDuration: '500ms', animationDelay: '100ms', animationFillMode: 'both' }}
            renderGridItem={template => <ClientTemplate onEdit={handleEdit} template={template} />}
            renderGridSkeleton={i => (
              <Card key={i} className="px-4 py-5 sm:px-5 sm:py-6">
                <div className="flex items-start justify-between gap-2 sm:gap-3">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-x-2">
                      <Skeleton className="h-5 w-24 sm:w-32" />
                    </div>
                    <div className="mt-2">
                      <Skeleton className="h-4 w-16" />
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
                <h3 className="text-lg font-semibold">{t('clientTemplates.noTemplates', { defaultValue: 'No client templates' })}</h3>
                <p className="mx-auto max-w-2xl text-muted-foreground">
                  {t('clientTemplates.noTemplatesDescription', { defaultValue: 'Create a client template to customize subscription output formats.' })}
                </p>
              </div>
            </CardContent>
          </Card>
        )}

        {isSearchEmpty && !isCurrentlyLoading && (
          <Card className="mb-12">
            <CardContent className="p-8 text-center">
              <div className="space-y-4">
                <h3 className="text-lg font-semibold">{t('noResults')}</h3>
                <p className="mx-auto max-w-2xl text-muted-foreground">{t('clientTemplates.noSearchResults', { defaultValue: 'No client templates match your search.' })}</p>
              </div>
            </CardContent>
          </Card>
        )}
      </div>

      <ClientTemplateModal
        isDialogOpen={isDialogOpen}
        onOpenChange={open => {
          if (!open) {
            setEditingTemplate(null)
            form.reset(clientTemplateFormDefaultValues as ClientTemplateFormValues)
          }
          setIsDialogOpen(open)
        }}
        form={form}
        editingTemplate={!!editingTemplate}
        editingTemplateId={editingTemplate?.id}
      />
    </div>
  )
}
