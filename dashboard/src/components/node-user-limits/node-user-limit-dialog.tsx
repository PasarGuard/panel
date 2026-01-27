import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

interface NodeUserLimitDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onSubmit: (data: { userId: number; nodeId: number; dataLimitGB: number }) => void
  users?: Array<{ id: number; username: string }>
  nodes?: Array<{ id: number; name: string }>
  initialData?: { userId?: number; nodeId?: number; dataLimitGB?: number }
  mode?: 'create' | 'edit'
}

export function NodeUserLimitDialog({ open, onOpenChange, onSubmit, users = [], nodes = [], initialData, mode = 'create' }: NodeUserLimitDialogProps) {
  const { t } = useTranslation()
  const [userId, setUserId] = useState<number | undefined>(initialData?.userId)
  const [nodeId, setNodeId] = useState<number | undefined>(initialData?.nodeId)
  const [dataLimitGB, setDataLimitGB] = useState<string>(initialData?.dataLimitGB?.toString() || '')

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!userId || !nodeId || !dataLimitGB) return

    onSubmit({
      userId,
      nodeId,
      dataLimitGB: parseFloat(dataLimitGB),
    })

    // Reset form
    if (mode === 'create') {
      setUserId(undefined)
      setNodeId(undefined)
      setDataLimitGB('')
    }
    onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[425px]">
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>{mode === 'create' ? t('nodes.userLimits.dialog.createTitle') : t('nodes.userLimits.dialog.editTitle')}</DialogTitle>
            <DialogDescription>{t('nodes.userLimits.dialog.description')}</DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="grid gap-2">
              <Label htmlFor="user">{t('nodes.userLimits.dialog.user')}</Label>
              <Select value={userId?.toString()} onValueChange={value => setUserId(parseInt(value))} disabled={mode === 'edit'}>
                <SelectTrigger id="user">
                  <SelectValue placeholder={t('nodes.userLimits.dialog.selectUser')} />
                </SelectTrigger>
                <SelectContent>
                  {users.map(user => (
                    <SelectItem key={user.id} value={user.id.toString()}>
                      {user.username}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="grid gap-2">
              <Label htmlFor="node">{t('nodes.userLimits.dialog.node')}</Label>
              <Select value={nodeId?.toString()} onValueChange={value => setNodeId(parseInt(value))} disabled={mode === 'edit'}>
                <SelectTrigger id="node">
                  <SelectValue placeholder={t('nodes.userLimits.dialog.selectNode')} />
                </SelectTrigger>
                <SelectContent>
                  {nodes.map(node => (
                    <SelectItem key={node.id} value={node.id.toString()}>
                      {node.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="grid gap-2">
              <Label htmlFor="dataLimit">{t('nodes.userLimits.dialog.dataLimit')} (GB)</Label>
              <Input id="dataLimit" type="number" step="0.01" min="0" placeholder="10" value={dataLimitGB} onChange={e => setDataLimitGB(e.target.value)} required />
              <p className="text-xs text-muted-foreground">{t('nodes.userLimits.dialog.dataLimitHint')}</p>
            </div>
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              {t('cancel')}
            </Button>
            <Button type="submit" disabled={!userId || !nodeId || !dataLimitGB}>
              {mode === 'create' ? t('create') : t('save')}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
