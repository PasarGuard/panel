import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Plus } from 'lucide-react'
import { useForm } from 'react-hook-form'
import PageHeader from '@/components/layout/page-header'
import { Separator } from '@/components/ui/separator'
import { toast } from 'sonner'
import AdminsTable from '@/components/admins/admins-table'
import AdminModal from '@/components/dialogs/admin-modal'
import { adminFormDefaultValues, adminFormSchema, type AdminFormValuesInput } from '@/components/forms/admin-form'
import { useActivateAllDisabledUsers, useDisableAllActiveUsers, useModifyAdmin, useRemoveAdmin, useResetAdminUsage } from '@/service/api'
import type { AdminDetails } from '@/service/api'
import AdminsStatistics from '@/components/admins/admin-statistics'
import { zodResolver } from '@hookform/resolvers/zod'
import useDynamicErrorHandler from '@/hooks/use-dynamic-errors'
import { removeAdminFromAdminsCache, upsertAdminInAdminsCache } from '@/utils/adminsCache'
import { useQueryClient } from '@tanstack/react-query'

export default function AdminsPage() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [editingAdmin, setEditingAdmin] = useState<Partial<AdminDetails> | null>(null)
  const [isDialogOpen, setIsDialogOpen] = useState(false)
  const [adminCounts, setAdminCounts] = useState<{ total: number; active: number; disabled: number } | null>(null)
  const form = useForm<AdminFormValuesInput>({
    resolver: zodResolver(adminFormSchema),
    defaultValues: adminFormDefaultValues,
  })

  const removeAdminMutation = useRemoveAdmin()
  const modifyAdminMutation = useModifyAdmin()
  const modifyDisableAllAdminUsers = useDisableAllActiveUsers()
  const modifyActivateAllAdminUsers = useActivateAllDisabledUsers()
  const resetUsageMutation = useResetAdminUsage()
  const handleError = useDynamicErrorHandler()
  const handleDelete = async (admin: AdminDetails) => {
    try {
      await removeAdminMutation.mutateAsync({
        username: admin.username,
      })
      toast.success(t('success', { defaultValue: 'Success' }), {
        description: t('admins.deleteSuccess', {
          name: admin.username,
          defaultValue: 'Admin «{{name}}» has been deleted successfully',
        }),
      })
      removeAdminFromAdminsCache(queryClient, admin.username)
    } catch (error) {
      handleError({
        error,
        fields: [],
        form,
        contextKey: 'admins',
      })
    }
  }

  const handleToggleStatus = async (admin: AdminDetails, checked: boolean) => {
    try {
      if (!admin.is_disabled && checked) {
        await modifyDisableAllAdminUsers.mutateAsync({
          username: admin.username,
        })
      }

      if (admin.is_disabled && checked) {
        await modifyActivateAllAdminUsers.mutateAsync({
          username: admin.username,
        })
      }
      const updatedAdmin = await modifyAdminMutation.mutateAsync({
        username: admin.username,
        data: {
          is_sudo: admin.is_sudo,
          is_disabled: !admin.is_disabled,
          discord_webhook: admin.discord_webhook,
          sub_template: admin.sub_template,
          telegram_id: admin.telegram_id,
          support_url: admin.support_url,
          profile_title: admin.profile_title,
          sub_domain: admin.sub_domain,
          note: admin.note,
          discord_id: admin.discord_id,
        },
      })
      upsertAdminInAdminsCache(queryClient, updatedAdmin, { allowInsert: true })

      toast.success(t('success', { defaultValue: 'Success' }), {
        description: t(admin.is_disabled ? 'admins.enableSuccess' : 'admins.disableSuccess', {
          name: admin.username,
          defaultValue: `Admin "{name}" has been ${admin.is_disabled ? 'enabled' : 'disabled'} successfully`,
        }),
      })

    } catch (error: any) {
      const status = error?.status ?? error?.response?.status
      const backendDetail = error?.data?.detail ?? error?.response?._data?.detail ?? error?.response?.data?.detail
      const defaultDescription = t(admin.is_disabled ? 'admins.enableFailed' : 'admins.disableFailed', {
        name: admin.username,
        defaultValue: `Failed to ${admin.is_disabled ? 'enable' : 'disable'} admin "{name}"`,
      })

      toast.error(t('error', { defaultValue: 'Error' }), {
        description: status === 403 && typeof backendDetail === 'string' && backendDetail.trim().length > 0 ? backendDetail : defaultDescription,
      })
    }
  }

  const handleEdit = (admin: AdminDetails) => {
    setEditingAdmin(admin)
    form.reset({
      username: admin.username,
      is_sudo: admin.is_sudo,
      is_disabled: admin.is_disabled || undefined,
      discord_webhook: admin.discord_webhook || '',
      sub_template: admin.sub_template || '',
      telegram_id: admin.telegram_id || undefined,
      support_url: admin.support_url || '',
      profile_title: admin.profile_title || '',
      sub_domain: admin.sub_domain || '',
      note: admin.note || '',
      discord_id: admin.discord_id || undefined,
      password: undefined,
      notification_enable: admin.notification_enable || {
        create: false,
        modify: false,
        delete: false,
        status_change: false,
        reset_data_usage: false,
        data_reset_by_next: false,
        subscription_revoked: false,
      },
    })
    setIsDialogOpen(true)
  }

  const resetUsage = async (adminUsername: string) => {
    try {
      const updatedAdmin = await resetUsageMutation.mutateAsync({
        username: adminUsername,
      })
      upsertAdminInAdminsCache(queryClient, updatedAdmin, { allowInsert: true })

      toast.success(t('success', { defaultValue: 'Success' }), {
        description: t('admins.resetUsageSuccess', {
          name: adminUsername,
          defaultValue: `Admin "{name}" user usage has been reset successfully`,
        }),
      })

    } catch (error) {
      toast.error(t('error', { defaultValue: 'Error' }), {
        description: t('admins.resetUsageFailed', {
          name: adminUsername,
          defaultValue: `Failed to reset admin "{name}" user usage`,
        }),
      })
    }
  }

  return (
    <div className="flex w-full flex-col items-start gap-2">
      <div className="w-full transform-gpu animate-fade-in" style={{ animationDuration: '400ms' }}>
        <PageHeader
          title="admins.title"
          description="admins.description"
          buttonIcon={Plus}
          buttonText="admins.createAdmin"
          onButtonClick={() => {
            setEditingAdmin(null)
            form.reset(adminFormDefaultValues)
            setIsDialogOpen(true)
          }}
        />
        <Separator />
      </div>

      <div className="w-full px-4 pt-2">
        <div className="transform-gpu animate-slide-up" style={{ animationDuration: '500ms', animationDelay: '100ms', animationFillMode: 'both' }}>
          <AdminsStatistics counts={adminCounts} />
        </div>

        <div className="transform-gpu animate-slide-up" style={{ animationDuration: '500ms', animationDelay: '250ms', animationFillMode: 'both' }}>
          <AdminsTable onEdit={handleEdit} onDelete={handleDelete} onToggleStatus={handleToggleStatus} onResetUsage={resetUsage} onTotalAdminsChange={setAdminCounts} />
        </div>

        <AdminModal
          isDialogOpen={isDialogOpen}
          onOpenChange={open => {
            if (!open) {
              setEditingAdmin(null)
              form.reset(adminFormDefaultValues)
            }
            setIsDialogOpen(open)
          }}
          form={form}
          editingAdmin={!!editingAdmin}
          editingAdminUserName={editingAdmin?.username || ''}
        />
      </div>
    </div>
  )
}
