import { Button } from '@/components/ui/button'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Pencil, Trash2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'

interface NodeUserLimit {
  id: number
  userId: number
  nodeId: number
  dataLimit: number
  username?: string
  nodeName?: string
}

interface NodeUserLimitsTableProps {
  limits: NodeUserLimit[]
  onEdit?: (limit: NodeUserLimit) => void
  onDelete?: (limitId: number) => void
  isLoading?: boolean
  showUser?: boolean
  showNode?: boolean
}

function bytesToGB(bytes: number): string {
  if (bytes === 0) return '∞'
  return (bytes / 1073741824).toFixed(2)
}

export function NodeUserLimitsTable({ limits, onEdit, onDelete, isLoading = false, showUser = true, showNode = true }: NodeUserLimitsTableProps) {
  const { t } = useTranslation()

  if (isLoading) {
    return (
      <div className="flex items-center justify-center p-8">
        <div className="text-muted-foreground">{t('loading')}</div>
      </div>
    )
  }

  if (limits.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center p-8 text-center">
        <p className="text-muted-foreground">{t('nodes.userLimits.table.noLimits')}</p>
        <p className="mt-1 text-sm text-muted-foreground">{t('nodes.userLimits.table.noLimitsHint')}</p>
      </div>
    )
  }

  return (
    <div className="rounded-md border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>{t('nodes.userLimits.table.id')}</TableHead>
            {showUser && <TableHead>{t('nodes.userLimits.table.user')}</TableHead>}
            {showNode && <TableHead>{t('nodes.userLimits.table.node')}</TableHead>}
            <TableHead>{t('nodes.userLimits.table.dataLimit')}</TableHead>
            <TableHead className="text-right">{t('actions')}</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {limits.map(limit => (
            <TableRow key={limit.id}>
              <TableCell className="font-medium">#{limit.id}</TableCell>
              {showUser && <TableCell>{limit.username || `User ID: ${limit.userId}`}</TableCell>}
              {showNode && <TableCell>{limit.nodeName || `Node ID: ${limit.nodeId}`}</TableCell>}
              <TableCell>
                <span className="font-mono">{bytesToGB(limit.dataLimit)} GB</span>
              </TableCell>
              <TableCell className="text-right">
                <div className="flex justify-end gap-2">
                  {onEdit && (
                    <Button variant="ghost" size="icon" onClick={() => onEdit(limit)} title={t('edit')}>
                      <Pencil className="h-4 w-4" />
                    </Button>
                  )}
                  {onDelete && (
                    <Button variant="ghost" size="icon" onClick={() => onDelete(limit.id)} title={t('delete')}>
                      <Trash2 className="h-4 w-4 text-destructive" />
                    </Button>
                  )}
                </div>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}
