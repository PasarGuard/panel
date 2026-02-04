import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { Button } from '@/components/ui/button'
import { Copy, MoreVertical, Pencil, Power, Trash2 } from 'lucide-react'
import { BaseHost, modifyHost, removeHost } from '@/service/api'
import { toast } from 'sonner'
import useDirDetection from '@/hooks/use-dir-detection'
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from '@/components/ui/alert-dialog'
import { cn } from '@/lib/utils'

interface HostActionsMenuProps {
  host: BaseHost
  onEdit: (host: BaseHost) => void
  onDuplicate: (host: BaseHost) => Promise<void>
  onDataChanged?: () => void
  className?: string
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

export default function HostActionsMenu({ host, onEdit, onDuplicate, onDataChanged, className }: HostActionsMenuProps) {
  const [isDeleteDialogOpen, setDeleteDialogOpen] = useState<boolean>(false)
  const { t } = useTranslation()
  const dir = useDirDetection()

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
    <div className={cn(className)} onClick={e => e.stopPropagation()}>
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

      <DeleteAlertDialog host={host} isOpen={isDeleteDialogOpen} onClose={() => setDeleteDialogOpen(false)} onConfirm={handleConfirmDelete} />
    </div>
  )
}
