import React, { useState } from 'react'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { queryClient } from '@/utils/query-client'
import { useUpdateCore, NodeResponse } from '@/service/api'
import { useXrayReleases } from '@/hooks/use-xray-releases'
import { LoaderButton } from '../ui/loader-button'
import { ExternalLink } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import useDirDetection from '@/hooks/use-dir-detection'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { Input } from '@/components/ui/input'

interface UpdateCoreDialogProps {
  node: NodeResponse
  isOpen: boolean
  onOpenChange: (open: boolean) => void
}

export default function UpdateCoreDialog({ node, isOpen, onOpenChange }: UpdateCoreDialogProps) {
  const { t } = useTranslation()
  const dir = useDirDetection()
  const [selectedVersion, setSelectedVersion] = useState<string>('latest')
  const [customVersion, setCustomVersion] = useState<string>('')
  const [versionMode, setVersionMode] = useState<'list' | 'custom'>('list')
  const [customVersionError, setCustomVersionError] = useState<string>('')
  const updateCoreMutation = useUpdateCore()
  const { latestVersion, releaseUrl, versions, isLoading: isLoadingReleases, hasUpdate } = useXrayReleases()

  const currentVersion = node.xray_version
  const showUpdateBadge = currentVersion && latestVersion && hasUpdate(currentVersion)

  React.useEffect(() => {
    if (isOpen) {
      setSelectedVersion('latest')
      setCustomVersion('')
      setVersionMode('list')
      setCustomVersionError('')
    }
  }, [isOpen])

  const validateCustomVersion = (version: string): boolean => {
    if (!version.trim()) {
      setCustomVersionError(t('nodeModal.customVersionRequired', { defaultValue: 'Version is required' }))
      return false
    }
    // Allow versions with or without 'v' prefix, and basic semantic versioning pattern
    const versionPattern = /^v?\d+\.\d+\.\d+(-[\w.]+)?$/
    const cleanVersion = version.trim()
    if (!versionPattern.test(cleanVersion)) {
      setCustomVersionError(t('nodeModal.invalidVersionFormat', { defaultValue: 'Invalid version format. Expected: vX.X.X or X.X.X' }))
      return false
    }
    setCustomVersionError('')
    return true
  }

  const handleCustomVersionChange = (value: string) => {
    setCustomVersion(value)
    if (customVersionError) {
      validateCustomVersion(value)
    }
  }

  const handleUpdate = async () => {
    try {
      let versionToSend: string

      if (versionMode === 'custom') {
        if (!validateCustomVersion(customVersion)) {
          return
        }
        versionToSend = customVersion.trim()
      } else {
        versionToSend = selectedVersion
        if (selectedVersion === 'latest') {
          if (!latestVersion) {
            toast.error(t('nodeModal.updateCoreFailed', {
              message: 'Latest version not available',
              defaultValue: 'Failed to update Xray core: Latest version not available',
            }))
            return
          }
          // Use actual latest version instead of 'latest' string
          versionToSend = latestVersion
        }
      }
      
      // Ensure version has 'v' prefix for backend pattern vX.X.X
      if (!versionToSend.startsWith('v')) {
        versionToSend = `v${versionToSend}`
      }
      
      const response = await updateCoreMutation.mutateAsync({
        nodeId: node.id,
        data: {
          core_version: versionToSend,
        },
      })
      const message = (response as any)?.detail || t('nodeModal.updateCoreSuccess', { defaultValue: 'Xray core updated successfully' })
      toast.success(message)
      onOpenChange(false)
      queryClient.invalidateQueries({ queryKey: ['/api/nodes'] })
      queryClient.invalidateQueries({ queryKey: ['/api/nodes/simple'] })
      queryClient.invalidateQueries({ queryKey: [`/api/node/${node.id}`] })
    } catch (error: any) {
      toast.error(
        t('nodeModal.updateCoreFailed', {
          message: error?.message || 'Unknown error',
          defaultValue: 'Failed to update Xray core: {message}',
        }),
      )
    }
  }

  return (
    <Dialog open={isOpen} onOpenChange={onOpenChange}>
      <DialogContent className={cn('sm:max-w-[520px]', dir === 'rtl' && 'sm:text-right')}>
        <DialogHeader className={cn('pb-2', dir === 'rtl' && 'text-right')}>
          <DialogTitle className={cn(dir === 'rtl' && 'text-right')}>
            {t('nodeModal.updateCoreTitle', { defaultValue: 'Update Xray Core' })}
          </DialogTitle>
          <DialogDescription className={cn(dir === 'rtl' && 'text-right')}>
            {t('nodeModal.updateCoreDescription', {
              nodeName: node.name,
              defaultValue: `Update Xray core for node «${node.name}»`,
            })}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-4">
          {/* Version Info Section */}
          <div className="rounded-lg border bg-muted/30 p-4 space-y-3">
            {currentVersion && (
              <div className="flex items-center justify-between">
                <span className={cn('text-sm font-medium', dir === 'rtl' && 'text-right')}>
                  {t('version.currentVersion', { defaultValue: 'Current Version' })}
                </span>
                <div className={cn('flex items-center gap-2', dir === 'rtl' && 'flex-row-reverse')}>
                  <span className="font-mono text-sm">{currentVersion}</span>
                  {showUpdateBadge && (
                    <Badge variant="outline" className="bg-amber-500/10 text-amber-700 border-amber-500/20 dark:bg-amber-400/10 dark:text-amber-300 dark:border-amber-400/20">
                      {t('nodeModal.updateAvailable', { defaultValue: 'Update Available' })}
                    </Badge>
                  )}
                </div>
              </div>
            )}
            {latestVersion && (
              <div className="flex items-center justify-between pt-2 border-t">
                <span className={cn('text-sm font-medium', dir === 'rtl' && 'text-right')}>
                  {t('nodeModal.latest', { defaultValue: 'Latest' })}
                </span>
                <div className={cn('flex items-center gap-2', dir === 'rtl' && 'flex-row-reverse')}>
                  <span className="font-mono text-sm font-semibold">{latestVersion}</span>
                  {releaseUrl && (
                    <a
                      href={releaseUrl}
                      target="_blank"
                      rel="no-referrer"
                      className="text-muted-foreground hover:text-foreground transition-colors"
                      onClick={e => e.stopPropagation()}
                    >
                      <ExternalLink className="h-3.5 w-3.5" />
                    </a>
                  )}
                </div>
              </div>
            )}
          </div>

          {/* Version Selection */}
          <div className="space-y-3">
            <Tabs value={versionMode} onValueChange={(value) => setVersionMode(value as 'list' | 'custom')} className="w-full">
              <TabsList className={cn('grid w-full grid-cols-2', dir === 'rtl' && 'flex-row-reverse')}>
                <TabsTrigger value="list" className={cn('text-sm', dir === 'rtl' && 'text-right')}>
                  {t('nodeModal.selectFromList', { defaultValue: 'Select from List' })}
                </TabsTrigger>
                <TabsTrigger value="custom" className={cn('text-sm', dir === 'rtl' && 'text-right')}>
                  {t('nodeModal.customVersion', { defaultValue: 'Custom Version' })}
                </TabsTrigger>
              </TabsList>

              <TabsContent value="list" className="mt-3">
                {isLoadingReleases ? (
                  <div className={cn('rounded-md border p-8 text-center', dir === 'rtl' && 'text-right')}>
                    <div className="text-sm text-muted-foreground">
                      {t('nodeModal.loadingReleases', { defaultValue: 'Loading releases...' })}
                    </div>
                  </div>
                ) : (
                  <ScrollArea className="h-[200px] rounded-md border sm:h-[280px]">
                    <div className="p-2 space-y-1">
                      {latestVersion && (
                        <button
                          type="button"
                          onClick={() => setSelectedVersion('latest')}
                          className={cn(
                            'w-full rounded-md px-3 py-2.5 text-left text-sm transition-all',
                            'hover:bg-accent hover:text-accent-foreground',
                            'border-2',
                            selectedVersion === 'latest'
                              ? 'bg-accent text-accent-foreground border-primary'
                              : 'border-transparent',
                            dir === 'rtl' && 'text-right',
                          )}
                        >
                          <div className="flex items-center justify-between">
                            <div className={cn('flex items-center gap-2', dir === 'rtl' && 'flex-row-reverse')}>
                              <span className="font-semibold">{t('nodeModal.latest', { defaultValue: 'Latest' })}</span>
                              <Badge variant="secondary" className="text-[10px] font-medium">
                                {latestVersion}
                              </Badge>
                            </div>
                            {selectedVersion === 'latest' && (
                              <div className="h-2 w-2 rounded-full bg-primary" />
                            )}
                          </div>
                        </button>
                      )}
                      {versions
                        .filter(release => release.version !== latestVersion)
                        .slice(0, 10)
                        .map(release => (
                          <button
                            key={release.version}
                            type="button"
                            onClick={() => setSelectedVersion(release.version)}
                            className={cn(
                              'w-full rounded-md px-3 py-2 text-left text-sm transition-all',
                              'hover:bg-accent hover:text-accent-foreground',
                              'border-2',
                              selectedVersion === release.version
                                ? 'bg-accent text-accent-foreground border-primary'
                                : 'border-transparent',
                              dir === 'rtl' && 'text-right',
                            )}
                          >
                            <div className="flex items-center justify-between">
                              <span className="font-mono">{release.version}</span>
                              {selectedVersion === release.version && (
                                <div className="h-2 w-2 rounded-full bg-primary" />
                              )}
                            </div>
                          </button>
                        ))}
                    </div>
                  </ScrollArea>
                )}
              </TabsContent>

              <TabsContent value="custom" className="mt-3 space-y-3">
                <div className="space-y-2">
                  <label htmlFor="custom-version-input" className={cn('text-sm font-medium', dir === 'rtl' && 'text-right')}>
                    {t('nodeModal.enterVersion', { defaultValue: 'Enter Version' })}
                  </label>
                  <Input
                    id="custom-version-input"
                    type="text"
                    placeholder={t('nodeModal.versionPlaceholder', { defaultValue: 'e.g., v1.8.0 or 1.8.0' })}
                    value={customVersion}
                    onChange={(e) => handleCustomVersionChange(e.target.value)}
                    onBlur={() => {
                      if (customVersion) {
                        validateCustomVersion(customVersion)
                      }
                    }}
                    error={customVersionError}
                    isError={!!customVersionError}
                    className="font-mono"
                  />
                  <p dir={dir} className={cn('text-xs text-muted-foreground', dir === 'rtl' && 'text-right')}>
                    {t('nodeModal.versionHint', { defaultValue: 'Enter a version in the format vX.X.X or X.X.X (e.g., v1.8.0)' })}
                  </p>
                </div>
              </TabsContent>
            </Tabs>
          </div>
        </div>

        <DialogFooter className="gap-2">
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={updateCoreMutation.isPending}>
            {t('cancel')}
          </Button>
          <LoaderButton
            className="!m-0"
            onClick={handleUpdate}
            disabled={
              updateCoreMutation.isPending ||
              isLoadingReleases ||
              (versionMode === 'list' && !latestVersion) ||
              (versionMode === 'custom' && (!customVersion.trim() || !!customVersionError))
            }
            isLoading={updateCoreMutation.isPending}
            loadingText={t('nodeModal.updating', { defaultValue: 'Updating...' })}
          >
            {t('nodeModal.update', { defaultValue: 'Update' })}
          </LoaderButton>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
