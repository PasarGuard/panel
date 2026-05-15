import { isValidIconUrl, languageOptions, platformOptions, PlatformIcon } from '@/features/subscriptions/components/subscription-application-shared'
import {
  subscriptionApplicationSchema,
  type SubscriptionApplicationFormData,
  type SubscriptionFormData,
} from '@/features/subscriptions/components/subscription-settings-schema'
import { Button } from '@/components/ui/button'
import { Form, FormControl, FormDescription, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/form'
import { Input } from '@/components/ui/input'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Sheet, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { Switch } from '@/components/ui/switch'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Textarea } from '@/components/ui/textarea'
import useDirDetection from '@/hooks/use-dir-detection'
import { useIsMobile } from '@/hooks/use-mobile'
import { cn } from '@/lib/utils'
import { zodResolver } from '@hookform/resolvers/zod'
import { Info, Pencil, Plus, RotateCcw, Trash2 } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import {
  useFieldArray,
  useForm,
  useFormContext,
  useFormState,
  useWatch,
  type Control,
  type FieldArrayPath,
  type FieldErrors,
  type FieldPath,
  type UseFormReturn,
} from 'react-hook-form'
import { useTranslation } from 'react-i18next'

function IconUrlInfoPopover() {
  const { t } = useTranslation()
  const dir = useDirDetection()
  const isMobile = useIsMobile()
  const infoPopoverSide = isMobile ? 'bottom' : dir === 'rtl' ? 'left' : 'right'
  const infoPopoverAlign = isMobile ? 'center' : 'start'
  const description = t('settings.subscriptions.applications.iconUrlDescription', { defaultValue: 'Optional. Shown next to app name.' })

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button type="button" variant="ghost" size="icon" className="h-auto w-auto p-0 hover:bg-transparent" aria-label={description}>
          <Info className="h-3.5 w-3.5 text-muted-foreground" />
        </Button>
      </PopoverTrigger>
      <PopoverContent
        className="w-[280px] p-3 text-xs leading-relaxed text-muted-foreground sm:w-[320px]"
        side={infoPopoverSide}
        align={infoPopoverAlign}
        sideOffset={5}
      >
        {description}
      </PopoverContent>
    </Popover>
  )
}

const emptyApplicationDefaults: SubscriptionApplicationFormData = {
  name: '',
  icon_url: '',
  import_url: '',
  description: { fa: '', en: '', ru: '', zh: '' },
  recommended: false,
  platform: 'android',
  download_links: [{ name: '', url: '', language: 'en' }],
}

function cloneApplication(app: SubscriptionApplicationFormData): SubscriptionApplicationFormData {
  return {
    ...app,
    description: { ...(app.description || {}) },
    download_links: (app.download_links || []).map(link => ({ ...link })),
  }
}

export type SubscriptionApplicationSheetProps =
  | {
    variant: 'create'
    open: boolean
    onOpenChange: (open: boolean) => void
    onConfirm: (app: SubscriptionApplicationFormData) => void
    isSaving: boolean
  }
  | {
    variant: 'edit'
    form: UseFormReturn<SubscriptionFormData>
    applicationIndex: number
    rowId: string
    open: boolean
    onOpenChange: (open: boolean) => void
  }

export function SubscriptionApplicationSheet(props: SubscriptionApplicationSheetProps) {
  if (props.variant === 'create') {
    return <SubscriptionApplicationSheetCreate {...props} />
  }
  return <SubscriptionApplicationSheetEdit {...props} />
}

/** @deprecated Use `<SubscriptionApplicationSheet variant="create" ... />` */
export function SubscriptionAddApplicationDialog(
  props: Pick<Extract<SubscriptionApplicationSheetProps, { variant: 'create' }>, 'open' | 'onOpenChange' | 'onConfirm' | 'isSaving'>,
) {
  return <SubscriptionApplicationSheet variant="create" {...props} />
}

