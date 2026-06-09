import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Plus } from 'lucide-react'
import { useForm } from 'react-hook-form'
import PageHeader from '@/components/layout/page-header'
import { Separator } from '@/components/ui/separator'
import { toast } from 'sonner'
import AdminsTable from '@/features/admins/components/admins-table'
import AdminModal from '@/features/admins/dialogs/admin-modal'
import { adminFormDefaultValues, adminFormSchema, adminPermissionOverridesDefaultValues, type AdminFormValuesInput } from '@/features/admins/forms/admin-form'
import { useModifyAdminById, useRemoveAdminById, useResetAdminUsageById } from '@/service/api'
import type { AdminDetails } from '@/service/api'
import AdminsStatistics from '@/features/admins/components/admin-statistics'
import { zodResolver } from '@hookform/resolvers/zod'
import useDynamicErrorHandler from '@/hooks/use-dynamic-errors'
import { removeAdminFromAdminsCache, upsertAdminInAdminsCache } from '@/utils/adminsCache'
import { useQueryClient } from '@tanstack/react-query'
import { useGetRolesSimple } from '@/service/api'
import { useAdmin } from '@/hooks/use-admin'
import { hasPermission } from '@/utils/rbac'

export default function AdminsPage() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const { admin: currentAdmin } = useAdmin()
  const canCreateAdmins = hasPermission(currentAdmin, 'admins', 'create')
  const canUpdateAdmins = hasPermission(currentAdmin, 'admins', 'update')
  const [editingAdmin, setEditingAdmin] = useState<Partial<AdminDetails> | null>(null)
  const [isDialogOpen, setIsDialogOpen] = useState(false)
  const [adminCounts, setAdminCounts] = useState<{ total: number; active: number; disabled: number; limited: number } | null>(null)
  const form = useForm<AdminFormValuesInput>({
    resolver: zodResolver(adminFormSchema),
    defaultValues: adminFormDefaultValues,
  })

  const removeAdminMutation = useRemoveAdminById()
  const modifyAdminMutation = useModifyAdminById()
  const rolesQuery = useGetRolesSimple({ query: { enabled: canUpdateAdmins } })
  const resetUsageMutation = useResetAdminUsageById()
  const handleError = useDynamicErrorHandler()

  const getAdminId = (admin: AdminDetails) => {
    if (admin.id == null) {
      toast.error(t('error', { defaultValue: 'Error' }), {
        description: t('admins.missingId', {
          name: admin.username,
          defaultValue: 'Admin "{name}" is missing an id in the current response.',
        }),
      })
      return null
    }

    return admin.id
  }

  const isAdminDisabled = (admin: AdminDetails) => (admin.status || (admin.is_disabled ? 'disabled' : 'active')) === 'disabled'

  const handleDelete = async (admin: AdminDetails) => {
    const adminId = getAdminId(admin)
    if (adminId == null) return

    try {
      await removeAdminMutation.mutateAsync({
        adminId,
      })
      toast.success(t('success', { defaultValue: 'Success' }), {
        description: t('admins.deleteSuccess', {
          name: admin.username,
          defaultValue: 'Admin «{{name}}» has been deleted successfully',
        }),
      })
      removeAdminFromAdminsCache(queryClient, adminId)
    } catch (error) {
      handleError({
        error,
        fields: [],
        form,
        contextKey: 'admins',
      })
    }
  }

  const handleToggleStatus = async (admin: AdminDetails) => {
    const adminId = getAdminId(admin)
    if (adminId == null) return

    try {
      const disabled = isAdminDisabled(admin)
      const updatedAdmin = await modifyAdminMutation.mutateAsync({
        adminId,
        data: {
          status: disabled ? 'active' : 'disabled',
          discord_webhook: admin.discord_webhook,
          sub_template: admin.sub_template,
          telegram_id: admin.telegram_id,
          support_url: admin.support_url,
          profile_title: admin.profile_title,
          sub_domain: admin.sub_domain,
          note: admin.note,
        },
      })
      upsertAdminInAdminsCache(queryClient, updatedAdmin, { allowInsert: true })

      toast.success(t('success', { defaultValue: 'Success' }), {
        description: t(disabled ? 'admins.enableSuccess' : 'admins.disableSuccess', {
          name: admin.username,
          defaultValue: `Admin "{name}" has been ${disabled ? 'enabled' : 'disabled'} successfully`,
        }),
      })
    } catch (error: any) {
      const status = error?.status ?? error?.response?.status
      const backendDetail = error?.data?.detail ?? error?.response?._data?.detail ?? error?.response?.data?.detail
      const disabled = isAdminDisabled(admin)
      const defaultDescription = t(disabled ? 'admins.enableFailed' : 'admins.disableFailed', {
        name: admin.username,
        defaultValue: `Failed to ${disabled ? 'enable' : 'disable'} admin "{name}"`,
      })

      toast.error(t('error', { defaultValue: 'Error' }), {
        description: status === 403 && typeof backendDetail === 'string' && backendDetail.trim().length > 0 ? backendDetail : defaultDescription,
      })
    }
  }

  const getRoleIdForAdmin = (admin: AdminDetails) => {
    const roleName = admin.role?.name
    if (admin.role?.is_owner || roleName === 'owner') return 1
    if (admin.role?.id != null) return admin.role.id
    const roleId = rolesQuery.data?.roles.find(role => role.name === roleName)?.id
    if (roleId != null) return roleId
    if (roleName === 'administrator') return 2
    return 3
  }

  const handleEdit = (admin: AdminDetails) => {
    if (!canUpdateAdmins) return

    const roleId = getRoleIdForAdmin(admin)
    setEditingAdmin(admin)
    form.reset({
      username: admin.username,
      role_id: roleId,
      status: (admin.status || (admin.is_disabled ? 'disabled' : 'active')) === 'disabled' ? 'disabled' : 'active',
      data_limit: admin.data_limit ?? null,
      is_disabled: admin.status === 'disabled' || admin.is_disabled || undefined,
      discord_webhook: admin.discord_webhook || '',
      sub_template: admin.sub_template || '',
      telegram_id: admin.telegram_id || undefined,
      support_url: admin.support_url || '',
      profile_title: admin.profile_title || '',
      sub_domain: admin.sub_domain || '',
      note: admin.note || '',
      password: undefined,
      permission_overrides: {
        ...adminPermissionOverridesDefaultValues,
        ...(admin.permission_overrides
          ? (() => {
              const { expire_min, expire_max, ...rest } = admin.permission_overrides
              return {
                ...rest,
                expire_days_min: expire_min == null ? null : Math.round(expire_min / 86_400),
                expire_days_max: expire_max == null ? null : Math.round(expire_max / 86_400),
              }
            })()
          : {}),
      },
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

  const resetUsage = async (admin: AdminDetails) => {
    const adminId = getAdminId(admin)
    if (adminId == null) return

    try {
      const updatedAdmin = await resetUsageMutation.mutateAsync({
        adminId,
      })
      upsertAdminInAdminsCache(queryClient, updatedAdmin, { allowInsert: true })

      toast.success(t('success', { defaultValue: 'Success' }), {
        description: t('admins.resetUsageSuccess', {
          name: admin.username,
          defaultValue: `Admin "{name}" user usage has been reset successfully`,
        }),
      })
    } catch (error) {
      toast.error(t('error', { defaultValue: 'Error' }), {
        description: t('admins.resetUsageFailed', {
          name: admin.username,
          defaultValue: `Failed to reset admin "{name}" user usage`,
        }),
      })
    }
  }

  return (
    <div className="flex w-full flex-col items-start gap-2">
      <div className="animate-fade-in w-full transform-gpu" style={{ animationDuration: '400ms' }}>
        <PageHeader
          title="admins.title"
          description="admins.description"
          buttonIcon={Plus}
          buttonText={canCreateAdmins ? 'admins.createAdmin' : undefined}
          onButtonClick={
            canCreateAdmins
              ? () => {
                  setEditingAdmin(null)
                  form.reset(adminFormDefaultValues)
                  setIsDialogOpen(true)
                }
              : undefined
          }
        />
        <Separator />
      </div>

      <div className="w-full px-4 pt-2">
        <div className="animate-slide-up transform-gpu" style={{ animationDuration: '500ms', animationDelay: '100ms', animationFillMode: 'both' }}>
          <AdminsStatistics counts={adminCounts} />
        </div>

        <div className="animate-slide-up transform-gpu" style={{ animationDuration: '500ms', animationDelay: '250ms', animationFillMode: 'both' }}>
          <AdminsTable onEdit={handleEdit} onDelete={handleDelete} onToggleStatus={handleToggleStatus} onResetUsage={resetUsage} onTotalAdminsChange={setAdminCounts} />
        </div>

        {(canCreateAdmins || canUpdateAdmins) && (
          <AdminModal
            isDialogOpen={isDialogOpen}
            onOpenChange={open => {
              if (open && editingAdmin && !canUpdateAdmins) return
              if (open && !editingAdmin && !canCreateAdmins) return
              if (!open) {
                setEditingAdmin(null)
                form.reset(adminFormDefaultValues)
              }
              setIsDialogOpen(open)
            }}
            form={form}
            editingAdmin={!!editingAdmin}
            editingAdminId={editingAdmin?.id}
          />
        )}
      </div>
    </div>
  )
}
