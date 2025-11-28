import PageHeader from '@/components/layout/page-header'
import { Separator } from '@/components/ui/separator'
import { Plus } from 'lucide-react'
import Groups from '@/components/groups/groups-list'
import { useState } from 'react'

export default function GroupsPage() {
  const [isDialogOpen, setIsDialogOpen] = useState(false)

  return (
    <div className="flex w-full flex-col items-start gap-2">
      <div className="w-full transform-gpu animate-fade-in" style={{ animationDuration: '400ms' }}>
        <PageHeader title="groups" description="manageGroups" buttonIcon={Plus} buttonText="createGroup" onButtonClick={() => setIsDialogOpen(true)} />
        <Separator />
      </div>

      <div className="w-full p-4">
        <div className="transform-gpu animate-slide-up" style={{ animationDuration: '500ms', animationDelay: '100ms', animationFillMode: 'both' }}>
          <Groups isDialogOpen={isDialogOpen} onOpenChange={setIsDialogOpen} />
        </div>
      </div>
    </div>
  )
}