function SubscriptionApplicationSheetCreate({
  open,
  onOpenChange,
  onConfirm,
  isSaving,
}: Extract<SubscriptionApplicationSheetProps, { variant: 'create' }>) {
  const { t } = useTranslation()
  const isRtl = useDirDetection() === 'rtl'
  const [iconBroken, setIconBroken] = useState(false)

  const form = useForm<SubscriptionApplicationFormData>({
    resolver: zodResolver(subscriptionApplicationSchema),
    defaultValues: emptyApplicationDefaults,
    mode: 'onSubmit',
  })

  const iconUrlWatch = form.watch('icon_url')
  useEffect(() => {
    setIconBroken(false)
  }, [iconUrlWatch])

  useEffect(() => {
    if (open) {
      form.reset(emptyApplicationDefaults)
    }
  }, [open, form])

  const onSubmit = (data: SubscriptionApplicationFormData) => {
    onConfirm(data)
  }

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side={isRtl ? 'left' : 'right'}
        className={cn('flex h-full max-h-screen w-full flex-col gap-0 overflow-hidden p-0 sm:max-w-lg')}
        onOpenAutoFocus={e => e.preventDefault()}
      >
        <Form {...form}>
          <form
            id="subscription-create-application-form"
            className="flex min-h-0 flex-1 flex-col gap-0 overflow-hidden"
            onSubmit={form.handleSubmit(onSubmit)}
          >
            <SheetHeader className="flex flex-col flex-shrink-0 space-y-1 border-b px-6 pb-4 pt-6 pe-14 text-start">
              <SheetTitle className="flex items-center gap-2">
                <Plus className="h-5 w-5" />
                <span>{t('settings.subscriptions.applications.addApplication')}</span>
              </SheetTitle>
              <SheetDescription>{t('settings.subscriptions.applications.addSheetDescription')}</SheetDescription>
            </SheetHeader>

            <div className="flex min-h-0 flex-1 flex-col gap-6 overflow-y-auto px-6 py-4">
              <ApplicationFieldsGridCreate
                iconBroken={iconBroken}
                setIconBroken={setIconBroken}
              />
              <DownloadLinksSection variant="create" linksFieldName="download_links" rowIdPrefix="create" />
            </div>

            <SheetFooter className="flex-shrink-0 flex-col gap-2 border-t px-6 py-4 sm:flex-row sm:justify-end">
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={isSaving} className="w-full sm:w-auto">
                {t('cancel')}
              </Button>
              <Button type="submit" form="subscription-create-application-form" disabled={isSaving} className="w-full sm:w-auto">
                {t('create')}
              </Button>
            </SheetFooter>
          </form>
        </Form>
      </SheetContent>
    </Sheet>
  )
}

