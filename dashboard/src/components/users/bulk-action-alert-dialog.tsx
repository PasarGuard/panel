import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import useDirDetection from '@/hooks/use-dir-detection'
import { useTranslation } from 'react-i18next'

interface BulkActionAlertDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  description: string
  actionLabel: string
  onConfirm: () => void
  isPending?: boolean
  destructive?: boolean
}

export function BulkActionAlertDialog({
  open,
  onOpenChange,
  title,
  description,
  actionLabel,
  onConfirm,
  isPending = false,
  destructive = false,
}: BulkActionAlertDialogProps) {
  const { t } = useTranslation()
  const dir = useDirDetection()

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent dir={dir}>
        <AlertDialogHeader>
          <AlertDialogTitle>{title}</AlertDialogTitle>
          <AlertDialogDescription>{description}</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel onClick={() => onOpenChange(false)}>{t('usersTable.cancel')}</AlertDialogCancel>
          <AlertDialogAction variant={destructive ? 'destructive' : undefined} onClick={onConfirm} disabled={isPending}>
            {actionLabel}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}
