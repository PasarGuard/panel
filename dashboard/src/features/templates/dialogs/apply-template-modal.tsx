import { useState, useEffect } from 'react'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Loader2, Layers } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useBulkApplyTemplateToUsers } from '@/service/api'
import { toast } from 'sonner'
import useDynamicErrorHandler from '@/hooks/use-dynamic-errors'

interface ApplyTemplateModalProps {
  open: boolean
  onClose: () => void
  userIds: number[]
  selectedCount: number
  onSuccess?: () => void
}

export default function ApplyTemplateModal({ open, onClose, userIds, selectedCount, onSuccess }: ApplyTemplateModalProps) {
  const { t } = useTranslation()
  const [selectedTemplateId, setSelectedTemplateId] = useState<number | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [templates, setTemplates] = useState<any[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [isError, setIsError] = useState(false)
  const bulkApplyTemplateMutation = useBulkApplyTemplateToUsers()
  const handleDynamicError = useDynamicErrorHandler()

  useEffect(() => {
    if (open) {
      fetchTemplates()
    } else {
      setTemplates([])
      setIsLoading(false)
      setIsError(false)
      setSelectedTemplateId(null)
    }
  }, [open])

  const fetchTemplates = async () => {
    setIsLoading(true)
    setIsError(false)
    try {
      const api = await import('@/service/api')
      const templatesResponse = await api.getUserTemplates()
      setTemplates(templatesResponse || [])
      setIsLoading(false)
    } catch (error) {
      setIsError(true)
      setIsLoading(false)
    }
  }

  const handleSubmit = async () => {
    if (!selectedTemplateId) return
    setSubmitting(true)
    try {
      await bulkApplyTemplateMutation.mutateAsync({
        data: {
          ids: userIds,
          user_template_id: selectedTemplateId,
        },
      })
      toast.success(t('bulk.applyTemplateSuccess', { count: selectedCount }))
      onSuccess?.()
      onClose()
    } catch (error: any) {
      handleDynamicError({
        error,
        fields: ['user_template_id'],
        form: { setError: () => {}, clearErrors: () => {} },
        contextKey: 'bulk',
      })
    } finally {
      setSubmitting(false)
    }
  }

  const selectedTemplate = templates.find(t => t.id === selectedTemplateId)

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="w-full max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Layers className="h-5 w-5" />
            <span>{t('bulk.applyTemplateTitle')}</span>
          </DialogTitle>
        </DialogHeader>
        <div className="mt-2 flex flex-col gap-4">
          <div>
            <div className="mb-3 text-sm text-muted-foreground">
              {t('bulk.applyTemplateDesc')}
            </div>
            <div className="mb-3 text-sm text-muted-foreground">
              {t('bulk.applyTemplatePrompt', {
                templateName: selectedTemplate?.name || t('bulk.noTemplateSelected'),
                count: selectedCount,
              })}
            </div>
            {isLoading ? (
              <div className="flex items-center justify-center p-2">
                <Loader2 className="animate-spin" />
              </div>
            ) : isError ? (
              <div className="p-2 text-destructive">{t('bulk.applyTemplateError')}</div>
            ) : templates.length > 0 ? (
              <Select value={selectedTemplateId?.toString() ?? ''} onValueChange={(value) => setSelectedTemplateId(Number(value))}>
                <SelectTrigger className="w-full">
                  <SelectValue placeholder={t('bulk.selectTemplatePlaceholder')} />
                </SelectTrigger>
                <SelectContent>
                  {templates.filter(t => !t.is_disabled).map((template: any) => (
                    <SelectItem key={template.id} value={template.id.toString()}>
                      {template.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            ) : (
              <div className="p-2 text-sm text-muted-foreground">{t('bulk.noTemplates')}</div>
            )}
          </div>
          <div className="mt-4 flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={onClose} disabled={submitting}>
              {t('cancel')}
            </Button>
            <Button type="button" onClick={handleSubmit} disabled={!selectedTemplateId || submitting}>
              {submitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              {submitting ? t('applying') : t('bulk.applyTemplate')}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}