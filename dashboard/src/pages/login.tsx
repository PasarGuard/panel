import { Footer } from '@/components/layout/footer'
import { Language } from '@/components/common/language'
import { useTheme } from '@/app/providers/theme-provider'
import { ThemeToggle } from '@/components/common/theme-toggle'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { LoaderButton } from '@/components/ui/loader-button'
import { PasswordInput } from '@/components/ui/password-input'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useAdminMiniAppToken, useAdminToken, useCreateOwner, useDeleteOwner, useResetOwnerPassword, useUpgradeOwner } from '@/service/api'
import { $fetch } from '@/service/http'
import { removeAuthToken, setAuthToken } from '@/utils/authStorage'
import { queryClient } from '@/utils/query-client'
import { zodResolver } from '@hookform/resolvers/zod'
import { retrieveRawInitData } from '@telegram-apps/sdk'
import { ArrowLeft, CircleAlertIcon, KeyRound, LogInIcon, RotateCcw, ShieldCheck, Trash2, UserRoundKey } from 'lucide-react'
import { FC, useEffect, useMemo, useState } from 'react'
import { useForm } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { useLocation, useNavigate } from 'react-router'
import { toast } from 'sonner'
import { z } from 'zod'
import useDirDetection from '@/hooks/use-dir-detection'
import { passwordValidation } from '@/features/admins/forms/admin-form'

const schema = z.object({
  username: z.string().min(1, 'login.fieldRequired'),
  password: z.string().min(1, 'login.fieldRequired'),
})

type LoginSchema = z.infer<typeof schema>
type OwnerSetupMode = 'create' | 'upgrade' | 'reset' | 'delete'

const validateOwnerPassword = (password: string, ctx: z.RefinementCtx) => {
  const passwordResult = passwordValidation.safeParse(password)
  if (!passwordResult.success) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      path: ['password'],
      message: passwordResult.error.errors[0].message,
    })
    return false
  }
  return true
}

const ownerSetupSchema = z
  .object({
    mode: z.enum(['create', 'upgrade', 'reset', 'delete']),
    key: z.string().min(1, 'setup.keyRequired'),
    username: z.string(),
    password: z.string(),
    passwordConfirm: z.string(),
    deleteConfirm: z.string(),
  })
  .superRefine((values, ctx) => {
    if (values.mode === 'create' || values.mode === 'upgrade') {
      if (!values.username.trim()) {
        ctx.addIssue({ code: z.ZodIssueCode.custom, path: ['username'], message: 'setup.usernameRequired' })
      }
    }
    if (values.mode === 'create') {
      if (!values.password) {
        ctx.addIssue({ code: z.ZodIssueCode.custom, path: ['password'], message: 'setup.passwordRequired' })
      } else if (!validateOwnerPassword(values.password, ctx)) {
        return
      }
      if (values.password && values.password !== values.passwordConfirm) {
        ctx.addIssue({ code: z.ZodIssueCode.custom, path: ['passwordConfirm'], message: 'setup.passwordMismatch' })
      }
    }
    if (values.mode === 'reset') {
      if (!values.password) {
        ctx.addIssue({ code: z.ZodIssueCode.custom, path: ['password'], message: 'setup.passwordRequired' })
      } else if (!validateOwnerPassword(values.password, ctx)) {
        return
      }
      if (values.password && values.password !== values.passwordConfirm) {
        ctx.addIssue({ code: z.ZodIssueCode.custom, path: ['passwordConfirm'], message: 'setup.passwordMismatch' })
      }
    }
    if (values.mode === 'delete') {
      if (values.deleteConfirm !== 'DELETE') {
        ctx.addIssue({ code: z.ZodIssueCode.custom, path: ['deleteConfirm'], message: 'setup.deleteConfirmRequired' })
      }
    }
  })

type OwnerSetupSchema = z.infer<typeof ownerSetupSchema>

