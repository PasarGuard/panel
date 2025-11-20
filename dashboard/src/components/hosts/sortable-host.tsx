import { useSortable } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { UniqueIdentifier } from '@dnd-kit/core'
import { BaseHost, removeHost, modifyHost } from '@/service/api'
import { Card } from '../ui/card'
import { ChevronsLeftRightEllipsis, CloudCog, Copy, GripVertical, MoreVertical, Pencil, Power, Trash2, Settings } from 'lucide-react'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from '../ui/dropdown-menu'
import { Button } from '../ui/button'
import { useTranslation } from 'react-i18next'
import useDirDetection from '@/hooks/use-dir-detection'
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from '../ui/alert-dialog'
import { cn } from '@/lib/utils'
import { toast } from 'sonner'
import { useState } from 'react'

interface SortableHostProps {
  host: BaseHost
  onEdit: (host: BaseHost) => void
  onDuplicate: (host: BaseHost) => Promise<void>
  onDataChanged?: () => void // New callback for notifying parent about data changes
  disabled?: boolean // Disable drag and drop when updating priorities
}

const DeleteAlertDialog = ({ host, isOpen, onClose, onConfirm }: { host: BaseHost; isOpen: boolean; onClose: () => void; onConfirm: () => void }) => {
  const { t } = useTranslation()
  const dir = useDirDetection()

  return (
    <AlertDialog open={isOpen} onOpenChange={onClose}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{t('deleteHost.title')}</AlertDialogTitle>
          <AlertDialogDescription>
            <span dir={dir} dangerouslySetInnerHTML={{ __html: t('deleteHost.prompt', { name: host.remark ?? '' }) }} />
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel onClick={onClose}>{t('cancel')}</AlertDialogCancel>
          <AlertDialogAction variant="destructive" onClick={onConfirm}>
            {t('delete')}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}

export default function SortableHost({ host, onEdit, onDuplicate, onDataChanged, disabled = false }: SortableHostProps) {
  const [isDeleteDialogOpen, setDeleteDialogOpen] = useState<boolean>(false)
  const { t } = useTranslation()
  const dir = useDirDetection()
  // Ensure host.id is not null before using it
  if (!host.id) {
    return null
  }

  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: host.id as UniqueIdentifier,
    disabled: disabled,
  })

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    zIndex: isDragging ? 2 : 1,
    opacity: isDragging ? 0.8 : 1,
  }
  const cursor = isDragging ? 'grabbing' : 'grab'

  const handleToggleStatus = async () => {
    if (!host.id) return

    try {
      const { id, ...hostData } = host

      let transformedMuxSettings = hostData.mux_settings
      if (hostData.mux_settings?.xray) {
        transformedMuxSettings = {
          ...hostData.mux_settings,
          xray: {
            enabled: hostData.mux_settings.xray.enabled,
            concurrency: hostData.mux_settings.xray.concurrency,
            xudp_concurrency: hostData.mux_settings.xray.xudpConcurrency ?? undefined,
            xudp_proxy_udp_443: hostData.mux_settings.xray.xudpProxyUDP443 ?? undefined,
          } as any,
        }
      }

      let transformedTransportSettings = hostData.transport_settings
      if (hostData.transport_settings?.xhttp_settings?.xmux) {
        transformedTransportSettings = {
          ...hostData.transport_settings,
          xhttp_settings: {
            ...hostData.transport_settings.xhttp_settings,
            xmux: {
              max_concurrency: hostData.transport_settings.xhttp_settings.xmux.maxConcurrency ?? undefined,
              max_connections: hostData.transport_settings.xhttp_settings.xmux.maxConnections ?? undefined,
              c_max_reuse_times: hostData.transport_settings.xhttp_settings.xmux.cMaxReuseTimes ?? undefined,
              h_max_reusable_secs: hostData.transport_settings.xhttp_settings.xmux.hMaxReusableSecs ?? undefined,
              h_max_request_times: hostData.transport_settings.xhttp_settings.xmux.hMaxRequestTimes ?? undefined,
              h_keep_alive_period: hostData.transport_settings.xhttp_settings.xmux.hKeepAlivePeriod ?? undefined,
            } as any,
          },
        }
      }

      await modifyHost(host.id, {
        ...hostData,
        mux_settings: transformedMuxSettings as any,
        transport_settings: transformedTransportSettings as any,
        is_disabled: !host.is_disabled,
      } as any)

      toast.success(
        t(host.is_disabled ? 'host.enableSuccess' : 'host.disableSuccess', {
          name: host.remark ?? '',
          defaultValue: `Host "{name}" has been ${host.is_disabled ? 'enabled' : 'disabled'} successfully`,
        }),
      )

      // Notify parent that data has changed
      if (onDataChanged) {
        onDataChanged()
      }
    } catch (error) {
      toast.error(
        t(host.is_disabled ? 'host.enableFailed' : 'host.disableFailed', {
          name: host.remark ?? '',
          defaultValue: `Failed to ${host.is_disabled ? 'enable' : 'disable'} host "{name}"`,
        }),
      )
    }
  }

  const handleDeleteClick = (event: Event) => {
    event.stopPropagation()
    setDeleteDialogOpen(true)
  }

  const handleConfirmDelete = async () => {
    if (!host.id) return

    try {
      await removeHost(host.id)

      toast.success(
        t('deleteHost.deleteSuccess', {
          name: host.remark ?? '',
          defaultValue: 'Host "{name}" removed successfully',
        }),
      )

      setDeleteDialogOpen(false)

      // Notify parent that data has changed
      if (onDataChanged) {
        onDataChanged()
      }
    } catch (error) {
      toast.error(
        t('deleteHost.deleteFailed', {
          name: host.remark ?? '',
          defaultValue: 'Failed to remove host "{name}"',
        }),
      )
    }
  }

  return (
    <div ref={setNodeRef} className="cursor-default" style={style} {...attributes}>
      <Card className="group relative h-full cursor-pointer p-4 transition-colors hover:bg-accent" onClick={() => onEdit(host)}>
        <div className="flex items-center gap-3">
          <button
            style={{ cursor: disabled ? 'not-allowed' : cursor }}
            className={cn('touch-none transition-opacity', disabled ? 'cursor-not-allowed opacity-30' : 'opacity-50 group-hover:opacity-100')}
            {...(disabled ? {} : listeners)}
            disabled={disabled}
          >
            <GripVertical className="h-5 w-5" />
            <span className="sr-only">Drag to reorder</span>
          </button>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <div className={cn('min-h-2 min-w-2 rounded-full', host.is_disabled ? 'bg-red-500' : 'bg-green-500')} />
              <div className="truncate font-medium">{host.remark ?? ''}</div>
            </div>
            <div className={cn('flex items-center gap-1', dir === 'rtl' && 'justify-start')}>
              <ChevronsLeftRightEllipsis className="h-4 w-4 text-muted-foreground" />
              <div dir="ltr" className="truncate text-sm text-muted-foreground">
                {Array.isArray(host.address) ? host.address[0] || '' : (host.address ?? '')}:{host.port === null ? <Settings className="inline h-3 w-3" /> : host.port}
              </div>
            </div>
            <div className="flex items-center gap-1 truncate text-sm text-muted-foreground">
              <CloudCog className="h-4 w-4" />
              <span>{t('inbound')}: </span>
              <span dir="ltr">{host.inbound_tag ?? ''}</span>
            </div>
          </div>
          <div onClick={e => e.stopPropagation()}>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="icon">
                  <MoreVertical className="h-4 w-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem
                  onSelect={e => {
                    e.stopPropagation()
                    handleToggleStatus()
                  }}
                >
                  <Power className="mr-2 h-4 w-4" />
                  {host?.is_disabled ? t('enable') : t('disable')}
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem
                  onSelect={e => {
                    e.stopPropagation()
                    onEdit(host)
                  }}
                >
                  <Pencil className="mr-2 h-4 w-4" />
                  {t('edit')}
                </DropdownMenuItem>
                <DropdownMenuItem
                  onSelect={e => {
                    e.stopPropagation()
                    onDuplicate(host)
                  }}
                >
                  <Copy className="mr-2 h-4 w-4" />
                  {t('duplicate')}
                </DropdownMenuItem>
                <DropdownMenuItem onSelect={handleDeleteClick} className="text-destructive">
                  <Trash2 className="mr-2 h-4 w-4" />
                  {t('delete')}
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </div>
      </Card>

      <DeleteAlertDialog host={host} isOpen={isDeleteDialogOpen} onClose={() => setDeleteDialogOpen(false)} onConfirm={handleConfirmDelete} />
    </div>
  )
}