function SubscriptionApplicationSheetEdit({
  form,
  applicationIndex,
  rowId,
  open,
  onOpenChange,
}: Extract<SubscriptionApplicationSheetProps, { variant: 'edit' }>) {
  const { t } = useTranslation()
  const isRtl = useDirDetection() === 'rtl'
  const [iconBroken, setIconBroken] = useState(false)
  const initialApplicationRef = useRef<SubscriptionApplicationFormData | null>(null)
  const [canUndo, setCanUndo] = useState(false)
  const [restoredLinks, setRestoredLinks] = useState<SubscriptionApplicationFormData['download_links'] | null>(null)
  const [restoreLinksVersion, setRestoreLinksVersion] = useState(0)
  const iconUrlWatch = form.watch(`applications.${applicationIndex}.icon_url`)

  useEffect(() => {
    setIconBroken(false)
  }, [iconUrlWatch])

  useEffect(() => {
    if (open) {
      const currentApplication = form.getValues(`applications.${applicationIndex}`) as SubscriptionApplicationFormData | undefined
      initialApplicationRef.current = currentApplication ? cloneApplication(currentApplication) : null
      setCanUndo(Boolean(currentApplication))
    }
  }, [open, form, applicationIndex])

  const undoChanges = () => {
    if (!initialApplicationRef.current) return
    const restoredApplication = cloneApplication(initialApplicationRef.current)
    const setOptions = { shouldDirty: true, shouldTouch: false, shouldValidate: false }

    form.setValue(`applications.${applicationIndex}.name`, restoredApplication.name, setOptions)
    form.setValue(`applications.${applicationIndex}.icon_url`, restoredApplication.icon_url, setOptions)
    form.setValue(`applications.${applicationIndex}.import_url`, restoredApplication.import_url, setOptions)
    form.setValue(`applications.${applicationIndex}.description`, restoredApplication.description, setOptions)
    form.setValue(`applications.${applicationIndex}.recommended`, restoredApplication.recommended, setOptions)
    form.setValue(`applications.${applicationIndex}.platform`, restoredApplication.platform, setOptions)
    setRestoredLinks(restoredApplication.download_links)
    setRestoreLinksVersion(version => version + 1)
    setIconBroken(false)
    void form.trigger(`applications.${applicationIndex}`)
  }

  const linksFieldName = `applications.${applicationIndex}.download_links` as FieldPath<SubscriptionFormData>

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side={isRtl ? 'left' : 'right'}
        className={cn('flex h-full max-h-screen w-full flex-col gap-0 overflow-hidden p-0 sm:max-w-lg')}
        onOpenAutoFocus={e => e.preventDefault()}
      >
        <SheetHeader className="flex flex-col flex-shrink-0 space-y-1 border-b px-6 pb-4 pt-6 pe-14 text-start">
          <SheetTitle className="flex items-center gap-2">
            <Pencil className="h-5 w-5" />
            <span>{t('settings.subscriptions.applications.editApplication', { defaultValue: 'Edit application' })}</span>
          </SheetTitle>
          <SheetDescription>{t('settings.subscriptions.applications.sheetDescription')}</SheetDescription>
        </SheetHeader>

        <div className="flex min-h-0 flex-1 flex-col gap-6 overflow-y-auto px-6 py-4">
          <ApplicationFieldsGridEdit
            form={form}
            applicationIndex={applicationIndex}
            iconBroken={iconBroken}
            setIconBroken={setIconBroken}
          />
          <DownloadLinksSection
            variant="edit"
            linksFieldName={linksFieldName}
            rowIdPrefix={rowId}
            applicationIndex={applicationIndex}
            restoredLinks={restoredLinks}
            restoreLinksVersion={restoreLinksVersion}
          />
        </div>

        <SheetFooter className="flex-shrink-0 flex-col gap-2 border-t px-6 py-4 sm:flex-row sm:justify-end">
          <Button type="button" variant="outline" className="w-full sm:w-auto" onClick={undoChanges} disabled={!canUndo}>
            <RotateCcw className="me-2 h-4 w-4" />
            {t('settings.subscriptions.applications.undo', { defaultValue: 'Undo' })}
          </Button>
          <Button type="button" variant="outline" className="w-full sm:w-auto" onClick={() => onOpenChange(false)}>
            {t('close', { defaultValue: 'Close' })}
          </Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  )
}

