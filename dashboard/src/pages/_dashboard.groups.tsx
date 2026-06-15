import PageHeader from '@/components/layout/page-header'
import { Separator } from '@/components/ui/separator'
import { Plus } from 'lucide-react'
import Groups from '@/features/groups/components/groups-list'
import { useAdmin } from '@/hooks/use-admin'
import { hasPermission } from '@/utils/rbac'
import { useState } from 'react'

export default function GroupsPage() {
  const { admin } = useAdmin()
  const canCreateGroups = hasPermission(admin, 'groups', 'create')
  const [isDialogOpen, setIsDialogOpen] = useState(false)
  const handleCreateGroup = () => {
    if (!canCreateGroups) return
    setIsDialogOpen(true)
  }

  return (
    <div className="flex w-full flex-col items-start gap-2">
      <div className="animate-fade-in w-full transform-gpu" style={{ animationDuration: '400ms' }}>
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
        <div className="animate-slide-up transform-gpu" style={{ animationDuration: '500ms', animationDelay: '100ms', animationFillMode: 'both' }}>
          <Groups isDialogOpen={isDialogOpen} onOpenChange={setIsDialogOpen} />
        </div>
      </div>
    </div>
  )
}
