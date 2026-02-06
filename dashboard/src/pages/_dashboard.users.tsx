import PageHeader from '@/components/layout/page-header'
import { Separator } from '@/components/ui/separator'
import { type UseEditFormValues, type UseFormValues, getDefaultUserForm } from '@/components/forms/user-form'
import UsersTable from '@/components/users/users-table'
import UsersStatistics from '@/components/users/users-statistics'
import { Plus } from 'lucide-react'
import UserModal from '@/components/dialogs/user-modal'
import { useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useForm } from 'react-hook-form'

const Users = () => {
  const [isUserModalOpen, setUserModalOpen] = useState(false)
  const queryClient = useQueryClient()
  const userForm = useForm<UseFormValues | UseEditFormValues>({
    defaultValues: getDefaultUserForm,
  })

  // Configure global refetch for all user data
  const refreshAllUserData = () => {
    // Invalidate all relevant queries
    queryClient.invalidateQueries({ queryKey: ['getUsers'] })
    queryClient.invalidateQueries({ queryKey: ['getUsersUsage'] })
    queryClient.invalidateQueries({ queryKey: ['/api/users/'] })
  }

  const handleCreateUser = () => {
    userForm.reset()
    setUserModalOpen(true)
  }

  return (
    <div className="flex w-full flex-col items-start gap-2">
      <div className="w-full transform-gpu animate-fade-in" style={{ animationDuration: '400ms' }}>
        <PageHeader title="users" description="manageAccounts" buttonIcon={Plus} buttonText="createUser" onButtonClick={handleCreateUser} />
        <Separator />
      </div>

      <div className="w-full px-4 pt-2">
        <div className="transform-gpu animate-slide-up" style={{ animationDuration: '500ms', animationDelay: '100ms', animationFillMode: 'both' }}>
          <UsersStatistics />
        </div>

        <div className="transform-gpu animate-slide-up" style={{ animationDuration: '500ms', animationDelay: '250ms', animationFillMode: 'both' }}>
          <UsersTable />
        </div>
      </div>

      <UserModal isDialogOpen={isUserModalOpen} onOpenChange={setUserModalOpen} form={userForm} editingUser={false} onSuccessCallback={() => refreshAllUserData()} />
    </div>
  )
}

export default Users