function ApplicationFieldsGridCreate({
  iconBroken,
  setIconBroken,
}: {
  iconBroken: boolean
  setIconBroken: (v: boolean) => void
}) {
  const { t } = useTranslation()
  const isRtl = useDirDetection() === 'rtl'
  const [selectedLanguage, setSelectedLanguage] = useState('en')
  const { control } = useFormContext<SubscriptionApplicationFormData>()
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
      <FormField
        control={control}
        name="name"
        render={({ field }) => (
          <FormItem className="space-y-1">
            <FormLabel className="text-xs text-muted-foreground/80">{t('settings.subscriptions.applications.name')}</FormLabel>
            <FormControl>
              <Input placeholder={t('settings.subscriptions.applications.namePlaceholder')} {...field} className="h-8 text-xs" />
            </FormControl>
            <FormMessage />
          </FormItem>
        )}
      />

      <FormField
        control={control}
        name="icon_url"
        render={({ field }) => (
          <FormItem className="space-y-1">
            <div className="flex items-center gap-1.5">
              <FormLabel className="text-xs text-muted-foreground/80">{t('settings.subscriptions.applications.iconUrl', { defaultValue: 'Icon URL' })}</FormLabel>
              <IconUrlInfoPopover />
            </div>
            <FormControl>
              <div className="flex items-center gap-2">
                <Input
                  placeholder={t('settings.subscriptions.applications.iconUrlPlaceholder', { defaultValue: 'https://...' })}
                  {...field}
                  className="h-8 min-w-0 flex-1 font-mono text-xs"
                  dir="ltr"
                />
                {field.value && !iconBroken && isValidIconUrl(String(field.value)) ? (
                  <img src={String(field.value)} alt="" className="h-8 w-8 shrink-0 rounded-sm object-cover" onError={() => setIconBroken(true)} />
                ) : (
                  <div className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-sm bg-muted text-muted-foreground/80">
                    <span className="text-[10px]">🖼️</span>
                  </div>
                )}
              </div>
            </FormControl>
            <FormMessage />
          </FormItem>
        )}
      />

      <FormField
        control={control}
        name="platform"
        render={({ field }) => (
          <FormItem className="space-y-1 sm:col-span-2">
            <FormLabel className="text-xs text-muted-foreground/80">{t('settings.subscriptions.applications.platform')}</FormLabel>
            <Select onValueChange={field.onChange} value={field.value}>
              <FormControl>
                <SelectTrigger className="h-8 w-full text-xs">
                  <SelectValue />
                </SelectTrigger>
              </FormControl>
              <SelectContent className="scrollbar-thin z-[60]">
                {platformOptions.map(option => (
                  <SelectItem key={option.value} value={option.value}>
                    <div className="flex items-center gap-1.5">
                      <PlatformIcon platform={option.value} />
                      <span className="text-xs">{t(option.label)}</span>
                    </div>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <FormMessage />
          </FormItem>
        )}
      />

      <FormField
        control={control}
        name="import_url"
        render={({ field }) => (
          <FormItem className="space-y-1 sm:col-span-2">
            <FormLabel className="text-xs text-muted-foreground/80">{t('settings.subscriptions.applications.importUrl')}</FormLabel>
            <FormControl>
              <Input placeholder={t('settings.subscriptions.applications.importUrlPlaceholder')} {...field} className="h-8 font-mono text-xs" dir="ltr" />
            </FormControl>
            <FormDescription className="text-xs text-muted-foreground">{t('settings.subscriptions.applications.importUrlDescription')}</FormDescription>
            <FormMessage />
          </FormItem>
        )}
      />

      <FormField
        control={control}
        name="description"
        render={({ field }) => (
          <FormItem className="space-y-1 sm:col-span-2">
            <FormLabel className="text-xs text-muted-foreground/80">{t('settings.subscriptions.applications.descriptionApp')}</FormLabel>
            <FormControl>
              <div className="flex flex-col gap-2">
                <Tabs value={selectedLanguage} onValueChange={setSelectedLanguage} className="w-full">
                  <TabsList className="flex h-auto w-full flex-wrap gap-1 overflow-x-auto px-1 sm:w-fit sm:flex-nowrap sm:gap-4">
                    {languageOptions.map(option => (
                      <TabsTrigger key={option.value} className="flex-1 px-1 text-xs sm:flex-none sm:px-2" value={option.value}>
                        <span className="me-1">{option.icon}</span>
                        <span>{option.label}</span>
                      </TabsTrigger>
                    ))}
                  </TabsList>
                </Tabs>
                <Textarea
                  placeholder={t('settings.subscriptions.applications.descriptionPlaceholder', {
                    lang: languageOptions.find(lang => lang.value === selectedLanguage)?.label || 'English',
                  })}
                  value={field.value?.[selectedLanguage] || ''}
                  onChange={e => {
                    const current = field.value || {}
                    field.onChange({
                      ...current,
                      [selectedLanguage]: e.target.value,
                    })
                  }}
                  className={cn('min-h-[60px] resize-none text-xs', isRtl && selectedLanguage !== 'fa' && 'text-left')}
                  dir={isRtl && selectedLanguage !== 'fa' ? 'ltr' : undefined}
                  rows={2}
                />
              </div>
            </FormControl>
            <FormMessage />
          </FormItem>
        )}
      />

      <FormField
        control={control}
        name="recommended"
        render={({ field }) => (
          <FormItem className="flex flex-row items-center justify-between space-y-0 rounded-lg border bg-muted/30 p-3 sm:col-span-2">
            <div className="space-y-0.5">
              <FormLabel className="text-xs font-medium">{t('settings.subscriptions.applications.recommended')}</FormLabel>
              <FormDescription className="text-xs text-muted-foreground">{t('settings.subscriptions.applications.recommendedDescription')}</FormDescription>
            </div>
            <FormControl>
              <Switch checked={field.value} onCheckedChange={field.onChange} />
            </FormControl>
          </FormItem>
        )}
      />
    </div>
  )
}

function ApplicationFieldsGridEdit({
  form,
  applicationIndex,
  iconBroken,
  setIconBroken,
}: {
  form: UseFormReturn<SubscriptionFormData>
  applicationIndex: number
  iconBroken: boolean
  setIconBroken: (v: boolean) => void
}) {
  const { t } = useTranslation()
  const isRtl = useDirDetection() === 'rtl'
  const [selectedLanguage, setSelectedLanguage] = useState('en')
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
      <FormField
        control={form.control}
        name={`applications.${applicationIndex}.name`}
        render={({ field }) => (
          <FormItem className="space-y-1">
            <FormLabel className="text-xs text-muted-foreground/80">{t('settings.subscriptions.applications.name')}</FormLabel>
            <FormControl>
              <Input placeholder={t('settings.subscriptions.applications.namePlaceholder')} {...field} className="h-8 text-xs" />
            </FormControl>
            {form.formState.errors.applications?.[applicationIndex]?.name && (
              <p className="text-[0.8rem] font-medium text-destructive">{t('validation.required', { field: t('settings.subscriptions.applications.name') })}</p>
            )}
          </FormItem>
        )}
      />

      <FormField
        control={form.control}
        name={`applications.${applicationIndex}.icon_url`}
        render={({ field }) => (
          <FormItem className="space-y-1">
            <div className="flex items-center gap-1.5">
              <FormLabel className="text-xs text-muted-foreground/80">{t('settings.subscriptions.applications.iconUrl', { defaultValue: 'Icon URL' })}</FormLabel>
              <IconUrlInfoPopover />
            </div>
            <FormControl>
              <div className="flex items-center gap-2">
                <Input placeholder={t('settings.subscriptions.applications.iconUrlPlaceholder', { defaultValue: 'https://...' })} {...field} className="h-8 min-w-0 flex-1 font-mono text-xs" dir="ltr" />
                {field.value && !iconBroken && isValidIconUrl(String(field.value)) ? (
                  <img src={String(field.value)} alt="" className="h-8 w-8 shrink-0 rounded-sm object-cover" onError={() => setIconBroken(true)} />
                ) : (
                  <div className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-sm bg-muted text-muted-foreground/80">
                    <span className="text-[10px]">🖼️</span>
                  </div>
                )}
              </div>
            </FormControl>
            <FormMessage />
          </FormItem>
        )}
      />

      <FormField
        control={form.control}
        name={`applications.${applicationIndex}.platform`}
        render={({ field }) => (
          <FormItem className="space-y-1 sm:col-span-2">
            <FormLabel className="text-xs text-muted-foreground/80">{t('settings.subscriptions.applications.platform')}</FormLabel>
            <Select onValueChange={field.onChange} value={field.value}>
              <FormControl>
                <SelectTrigger className="h-8 w-full text-xs">
                  <SelectValue />
                </SelectTrigger>
              </FormControl>
              <SelectContent className="scrollbar-thin z-[60]">
                {platformOptions.map(option => (
                  <SelectItem key={option.value} value={option.value}>
                    <div className="flex items-center gap-1.5">
                      <PlatformIcon platform={option.value} />
                      <span className="text-xs">{t(option.label)}</span>
                    </div>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <FormMessage />
          </FormItem>
        )}
      />

      <FormField
        control={form.control}
        name={`applications.${applicationIndex}.import_url`}
        render={({ field }) => (
          <FormItem className="space-y-1 sm:col-span-2">
            <FormLabel className="text-xs text-muted-foreground/80">{t('settings.subscriptions.applications.importUrl')}</FormLabel>
            <FormControl>
              <Input placeholder={t('settings.subscriptions.applications.importUrlPlaceholder')} {...field} className="h-8 text-left font-mono text-xs" dir="ltr" />
            </FormControl>
            <FormDescription className="text-xs text-muted-foreground">{t('settings.subscriptions.applications.importUrlDescription')}</FormDescription>
            <FormMessage />
          </FormItem>
        )}
      />

      <FormField
        control={form.control}
        name={`applications.${applicationIndex}.description`}
        render={({ field }) => (
          <FormItem className="space-y-1 sm:col-span-2">
            <FormLabel className="text-xs text-muted-foreground/80">{t('settings.subscriptions.applications.descriptionApp')}</FormLabel>
            <FormControl>
              <div className="flex flex-col gap-2">
                <Tabs value={selectedLanguage} onValueChange={setSelectedLanguage} className="w-full">
                  <TabsList className="flex h-auto w-full flex-wrap gap-1 overflow-x-auto px-1 sm:w-fit sm:flex-nowrap sm:gap-4">
                    {languageOptions.map(option => (
                      <TabsTrigger key={option.value} className="flex-1 px-1 text-xs sm:flex-none sm:px-2" value={option.value}>
                        <span className="me-1">{option.icon}</span>
                        <span>{option.label}</span>
                      </TabsTrigger>
                    ))}
                  </TabsList>
                </Tabs>
                <Textarea
                  placeholder={t('settings.subscriptions.applications.descriptionPlaceholder', {
                    lang: languageOptions.find(lang => lang.value === selectedLanguage)?.label || 'English',
                  })}
                  value={field.value?.[selectedLanguage] || ''}
                  onChange={e => {
                    const current = field.value || {}
                    field.onChange({
                      ...current,
                      [selectedLanguage]: e.target.value,
                    })
                  }}
                  className={cn('min-h-[60px] resize-none text-xs', isRtl && selectedLanguage !== 'fa' && 'text-left')}
                  dir={isRtl && selectedLanguage !== 'fa' ? 'ltr' : undefined}
                  rows={2}
                />
              </div>
            </FormControl>
            <FormMessage />
          </FormItem>
        )}
      />

      <FormField
        control={form.control}
        name={`applications.${applicationIndex}.recommended`}
        render={({ field }) => (
          <FormItem className="flex flex-row items-center justify-between space-y-0 rounded-lg border bg-muted/30 p-3 sm:col-span-2">
            <div className="space-y-0.5">
              <FormLabel className="text-xs font-medium">{t('settings.subscriptions.applications.recommended')}</FormLabel>
              <FormDescription className="text-xs text-muted-foreground">{t('settings.subscriptions.applications.recommendedDescription')}</FormDescription>
            </div>
            <FormControl>
              <Switch checked={field.value} onCheckedChange={field.onChange} />
            </FormControl>
          </FormItem>
        )}
      />
    </div>
  )
}

type DownloadLinksSectionProps = {
  variant: 'create' | 'edit'
  linksFieldName: string
  rowIdPrefix: string
  applicationIndex?: number
  restoredLinks?: SubscriptionApplicationFormData['download_links'] | null
  restoreLinksVersion?: number
}

function DownloadLinksSection({
  variant,
  linksFieldName,
  rowIdPrefix,
  applicationIndex,
  restoredLinks,
  restoreLinksVersion = 0,
}: DownloadLinksSectionProps) {
  const { t } = useTranslation()
  const isRtl = useDirDetection() === 'rtl'
  const { control } = useFormContext<SubscriptionFormData & SubscriptionApplicationFormData>()
  const { errors } = useFormState({ control })

  const { fields, append, remove, replace } = useFieldArray({
    control: control as Control<SubscriptionFormData & SubscriptionApplicationFormData>,
    name: linksFieldName as FieldArrayPath<SubscriptionFormData & SubscriptionApplicationFormData>,
  })

  useEffect(() => {
    if (variant !== 'edit' || restoreLinksVersion === 0 || !restoredLinks) return
    replace(restoredLinks.map(link => ({ ...link })))
  }, [replace, restoredLinks, restoreLinksVersion, variant])

  const watchedLinks = useWatch({
    control: control as Control<SubscriptionFormData & SubscriptionApplicationFormData>,
    name: linksFieldName as FieldPath<SubscriptionFormData & SubscriptionApplicationFormData>,
  }) as { language?: string }[] | undefined

  const addDownloadLink = () => {
    append({ name: '', url: '', language: 'en' })
  }

  const createErrors = errors as FieldErrors<SubscriptionApplicationFormData>
  const editErrors = errors as FieldErrors<SubscriptionFormData>
  const downloadLinksRootError =
    variant === 'create'
      ? createErrors.download_links?.message
      : applicationIndex !== undefined
        ? editErrors.applications?.[applicationIndex]?.download_links?.message
        : undefined

  return (
    <div className="space-y-2">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <FormLabel className="text-xs font-medium text-muted-foreground/80">
          {t('settings.subscriptions.applications.downloadLinks')} ({fields.length})
        </FormLabel>
        <Button type="button" variant="outline" size="sm" onClick={addDownloadLink} className="h-7 w-full text-xs sm:w-auto">
          <Plus className="me-1 h-3 w-3" />
          <span className="hidden sm:inline">{t('settings.subscriptions.applications.addDownloadLink')}</span>
          <span className="sm:hidden">{t('settings.subscriptions.applications.addDownloadLink', { defaultValue: 'Add Link' })}</span>
        </Button>
      </div>

      {downloadLinksRootError && (
        <p className="px-1 text-[0.8rem] font-medium text-destructive">
          {t('settings.subscriptions.applications.downloadLinksRequired', { defaultValue: 'At least one download link is required' })}
        </p>
      )}

      {fields.length === 0 ? (
        <div className="py-4 text-center text-muted-foreground">
          <p className="text-xs">{t('settings.subscriptions.applications.noDownloadLinks')}</p>
        </div>
      ) : (
        <div className="max-h-[min(50dvh,28rem)] space-y-2 overflow-y-auto pe-0.5">
          {fields.map((linkField, linkIndex) => {
            const base = `${linksFieldName}.${linkIndex}` as const
            const linkLang = watchedLinks?.[linkIndex]?.language ?? 'en'
            const ltrForThis = isRtl && linkLang !== 'fa'

            const nameErr =
              variant === 'create'
                ? createErrors.download_links?.[linkIndex]?.name
                : applicationIndex !== undefined
                  ? editErrors.applications?.[applicationIndex]?.download_links?.[linkIndex]?.name
                  : undefined
            const urlErr =
              variant === 'create'
                ? createErrors.download_links?.[linkIndex]?.url
                : applicationIndex !== undefined
                  ? editErrors.applications?.[applicationIndex]?.download_links?.[linkIndex]?.url
                  : undefined

            return (
              <div key={`${rowIdPrefix}-${linkField.id}`} className="flex flex-col gap-2 rounded-md border bg-muted/20 p-2 sm:flex-row">
                <FormField
                  control={control}
                  name={`${base}.name` as FieldPath<SubscriptionFormData & SubscriptionApplicationFormData>}
                  render={({ field }) => (
                    <FormItem className="min-w-0 flex-1">
                      <FormControl>
                        <Input
                          placeholder={t('settings.subscriptions.applications.downloadLinkNamePlaceholder')}
                          name={field.name}
                          onBlur={field.onBlur}
                          onChange={field.onChange}
                          ref={field.ref}
                          value={String(field.value ?? '')}
                          className={cn('h-7 text-xs', ltrForThis && 'text-left')}
                          dir={ltrForThis ? 'ltr' : undefined}
                        />
                      </FormControl>
                      {nameErr && (
                        <p className="text-[0.75rem] font-medium text-destructive">
                          {t('validation.required', { field: t('settings.subscriptions.applications.downloadLinkName', { defaultValue: 'Download link name' }) })}
                        </p>
                      )}
                    </FormItem>
                  )}
                />
                <FormField
                  control={control}
                  name={`${base}.url` as FieldPath<SubscriptionFormData & SubscriptionApplicationFormData>}
                  render={({ field }) => (
                    <FormItem className="min-w-0 flex-1">
                      <FormControl>
                        <Input
                          placeholder={t('settings.subscriptions.applications.downloadLinkUrlPlaceholder')}
                          name={field.name}
                          onBlur={field.onBlur}
                          onChange={field.onChange}
                          ref={field.ref}
                          value={String(field.value ?? '')}
                          className="h-7 text-left font-mono text-xs"
                          dir="ltr"
                        />
                      </FormControl>
                      {urlErr && <p className="text-[0.75rem] font-medium text-destructive">{t('validation.url', { defaultValue: 'Please enter a valid URL' })}</p>}
                    </FormItem>
                  )}
                />
                <div className="flex items-start gap-2 sm:items-center">
                  <FormField
                    control={control}
                    name={`${base}.language` as FieldPath<SubscriptionFormData & SubscriptionApplicationFormData>}
                    render={({ field }) => (
                      <FormItem className="w-full sm:w-24">
                        <Select onValueChange={field.onChange} value={String(field.value ?? 'en')}>
                          <FormControl>
                            <SelectTrigger className="h-7 text-xs">
                              <SelectValue />
                            </SelectTrigger>
                          </FormControl>
                          <SelectContent className="scrollbar-thin z-[60]">
                            {languageOptions.map(option => (
                              <SelectItem key={option.value} value={option.value}>
                                <div className="flex items-center gap-1.5">
                                  <span className="text-xs">{option.icon}</span>
                                  <span className="text-xs">{option.label}</span>
                                </div>
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    onClick={() => remove(linkIndex)}
                    disabled={fields.length <= 1}
                    className="h-7 w-7 shrink-0 p-0 text-destructive hover:bg-destructive/10 disabled:opacity-40"
                    aria-label={t('remove', { defaultValue: 'Remove' })}
                  >
                    <Trash2 className="h-3 w-3" />
                  </Button>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
