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
      // Send full host data with only is_disabled toggled
      await modifyHost(host.id, {
        remark: host.remark || '',
        address: host.address || [],
        port: host.port,
        inbound_tag: host.inbound_tag || '',
        status: host.status || [],
        host: host.host || [],
        sni: host.sni || [],
        path: host.path || '',
        security: host.security || 'inbound_default',
        alpn: (!host.alpn || host.alpn.length === 0) ? undefined : host.alpn,
        fingerprint: host.fingerprint === '' ? undefined : host.fingerprint,
        allowinsecure: host.allowinsecure || false,
        is_disabled: !host.is_disabled,
        random_user_agent: host.random_user_agent || false,
        use_sni_as_host: host.use_sni_as_host || false,
        priority: host.priority || 0,
        ech_config_list: host.ech_config_list,
        fragment_settings: host.fragment_settings,
        noise_settings: host.noise_settings,
        mux_settings: host.mux_settings,
        transport_settings: host.transport_settings as any, // Type cast needed due to Output/Input mismatch
        http_headers: host.http_headers || {},
      })

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
      <Card className="p-4 relative group h-full hover:bg-accent transition-colors cursor-pointer" onClick={() => onEdit(host)}>
        <div className="flex items-center gap-3">
          <button 
            style={{ cursor: disabled ? 'not-allowed' : cursor }} 
            className={cn(
              "touch-none transition-opacity",
              disabled ? "opacity-30 cursor-not-allowed" : "opacity-50 group-hover:opacity-100"
            )} 
            {...(disabled ? {} : listeners)}
            disabled={disabled}
          >
            <GripVertical className="h-5 w-5" />
            <span className="sr-only">Drag to reorder</span>
          </button>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <div className={cn('min-h-2 min-w-2 rounded-full', host.is_disabled ? 'bg-red-500' : 'bg-green-500')} />
              <div className="font-medium truncate">{host.remark ?? ''}</div>
            </div>
            <div className={cn('flex items-center gap-1', dir === 'rtl' && 'justify-start')}>
              <ChevronsLeftRightEllipsis className="h-4 w-4 text-muted-foreground" />
              <div dir="ltr" className="text-sm text-muted-foreground truncate">
                {Array.isArray(host.address) ? host.address[0] || '' : host.address ?? ''}:{host.port === null ? <Settings className="h-3 w-3 inline" /> : host.port}
              </div>
            </div>
            <div className="flex items-center gap-1 text-sm text-muted-foreground truncate">
              <CloudCog className="h-4 w-4" />
              <span>{t('inbound')}: </span>
              <span dir="ltr">{host.inbound_tag ?? ''}</span>
            </div>
          </div>
          <div onClick={(e) => e.stopPropagation()}>
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
                <Power className="h-4 w-4 mr-2" />
                {host?.is_disabled ? t('enable') : t('disable')}
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem
                onSelect={e => {
                  e.stopPropagation()
                  onEdit(host)
                }}
              >
                <Pencil className="h-4 w-4 mr-2" />
                {t('edit')}
              </DropdownMenuItem>
              <DropdownMenuItem
                onSelect={e => {
                  e.stopPropagation()
                  onDuplicate(host)
                }}
              >
                <Copy className="h-4 w-4 mr-2" />
                {t('duplicate')}
              </DropdownMenuItem>
              <DropdownMenuItem onSelect={handleDeleteClick} className="text-destructive">
                <Trash2 className="h-4 w-4 mr-2" />
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
