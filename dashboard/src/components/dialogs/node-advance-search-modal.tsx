import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog.tsx'
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/form.tsx'
import { Button } from '@/components/ui/button.tsx'
import { LoaderButton } from '@/components/ui/loader-button.tsx'
import useDirDetection from '@/hooks/use-dir-detection'
import { UseFormReturn } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { z } from 'zod'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select.tsx'
import { Badge } from '@/components/ui/badge.tsx'
import { X } from 'lucide-react'
import { NodeStatus } from '@/service/api'
import { Checkbox } from '@/components/ui/checkbox.tsx'
import CoresSelector from '@/components/common/cores-selector.tsx'

interface NodeAdvanceSearchModalProps {
  isDialogOpen: boolean
  onOpenChange: (open: boolean) => void
  form: UseFormReturn<NodeAdvanceSearchFormValue>
  onSubmit: (values: NodeAdvanceSearchFormValue) => void
}

export const nodeAdvanceSearchFormSchema = z.object({
  status: z.array(z.nativeEnum(NodeStatus)).optional(),
  core_id: z.number().nullable().optional()
})

export type NodeAdvanceSearchFormValue = z.infer<typeof nodeAdvanceSearchFormSchema>

const statusOptions = [
  { value: NodeStatus.connected, label: 'nodeModal.status.connected' },
  { value: NodeStatus.disabled, label: 'nodeModal.status.disabled' },
  { value: NodeStatus.error, label: 'nodeModal.status.error' },
  { value: NodeStatus.limited, label: 'status.limited' },
  { value: NodeStatus.connecting, label: 'nodeModal.status.connecting' },
] as const

export default function NodeAdvanceSearchModal({ isDialogOpen, onOpenChange, form, onSubmit }: NodeAdvanceSearchModalProps) {
  const dir = useDirDetection()
  const { t } = useTranslation()

  return (
    <Dialog open={isDialogOpen} onOpenChange={onOpenChange}>
      <DialogContent className="flex h-full max-w-[650px] flex-col justify-start sm:h-auto" onOpenAutoFocus={e => e.preventDefault()}>
        <DialogHeader>
          <DialogTitle className={`${dir === 'rtl' ? 'text-right' : 'text-left'}`} dir={dir}>
            {t('advanceSearch.title')}
          </DialogTitle>
        </DialogHeader>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="flex h-full flex-col justify-between space-y-4">
            <div className="-mr-4 max-h-[80dvh] overflow-y-auto px-2 pr-4 sm:max-h-[75dvh]">
              <div className="flex w-full flex-1 flex-col items-start gap-4 pb-4">
                <FormField
                  control={form.control}
                  name="status"
                  render={({ field }) => {
                    return (
                      <FormItem className="w-full flex-1">
                        <FormLabel>{t('advanceSearch.byStatus')}</FormLabel>
                        <FormControl>
                          <>
                            {/* Display selected statuses as badges */}
                            {field.value && field.value.length > 0 && (
                              <div className="flex flex-wrap gap-2 mb-2">
                                {field.value.map(status => {
                                  const option = statusOptions.find(opt => opt.value === status)
                                  if (!option) return null
                                  return (
                                    <Badge key={status} variant="secondary" className="flex items-center gap-1">
                                      {t(option.label)}
                                      <X
                                        className="h-3 w-3 cursor-pointer"
                                        onClick={() => {
                                          field.onChange(field.value?.filter(s => s !== status))
                                        }}
                                      />
                                    </Badge>
                                  )
                                })}
                              </div>
                            )}
                            
                            {/* Status selector with checkboxes */}
                            <Select
                              value=""
                              onValueChange={(value: NodeStatus) => {
                                if (!value) return
                                const currentValue = field.value || []
                                if (!currentValue.includes(value)) {
                                  field.onChange([...currentValue, value])
                                }
                              }}
                            >
                              <SelectTrigger dir={dir} className="w-full gap-2 py-2">
                                <SelectValue placeholder={t('hostsDialog.selectStatus')} />
                              </SelectTrigger>
                              <SelectContent dir={dir} className="bg-background">
                                {statusOptions.map(option => (
                                  <SelectItem
                                    key={option.value}
                                    value={option.value}
                                    className="flex cursor-pointer items-center gap-2 px-4 py-2 focus:bg-accent"
                                    disabled={field.value?.includes(option.value)}
                                  >
                                    <div className="flex w-full items-center gap-3">
                                      <Checkbox checked={field.value?.includes(option.value)} className="h-4 w-4" />
                                      <span className="text-sm font-normal">{t(option.label)}</span>
                                    </div>
                                  </SelectItem>
                                ))}
                              </SelectContent>
                            </Select>
                            
                            {/* Clear all button */}
                            {field.value && field.value.length > 0 && (
                              <Button
                                type="button"
                                variant="outline"
                                size="sm"
                                onClick={() => field.onChange([])}
                                className="mt-2 w-full"
                              >
                                {t('hostsDialog.clearAllStatuses')}
                              </Button>
                            )}
                          </>
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )
                  }}
                />
                
                <FormField
                  control={form.control}
                  name="core_id"
                  render={({ field }) => {
                    return (
                      <FormItem className="w-full flex-1">
                        <FormLabel>{t('advanceSearch.byCore', { defaultValue: 'Core' })}</FormLabel>
                        <FormControl>
                          <CoresSelector
                            control={form.control}
                            name="core_id"
                            onCoreChange={field.onChange}
                            placeholder={t('advanceSearch.searchCore', { defaultValue: 'Search cores...' })}
                          />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )
                  }}
                />
              </div>
            </div>
            <div className="flex justify-end gap-2">
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                {t('cancel')}
              </Button>
              <LoaderButton type="submit">
                {t('apply')}
              </LoaderButton>
            </div>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  )
}
