import PageHeader from '@/components/layout/page-header'
import { Separator } from '@/components/ui/separator'
import { Plus } from 'lucide-react'
import Groups from '@/features/groups/components/groups-list'
import { useAdmin } from '@/hooks/use-admin'
import { hasPermission } from '@/utils/rbac'
import { useCallback, useState } from 'react'
import { useCommandCreate } from '@/hooks/use-command-create'

export default function GroupsPage() {
  const { admin } = useAdmin()
  const canCreateGroups = hasPermission(admin, 'groups', 'create')
  const [isDialogOpen, setIsDialogOpen] = useState(false)
  const handleCreateGroup = useCallback(() => {
    if (!canCreateGroups) return
    setIsDialogOpen(true)
  }, [canCreateGroups])

  useCommandCreate('group', handleCreateGroup)

  return (
    <div className="flex w-full flex-col items-start gap-2">
      <div className="w-full transform-gpu">
        <PageHeader
          title="groups"
          description="manageGroups"
          buttonIcon={canCreateGroups ? Plus : undefined}
          buttonText={canCreateGroups ? 'createGroup' : undefined}
          onButtonClick={canCreateGroups ? handleCreateGroup : undefined}
        />
        <Separator />
      </div>

      <div className="w-full p-4">
        <div className="transform-gpu">
          <Groups isDialogOpen={isDialogOpen} onOpenChange={setIsDialogOpen} />
        </div>
      </div>
    </div>
  )
}
