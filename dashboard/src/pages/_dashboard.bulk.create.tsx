'use client'

import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { useNavigate } from 'react-router'
import { 
  useBulkCreateUsersFromTemplate, 
  useGetUserTemplates,
  UsernameGenerationStrategy,
  BulkUsersCreateResponse
} from '@/service/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { CopyButton } from '@/components/common/copy-button'
import QRCodeModal from '@/components/dialogs/qrcode-modal'
import { useClipboard } from '@/hooks/use-clipboard'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { 
  UserPlus, 
  Users, 
  FileText, 
  Hash,
  Sparkles,
  CheckCircle2,
  AlertTriangle,
  FileQuestion,
  Copy,
  ArrowLeft,
  QrCode,
  Check
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import useDirDetection from '@/hooks/use-dir-detection'
import { formatBytes } from '@/utils/formatByte'
import { Skeleton } from '@/components/ui/skeleton'

export default function BulkCreateUsersPage() {
  const { t, i18n } = useTranslation()
  const navigate = useNavigate()
  const dir = useDirDetection()
  const isRTL = dir === 'rtl'

  const [selectedTemplateId, setSelectedTemplateId] = useState<number | undefined>()
  const [baseUsername, setBaseUsername] = useState('')
  const [userCount, setUserCount] = useState<string>('1')
  const [strategy, setStrategy] = useState<UsernameGenerationStrategy>(
    UsernameGenerationStrategy.sequence
  )
  const [startNumber, setStartNumber] = useState<string>('1')
  const [note, setNote] = useState('')
  const [touchedFields, setTouchedFields] = useState<Set<string>>(new Set())
  
  const [createdUrls, setCreatedUrls] = useState<string[]>([])
  const [showSuccess, setShowSuccess] = useState(false)
  const [selectedQRUrl, setSelectedQRUrl] = useState<string | null>(null)
  const [previewUsernames, setPreviewUsernames] = useState<string[]>([])

  const { data: templatesData, isLoading: templatesLoading } = useGetUserTemplates({ limit: 100, offset: 0 })
  const createMutation = useBulkCreateUsersFromTemplate()

  const templates = templatesData || []
  const selectedTemplate = templates.find(t => t.id === selectedTemplateId)

  useEffect(() => {
    if (templates.length > 0 && !selectedTemplateId) {
      setSelectedTemplateId(templates[0].id)
    }
  }, [templates, selectedTemplateId])

  const handleCreate = () => {
    // Mark all fields as touched when user tries to submit
    setTouchedFields(new Set(['userCount', 'baseUsername', 'startNumber']))
    
    if (!selectedTemplateId) {
      toast.error(t('error'), { description: t('bulk.create.selectTemplateError') })
      return
    }

    const parsedUserCount = parseInt(userCount) || 0
    if (!userCount || parsedUserCount < 1 || parsedUserCount > 500) {
      toast.error(t('error'), { description: t('bulk.create.invalidCount') })
      return
    }

    // Base username is only required for sequence strategy
    if (strategy === UsernameGenerationStrategy.sequence && !baseUsername) {
      toast.error(t('error'), { description: t('bulk.create.baseUsernameRequired') })
      return
    }

    const parsedStartNumber = parseInt(startNumber) || 1

    const payload = {
      user_template_id: selectedTemplateId,
      count: parsedUserCount,
      // When strategy is 'random', username must be null
      username: strategy === UsernameGenerationStrategy.random ? null : (baseUsername || undefined),
      strategy: strategy,
      start_number: strategy === UsernameGenerationStrategy.sequence && parsedStartNumber > 1 ? parsedStartNumber : undefined,
      note: note || undefined,
    }

    createMutation.mutate(
      { data: payload },
      {
        onSuccess: (response: BulkUsersCreateResponse) => {
          const urls = response.subscription_urls || []
          const createdCount = response.created || 0
          
          // If no users were created, it means all users already exist
          if (createdCount === 0) {
            toast.error(
              t('bulk.create.failed'),
              { description: t('bulk.create.allUsersExist') }
            )
            return
          }
          
          setCreatedUrls(urls)
          setShowSuccess(true)
          
          toast.success(
            t('bulk.create.success'), 
            { 
              description: t('bulk.create.created', { 
                count: createdCount
              })
            }
          )

          // Reset form
          setBaseUsername('')
          setUserCount('1')
          setStartNumber('1')
          setNote('')
        },
        onError: (error: any) => {
          toast.error(
            t('bulk.create.failed'), 
            { description: error?.message || JSON.stringify(error) }
          )
        },
      }
    )
  }

  const { copy: copyAll, copied: allCopied } = useClipboard({ timeout: 2000 })
  
  const copyAllUrls = async () => {
    const text = createdUrls.join('\n')
    await copyAll(text)
  }

  const getStrategyLabel = (strat: UsernameGenerationStrategy) => {
    switch (strat) {
      case UsernameGenerationStrategy.sequence:
        return t('bulk.create.strategy.sequence')
      case UsernameGenerationStrategy.random:
        return t('bulk.create.strategy.random')
      default:
        return strat
    }
  }

  // Generate preview usernames only when relevant inputs change
  useEffect(() => {
    const previews: string[] = []
    const parsedUserCount = parseInt(userCount) || 0
    const parsedStartNumber = parseInt(startNumber) || 1
    
    const prefix = selectedTemplate?.username_prefix || ''
    const suffix = selectedTemplate?.username_suffix || ''
    
    if (strategy === UsernameGenerationStrategy.sequence) {
      if (!baseUsername || parsedUserCount === 0) {
        setPreviewUsernames([])
        return
      }
      for (let i = 0; i < Math.min(3, parsedUserCount); i++) {
        const username = `${prefix}${baseUsername}${parsedStartNumber + i}${suffix}`
        previews.push(username)
      }
    } else if (strategy === UsernameGenerationStrategy.random) {
      if (parsedUserCount === 0) {
        setPreviewUsernames([])
        return
      }
      // For random strategy, generate stable example usernames based on userCount
      // Using a simple hash-like approach to keep them stable
      for (let i = 0; i < Math.min(3, parsedUserCount); i++) {
        // Create a stable "random" suffix based on index
        const stableSeed = `preview-${i}-${parsedUserCount}`.split('').reduce((acc, char) => acc + char.charCodeAt(0), 0)
        const randomPart = stableSeed.toString(36).substring(0, 6).padStart(6, '0')
        const username = `${prefix}user-${randomPart}${suffix}`
        previews.push(username)
      }
    }
    
    setPreviewUsernames(previews)
  }, [baseUsername, userCount, strategy, startNumber, selectedTemplate])

  // Show no templates message if there are no templates
  if (!templatesLoading && templates.length === 0) {
    return (
      <div className="flex w-full flex-1 items-center justify-center">
        <Card className="w-full max-w-md">
          <CardContent className="flex flex-col items-center justify-center space-y-4 py-10 text-center">
            <div className="rounded-full bg-muted p-6">
              <FileQuestion className="h-10 w-10 text-muted-foreground" />
            </div>
            <div className="space-y-2">
              <h3 className="text-lg font-semibold">
                {t('bulk.create.noTemplates')}
              </h3>
              <p className="text-sm text-muted-foreground">
                {t('bulk.create.noTemplatesDesc')}
              </p>
            </div>
            <Button onClick={() => navigate('/templates')} size="lg">
              <FileText className={cn("h-4 w-4", isRTL ? "ml-2" : "mr-2")} />
              {t('bulk.create.createTemplate')}
            </Button>
          </CardContent>
        </Card>
      </div>
    )
  }

  if (showSuccess && createdUrls.length > 0) {
    return (
      <div className="w-full space-y-4">
        <Button 
          variant="ghost" 
          onClick={() => { setShowSuccess(false); setCreatedUrls([]) }}
          className="mb-2"
        >
          <ArrowLeft className={cn("h-4 w-4", isRTL ? "ml-2 rotate-180" : "mr-2")} />
          {t('back')}
        </Button>

        <Alert className="border-green-200 bg-green-50 dark:border-green-800 dark:bg-green-950/20">
          <CheckCircle2 className="h-4 w-4 text-green-600 dark:text-green-400" />
          <AlertTitle className="text-green-800 dark:text-green-200">
            {t('bulk.create.successTitle')}
          </AlertTitle>
          <AlertDescription className="text-green-700 dark:text-green-300">
            {t('bulk.create.successDescription', { 
              count: createdUrls.length
            })}
          </AlertDescription>
        </Alert>

        <Card>
          <CardHeader>
            <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <CardTitle className="text-base sm:text-lg">
                  {t('bulk.create.subscriptionUrls')}
                </CardTitle>
                <CardDescription className="text-xs sm:text-sm">
                  {t('bulk.create.subscriptionUrlsDesc')}
                </CardDescription>
              </div>
              <Tooltip open={allCopied ? true : undefined}>
                <TooltipTrigger asChild>
                  <Button onClick={copyAllUrls} variant="outline" size="sm" className="w-full sm:w-auto">
                    {allCopied ? (
                      <>
                        <Check className={cn("h-4 w-4", isRTL ? "ml-2" : "mr-2")} />
                        {t('copied')}
                      </>
                    ) : (
                      <>
                        <Copy className={cn("h-4 w-4", isRTL ? "ml-2" : "mr-2")} />
                        {t('copyAll')}
                      </>
                    )}
                  </Button>
                </TooltipTrigger>
                <TooltipContent>
                  <p>{allCopied ? t('copied') : t('copyAll')}</p>
                </TooltipContent>
              </Tooltip>
            </div>
          </CardHeader>
          <CardContent>
            <div dir='ltr' className="max-h-[60vh] space-y-2 overflow-y-auto rounded-md border p-3">
              {createdUrls.map((url, index) => (
                <div 
                  key={index} 
                  className="group flex items-center gap-2 rounded-md border bg-muted/50 p-2 transition-colors hover:bg-muted"
                >
                  <code className="flex-1 overflow-hidden text-ellipsis whitespace-nowrap text-xs">
                    {url}
                  </code>
                  <CopyButton
                    value={url}
                    className="h-8 w-8 shrink-0"
                    copiedMessage="copied"
                    defaultMessage="clickToCopy"
                  />
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => setSelectedQRUrl(url)}
                    className="h-8 w-8 shrink-0"
                    title={t('qrcodeDialog.sublink')}
                  >
                    <QrCode className="h-4 w-4" />
                  </Button>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        {/* QR Code Modal */}
        {selectedQRUrl && (
          <QRCodeModal 
            subscribeUrl={selectedQRUrl} 
            onCloseModal={() => setSelectedQRUrl(null)} 
          />
        )}
      </div>
    )
  }

  return (
    <div className="w-full space-y-4">
      <Card>
        <CardHeader>
          <div className="flex items-start gap-3">
            <div className="rounded-lg bg-primary/10 p-2">
              <UserPlus className="h-5 w-5 text-primary" />
            </div>
            <div className="flex-1">
              <CardTitle className="text-base sm:text-lg">
                {t('bulk.create.title')}
              </CardTitle>
              <CardDescription className="text-xs sm:text-sm">
                {t('bulk.create.description')}
              </CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-6 relative">
          {/* Loading Overlay */}
          {createMutation.isPending && (
            <div className="absolute inset-0 z-10 flex items-center justify-center rounded-lg bg-background/80 backdrop-blur-sm">
              <div className="flex flex-col items-center gap-2">
                <div className="h-6 w-6 animate-spin rounded-full border-2 border-primary border-t-transparent" />
                <span className="text-sm text-muted-foreground">{t('bulk.create.creating')}</span>
              </div>
            </div>
          )}

          {/* Template Selection */}
          <div className="space-y-3">
            <Label htmlFor="template" className="flex items-center gap-2 text-sm font-medium">
              <FileText className="h-4 w-4 text-muted-foreground" />
              {t('bulk.create.selectTemplate')}
            </Label>
            {templatesLoading ? (
              <Skeleton className="h-10 w-full" />
            ) : (
              <Select 
                value={selectedTemplateId?.toString()} 
                onValueChange={(value) => setSelectedTemplateId(Number(value))}
                disabled={createMutation.isPending}
              >
                <SelectTrigger className="h-10">
                  <SelectValue placeholder={t('bulk.create.selectTemplatePlaceholder')} />
                </SelectTrigger>
                <SelectContent>
                  {templates.map((template) => (
                    <SelectItem key={template.id} value={template.id.toString()}>
                      <div className="flex items-center gap-2">
                        <span>{template.name || t('unnamed')}</span>
                        {template.is_disabled && (
                          <Badge variant="secondary" className="text-xs">
                            {t('disabled')}
                          </Badge>
                        )}
                      </div>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
            
            {templatesLoading ? (
              <div className="rounded-lg border bg-muted/50 p-3 space-y-2">
                <Skeleton className="h-4 w-full" />
                <Skeleton className="h-4 w-3/4" />
                <Skeleton className="h-4 w-1/2" />
              </div>
            ) : selectedTemplate ? (
              <div className="rounded-lg border bg-muted/50 p-3 text-xs sm:text-sm">
                <div className="space-y-1.5">
                  {selectedTemplate.username_prefix && (
                    <div className="flex items-center justify-between">
                      <span className="text-muted-foreground">{t('templates.prefix')}:</span>
                      <span className="font-medium font-mono">{selectedTemplate.username_prefix}</span>
                    </div>
                  )}
                  {selectedTemplate.username_suffix && (
                    <div className="flex items-center justify-between">
                      <span className="text-muted-foreground">{t('templates.suffix')}:</span>
                      <span className="font-medium font-mono">{selectedTemplate.username_suffix}</span>
                    </div>
                  )}
                  {selectedTemplate.data_limit !== null && selectedTemplate.data_limit !== undefined && (
                    <div className="flex items-center justify-between">
                      <span className="text-muted-foreground">{t('userDialog.dataLimit')}:</span>
                      <span className="font-medium" dir="ltr">{formatBytes(selectedTemplate.data_limit)}</span>
                    </div>
                  )}
                  {selectedTemplate.expire_duration !== null && selectedTemplate.expire_duration !== undefined && (
                    <div className="flex items-center justify-between">
                      <span className="text-muted-foreground">{t('expire')}:</span>
                      <span className="font-medium">{Math.floor(selectedTemplate.expire_duration / 86400)}{t('dateInfo.day')}</span>
                    </div>
                  )}
                  {selectedTemplate.group_ids && selectedTemplate.group_ids.length > 0 && (
                    <div className="flex items-center justify-between">
                      <span className="text-muted-foreground">{t('groups')}:</span>
                      <span className="font-medium">
                        {selectedTemplate.group_ids.length} {i18n.language === 'fa' ? 'گروه' : t('groups')}
                      </span>
                    </div>
                  )}
                </div>
              </div>
            ) : null}
          </div>

          <Separator />

          {/* Username Configuration */}
          <div className="space-y-4">
            <Label className="flex items-center gap-2 text-sm font-medium">
              <Users className="h-4 w-4 text-muted-foreground" />
              {t('bulk.create.userConfiguration')}
            </Label>

            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="count" className="text-sm">
                  {t('bulk.create.userCount')}
                </Label>
                {templatesLoading ? (
                  <Skeleton className="h-10 w-full" />
                ) : (
                  <>
                    <Input
                      id="count"
                      type="number"
                      min="1"
                      max="500"
                      value={userCount}
                      onChange={(e) => {
                        const value = e.target.value
                        if (value === '') {
                          setUserCount('')
                        } else {
                          const numValue = parseInt(value)
                          if (!isNaN(numValue) && numValue > 0) {
                            setUserCount(String(Math.min(500, Math.max(1, numValue))))
                          }
                        }
                        setTouchedFields(prev => new Set(prev).add('userCount'))
                      }}
                      onBlur={() => setTouchedFields(prev => new Set(prev).add('userCount'))}
                      className={cn("h-10", !userCount && touchedFields.has('userCount') && "border-destructive")}
                      disabled={createMutation.isPending}
                    />
                    {!userCount && touchedFields.has('userCount') ? (
                      <p className="text-xs text-destructive">
                        {t('validation.required', { field: t('bulk.create.userCount'), defaultValue: 'User count is required' })}
                      </p>
                    ) : (
                      <p className="text-xs text-muted-foreground">
                        {t('bulk.create.maxUsers')}
                      </p>
                    )}
                  </>
                )}
              </div>

              <div className="space-y-2">
                <Label htmlFor="strategy" className="text-sm">
                  {t('bulk.create.usernameStrategy')}
                </Label>
                {templatesLoading ? (
                  <Skeleton className="h-10 w-full" />
                ) : (
                  <Select 
                    value={strategy} 
                    onValueChange={(value) => {
                      setStrategy(value as UsernameGenerationStrategy)
                      // Clear username when switching to random strategy
                      if (value === UsernameGenerationStrategy.random) {
                        setBaseUsername('')
                      }
                    }}
                    disabled={createMutation.isPending}
                  >
                    <SelectTrigger className="h-10">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {Object.values(UsernameGenerationStrategy).map((strat) => (
                        <SelectItem key={strat} value={strat}>
                          {getStrategyLabel(strat)}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )}
              </div>
            </div>

            {strategy === UsernameGenerationStrategy.sequence && (
              <div className="space-y-2">
                <Label htmlFor="baseUsername" className="text-sm">
                  {t('bulk.create.baseUsername')}
                </Label>
                {templatesLoading ? (
                  <Skeleton className="h-10 w-full" />
                ) : (
                  <>
                    <Input
                      id="baseUsername"
                      value={baseUsername}
                      onChange={(e) => {
                        setBaseUsername(e.target.value)
                        setTouchedFields(prev => new Set(prev).add('baseUsername'))
                      }}
                      onBlur={() => setTouchedFields(prev => new Set(prev).add('baseUsername'))}
                      placeholder={t('bulk.create.baseUsernamePlaceholder')}
                      className={cn("h-10", !baseUsername && touchedFields.has('baseUsername') && "border-destructive")}
                      disabled={createMutation.isPending}
                    />
                    {!baseUsername && touchedFields.has('baseUsername') ? (
                      <p className="text-xs text-destructive">
                        {t('validation.required', { field: t('bulk.create.baseUsername'), defaultValue: 'Base username is required' })}
                      </p>
                    ) : (
                      <p className="text-xs text-muted-foreground">
                        {t('bulk.create.baseUsernameHelp')}
                      </p>
                    )}
                  </>
                )}
              </div>
            )}

            {strategy === UsernameGenerationStrategy.sequence && (
              <div className="space-y-2">
                <Label htmlFor="startNumber" className="flex items-center gap-2 text-sm">
                  <Hash className="h-3.5 w-3.5" />
                  {t('bulk.create.startNumber')}
                </Label>
                {templatesLoading ? (
                  <Skeleton className="h-10 w-full" />
                ) : (
                  <>
                    <Input
                      id="startNumber"
                      type="number"
                      min="1"
                      value={startNumber}
                      onChange={(e) => {
                        const value = e.target.value
                        if (value === '') {
                          setStartNumber('')
                        } else {
                          const numValue = parseInt(value)
                          if (!isNaN(numValue) && numValue > 0) {
                            setStartNumber(String(Math.max(1, numValue)))
                          }
                        }
                        setTouchedFields(prev => new Set(prev).add('startNumber'))
                      }}
                      onBlur={() => setTouchedFields(prev => new Set(prev).add('startNumber'))}
                      className={cn("h-10", !startNumber && touchedFields.has('startNumber') && "border-destructive")}
                      disabled={createMutation.isPending}
                    />
                    {!startNumber && touchedFields.has('startNumber') ? (
                      <p className="text-xs text-destructive">
                        {t('validation.required', { field: t('bulk.create.startNumber'), defaultValue: 'Start number is required' })}
                      </p>
                    ) : (
                      <p className="text-xs text-muted-foreground">
                        {t('bulk.create.startNumberHelp')}
                      </p>
                    )}
                  </>
                )}
              </div>
            )}

            {/* Preview */}
            {previewUsernames.length > 0 && (
              <div className="rounded-lg border bg-primary/5 p-4">
                <div className="mb-2 flex items-center gap-2">
                  <Sparkles className="h-4 w-4 text-primary" />
                  <span className="text-sm font-medium">
                    {t('bulk.create.preview')}
                  </span>
                </div>
                <div className="flex flex-wrap gap-2">
                  {previewUsernames.map((username, index) => (
                    <Badge key={index} variant="secondary" className="font-mono text-xs">
                      {username}
                    </Badge>
                  ))}
                  {parseInt(userCount) > 3 && (
                    <Badge variant="outline" className="text-xs">
                      +{parseInt(userCount) - 3} {t('more')}
                    </Badge>
                  )}
                </div>
              </div>
            )}
          </div>

          <Separator />

          {/* Optional Note */}
          <div className="space-y-2">
            <Label htmlFor="note" className="text-sm">
              {t('bulk.create.note')}
            </Label>
            {templatesLoading ? (
              <Skeleton className="h-20 w-full" />
            ) : (
              <Textarea
                id="note"
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder={t('bulk.create.notePlaceholder')}
                rows={3}
                className="resize-none"
                disabled={createMutation.isPending}
              />
            )}
          </div>

          {/* Validation Warning */}
          {strategy === UsernameGenerationStrategy.sequence && !baseUsername && (
            <Alert variant="destructive">
              <AlertTriangle className="h-4 w-4" />
              <AlertTitle className="text-sm">{t('error')}</AlertTitle>
              <AlertDescription className="text-xs">
                {t('bulk.create.baseUsernameRequired')}
              </AlertDescription>
            </Alert>
          )}
        </CardContent>
      </Card>

      {/* Action Button */}
      <div className="flex justify-end">
        <Button
          onClick={handleCreate}
          disabled={
            createMutation.isPending || 
            !selectedTemplateId || 
            !userCount ||
            parseInt(userCount) < 1 || 
            parseInt(userCount) > 500 ||
            (strategy === UsernameGenerationStrategy.sequence && !baseUsername)
          }
          size="lg"
          className={cn(
            "w-full sm:w-auto sm:min-w-[200px]",
            createMutation.isPending && "animate-pulse"
          )}
        >
          {createMutation.isPending ? (
            <>
              <div className={cn("h-4 w-4 animate-spin rounded-full border-2 border-background border-t-transparent", isRTL ? "ml-2" : "mr-2")} />
              {t('bulk.create.creating')}
            </>
          ) : (
            <>
              <UserPlus className={cn("h-4 w-4", isRTL ? "ml-2" : "mr-2")} />
              {t('bulk.create.createUsers', { count: parseInt(userCount) || 0 })}
            </>
          )}
        </Button>
      </div>
    </div>
  )
}