const formatApiDetail = (detail: unknown): string | undefined => {
  if (!detail) return undefined
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail
      .map(item => formatApiDetail(item))
      .filter(Boolean)
      .join('\n')
  }
  if (typeof detail === 'object') {
    return Object.entries(detail as Record<string, unknown>)
      .map(([key, value]) => {
        const message = formatApiDetail(value)
        return message ? `${key}: ${message}` : key
      })
      .join('\n')
  }
  return String(detail)
}

const getOwnerSetupErrorMessage = (error: any) => formatApiDetail(error?.data?.detail ?? error?.response?._data?.detail ?? error?.response?.data?.detail) || error?.message || 'Request failed'

export const Login: FC = () => {
  const navigate = useNavigate()
  const { t } = useTranslation()
  const dir = useDirDetection()
  const location = useLocation()
  const { resolvedTheme } = useTheme()
  const {
    register,
    formState: { errors },
    handleSubmit,
  } = useForm<LoginSchema>({
    defaultValues: {
      username: '',
      password: '',
    },
    resolver: zodResolver(schema),
  })

  useEffect(() => {
    // Cancel all ongoing queries first to stop any in-flight requests
    queryClient.cancelQueries()
    // Remove the auth token
    removeAuthToken()
    // Clear all React Query cache to ensure fresh state after logout
    queryClient.clear()
    if (location.pathname !== '/login') {
      navigate('/login', { replace: true })
    }
  }, [location.pathname, navigate])

  let isTelegram = false
  let initDataRaw = ''
  try {
    initDataRaw = retrieveRawInitData() || ''
    isTelegram = !!initDataRaw
  } catch (e) {
    isTelegram = false
    initDataRaw = ''
  }

  const {
    mutate: login,
    isPending: loading,
    error,
  } = useAdminToken({
    mutation: {
      onSuccess({ access_token }) {
        setAuthToken(access_token)
        navigate('/', { replace: true })
      },
    },
  })

  // MiniApp login mutation
  const { isPending: miniAppLoading, error: miniAppError } = useAdminMiniAppToken({
    mutation: {
      onSuccess(data: any) {
        // Assume data contains access_token
        if (data && data.access_token) {
          setAuthToken(data.access_token)
          navigate('/', { replace: true })
        }
      },
    },
  })

  const handleLogin = async (values: LoginSchema) => {
    if (isTelegram) {
      try {
        const data = await $fetch('/api/admin/miniapp/token', {
          method: 'POST',
          headers: {
            'x-telegram-authorization': initDataRaw,
          },
        })
        if (data && data.access_token) {
          setAuthToken(data.access_token)
          navigate('/', { replace: true })
        } else {
          throw new Error(data?.detail || 'Telegram login failed')
        }
      } catch (err: any) {
        alert(err.message || 'Telegram login failed')
      }
    } else {
      login({
        data: {
          ...values,
          grant_type: 'password',
        },
      })
    }
  }

  const [telegramLoading, setTelegramLoading] = useState(false)
  const [view, setView] = useState<'login' | 'setup'>('login')

  const {
    register: registerOwner,
    handleSubmit: handleOwnerSubmit,
    reset: resetOwnerForm,
    setValue: setOwnerValue,
    watch: watchOwner,
    clearErrors: clearOwnerErrors,
    formState: { errors: ownerErrors },
  } = useForm<OwnerSetupSchema>({
    defaultValues: {
      mode: 'create',
      key: '',
      username: '',
      password: '',
      passwordConfirm: '',
      deleteConfirm: '',
    },
    resolver: zodResolver(ownerSetupSchema),
  })

  const ownerSetupMode = watchOwner('mode')
  const ownerSetupKey = watchOwner('key')
  const ownerDeleteConfirm = watchOwner('deleteConfirm')

  const createOwner = useCreateOwner()
  const upgradeOwner = useUpgradeOwner()
  const resetOwner = useResetOwnerPassword()
  const deleteOwner = useDeleteOwner()
  const ownerSetupPending = createOwner.isPending || upgradeOwner.isPending || resetOwner.isPending || deleteOwner.isPending
  const ownerSetupSubmitDisabled = ownerSetupPending || (ownerSetupMode === 'delete' && (!ownerSetupKey.trim() || ownerDeleteConfirm !== 'DELETE'))

  const ownerSetupTitle = useMemo(() => {
    if (ownerSetupMode === 'upgrade') return t('setup.upgradeOwner', { defaultValue: 'Make admin owner' })
    if (ownerSetupMode === 'reset') return t('setup.resetOwner', { defaultValue: 'Reset owner password' })
    if (ownerSetupMode === 'delete') return t('setup.deleteOwner', { defaultValue: 'Delete owner' })
    return t('setup.createOwner', { defaultValue: 'Create owner' })
  }, [ownerSetupMode, t])

  const switchToSetup = () => {
    resetOwnerForm({ mode: 'create', key: '', username: '', password: '', passwordConfirm: '', deleteConfirm: '' })
    setView('setup')
  }

  const switchToLogin = () => {
    resetOwnerForm({ mode: 'create', key: '', username: '', password: '', passwordConfirm: '', deleteConfirm: '' })
    setView('login')
  }

  const handleOwnerSetupModeChange = (mode: string) => {
    resetOwnerForm({ mode: mode as OwnerSetupMode, key: '', username: '', password: '', passwordConfirm: '', deleteConfirm: '' })
    setOwnerValue('mode', mode as OwnerSetupMode)
    clearOwnerErrors()
  }

  const onOwnerSubmit = async (values: OwnerSetupSchema) => {
    try {
      if (values.mode === 'create') {
        await createOwner.mutateAsync({ data: { key: values.key, username: values.username, password: values.password } })
        toast.success(t('setup.ownerCreated', { defaultValue: 'Owner created successfully' }))
      } else if (values.mode === 'upgrade') {
        await upgradeOwner.mutateAsync({ data: { key: values.key, username: values.username } })
        toast.success(t('setup.ownerUpgraded', { defaultValue: 'Admin promoted to owner successfully' }))
      } else if (values.mode === 'reset') {
        await resetOwner.mutateAsync({ data: { key: values.key, password: values.password } })
        toast.success(t('setup.ownerReset', { defaultValue: 'Owner password reset successfully' }))
      } else {
        await deleteOwner.mutateAsync({ params: { key: values.key } })
        toast.success(t('setup.ownerDeleted', { defaultValue: 'Owner deleted successfully' }))
      }

      resetOwnerForm({ mode: 'create', key: '', username: '', password: '', passwordConfirm: '', deleteConfirm: '' })
      setView('login')
    } catch (err: any) {
      toast.error(t('error', { defaultValue: 'Error' }), { description: getOwnerSetupErrorMessage(err) })
    }
  }

  // Auto-login for Telegram MiniApp
  useEffect(() => {
    if (isTelegram) {
      // Try to expand for all platforms
      try {
        const win = window as any
        // Always try to expand the Telegram WebApp if possible
        if (win.Telegram && win.Telegram.WebApp && typeof win.Telegram.WebApp.expand === 'function') {
          win.Telegram.WebApp.expand()
        }
        // Send web_app_expand event for all platforms
        const expandEventData = JSON.stringify({
          eventType: 'web_app_expand',
          eventData: {},
        })
        // Web (iframe)
        if (window.parent && window.parent !== window) {
          window.parent.postMessage(expandEventData, 'https://web.telegram.org')
        }
        // Windows Phone
        if (typeof (window as any).external !== 'undefined' && typeof (window as any).external.notify === 'function') {
          ;(window as any).external.notify(expandEventData)
        }
        // Mobile/Desktop
        if (win.TelegramWebviewProxy && typeof win.TelegramWebviewProxy.postEvent === 'function') {
          win.TelegramWebviewProxy.postEvent('web_app_expand', '{}')
        }
      } catch (e) {
        // Ignore errors if not available
      }

      setTelegramLoading(true)
      $fetch('/api/admin/miniapp/token', {
        method: 'POST',
        headers: {
          'x-telegram-authorization': initDataRaw,
        },
      })
        .then((data: any) => {
          if (data && data.access_token) {
            setAuthToken(data.access_token)
            navigate('/', { replace: true })
          } else {
            throw new Error(data?.detail || 'Telegram login failed')
          }
        })
        .catch((err: any) => {
          alert(err.message || 'Telegram login failed')
        })
        .finally(() => {
          setTelegramLoading(false)
        })
    }
  }, [])

  return (
    <div className="flex min-h-screen w-full flex-col justify-between p-6">
      <div className="w-full">
        <div className="flex w-full items-center justify-between">
          <Language />
          <ThemeToggle />
        </div>
        <div className="flex w-full items-center justify-center">
          <div className="mt-6 w-full max-w-[340px]">
            <div className="flex flex-col items-center gap-2">
              <img src={resolvedTheme === 'dark' ? '/statics/favicon/logo.png' : '/statics/favicon/logo-dark.png'} alt="PasarGuard Logo" className="h-20 w-20 object-contain" />
              <span className="text-2xl font-semibold">{view === 'login' ? t('login.loginYourAccount') : t('setup.ownerAccess', { defaultValue: 'Owner access' })}</span>
              <span className="text-center text-gray-600 dark:text-gray-400">
                {view === 'login'
                  ? t('login.welcomeBack')
                  : t('setup.ownerAccessDescription', {
                      defaultValue: 'Use a temporary setup key to create, promote, reset, or remove the owner account.',
                    })}
              </span>
            </div>

            <div className="mx-auto w-full max-w-[300px] pt-4">
              {view === 'login' ? (
                <form onSubmit={handleSubmit(handleLogin)} autoComplete="on">
                  <div className="mt-4 flex flex-col gap-y-2">
                    <Input className="py-5" placeholder={t('username')} autoComplete="username" {...register('username')} error={t(errors?.username?.message as string)} />
                    <PasswordInput className="py-5" placeholder={t('password')} allowBrowserSave {...register('password')} error={t(errors?.password?.message as string)} />
                    {((error && error.data) || (miniAppError && miniAppError.data)) && (
                      <Alert className="mt-2" variant="destructive">
                        <CircleAlertIcon size="18px" />
                        <AlertDescription>{getOwnerSetupErrorMessage(error || miniAppError)}</AlertDescription>
                      </Alert>
                    )}
                    <div className="mt-2 flex flex-col gap-2">
                      <LoaderButton isLoading={loading || miniAppLoading || telegramLoading} type="submit" className="flex w-full items-center gap-2">
                        <LogInIcon size="18px" />
                        <span>{t('login')}</span>
                      </LoaderButton>
                      <Button type="button" variant="outline" className="flex w-full items-center gap-2" onClick={switchToSetup}>
                        <KeyRound className="h-4 w-4" />
                        <span>{t('setup.ownerAccess', { defaultValue: 'Owner access' })}</span>
                      </Button>
                    </div>
                  </div>
                </form>
              ) : (
                <form className="mt-4 flex flex-col gap-2" onSubmit={handleOwnerSubmit(onOwnerSubmit)} autoComplete="off">
                  <input type="hidden" {...registerOwner('mode')} />
                  <Tabs value={ownerSetupMode} onValueChange={handleOwnerSetupModeChange} className="w-full">
                    <TabsList className="grid h-auto w-full grid-cols-2 gap-1 p-1">
                      <TabsTrigger value="create" className="h-8 gap-1 px-2 text-xs">
                        <ShieldCheck className="h-3.5 w-3.5 shrink-0" />
                        <span className="truncate">{t('setup.createOwnerShort', { defaultValue: 'Create' })}</span>
                      </TabsTrigger>
                      <TabsTrigger value="upgrade" className="h-8 gap-1 px-2 text-xs">
                        <UserRoundKey className="h-3.5 w-3.5 shrink-0" />
                        <span className="truncate">{t('setup.upgradeOwnerShort', { defaultValue: 'Make owner' })}</span>
                      </TabsTrigger>
                      <TabsTrigger value="reset" className="h-8 gap-1 px-2 text-xs">
                        <RotateCcw className="h-3.5 w-3.5 shrink-0" />
                        <span className="truncate">{t('setup.resetOwnerShort', { defaultValue: 'Reset' })}</span>
                      </TabsTrigger>
                      <TabsTrigger value="delete" className="h-8 gap-1 px-2 text-xs">
                        <Trash2 className="h-3.5 w-3.5 shrink-0" />
                        <span className="truncate">{t('setup.deleteOwnerShort', { defaultValue: 'Delete' })}</span>
                      </TabsTrigger>
                    </TabsList>
                  </Tabs>

                  <Input
                    className="py-5"
                    placeholder={t('setup.tempKey', { defaultValue: 'Temp key' })}
                    autoComplete="one-time-code"
                    {...registerOwner('key')}
                    error={t(ownerErrors?.key?.message as string)}
                  />

                  {(ownerSetupMode === 'create' || ownerSetupMode === 'upgrade') && (
                    <Input
                      className="py-5"
                      placeholder={t('username', { defaultValue: 'Username' })}
                      autoComplete="username"
                      {...registerOwner('username')}
                      error={t(ownerErrors?.username?.message as string)}
                    />
                  )}

                  {ownerSetupMode === 'create' && (
                    <>
                      <PasswordInput
                        className="py-5"
                        placeholder={t('password', { defaultValue: 'Password' })}
                        autoComplete="new-password"
                        {...registerOwner('password')}
                        error={t(ownerErrors?.password?.message as string)}
                      />
                      <PasswordInput
                        className="py-5"
                        placeholder={t('admins.passwordConfirm', { defaultValue: 'Confirm password' })}
                        autoComplete="new-password"
                        {...registerOwner('passwordConfirm')}
                        error={t(ownerErrors?.passwordConfirm?.message as string)}
                      />
                    </>
                  )}

                  {ownerSetupMode === 'reset' && (
                    <>
                      <PasswordInput
                        className="py-5"
                        placeholder={t('password', { defaultValue: 'Password' })}
                        autoComplete="new-password"
                        {...registerOwner('password')}
                        error={t(ownerErrors?.password?.message as string)}
                      />
                      <PasswordInput
                        className="py-5"
                        placeholder={t('admins.passwordConfirm', { defaultValue: 'Confirm password' })}
                        autoComplete="new-password"
                        {...registerOwner('passwordConfirm')}
                        error={t(ownerErrors?.passwordConfirm?.message as string)}
                      />
                    </>
                  )}

                  {ownerSetupMode === 'delete' && (
                    <>
                      <Input
                        className="py-5"
                        placeholder={t('setup.deleteConfirm', { defaultValue: 'Type DELETE to confirm' })}
                        {...registerOwner('deleteConfirm')}
                        error={t(ownerErrors?.deleteConfirm?.message as string)}
                      />
                      <Alert variant="destructive" className="mt-2 py-5">
                        <CircleAlertIcon size="18px" />
                        <AlertDescription className="leading-6">
                          {t('setup.deleteWarning', {
                            defaultValue: 'This action cannot be undone. The owner account will be permanently removed.',
                          })}
                        </AlertDescription>
                      </Alert>
                    </>
                  )}

                  <div className="mt-2 flex flex-col gap-2">
                    <Button
                      type="submit"
                      variant={ownerSetupMode === 'delete' ? 'destructive' : 'default'}
                      isLoading={ownerSetupPending}
                      loadingText={ownerSetupTitle}
                      disabled={ownerSetupSubmitDisabled}
                      className="w-full"
                    >
                      {ownerSetupTitle}
                    </Button>
                    <Button type="button" variant="ghost" className="flex w-full items-center gap-2" onClick={switchToLogin}>
                      <ArrowLeft className={dir === 'rtl' ? 'h-4 w-4 scale-x-[-1]' : 'h-4 w-4'} />
                      <span>{t('login.backToLogin', { defaultValue: 'Back to login' })}</span>
                    </Button>
                  </div>
                </form>
              )}
            </div>
          </div>
        </div>
      </div>
      <Footer />
    </div>
  )
}

export default Login
