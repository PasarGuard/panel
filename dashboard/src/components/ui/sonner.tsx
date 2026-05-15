import { useTheme } from '@/app/providers/theme-provider'
import { Toaster as Sonner } from 'sonner'
import useDirDetection from '@/hooks/use-dir-detection'
import type { CSSProperties } from 'react'

type ToasterProps = React.ComponentProps<typeof Sonner>

const Toaster = ({ ...props }: ToasterProps) => {
  const { resolvedTheme, radius } = useTheme()
  const dir = useDirDetection()

  return (
    <Sonner
      theme={resolvedTheme as ToasterProps['theme']}
      className="toaster group font-body"
      dir={dir}
      style={{
        '--normal-bg': 'hsl(var(--background))',
        '--normal-border': 'hsl(var(--border))',
        '--normal-text': 'hsl(var(--foreground))',
        '--normal-bg-hover': 'hsl(var(--accent))',
        '--normal-border-hover': 'hsl(var(--border))',
        ...props.style,
      } as CSSProperties}
      toastOptions={{
        style: { borderRadius: radius },
        classNames: {
          toast: 'group font-body toast group-[.toaster]:bg-background group-[.toaster]:text-foreground group-[.toaster]:border-border group-[.toaster]:shadow-lg',
          description: 'group-[.toast]:text-muted-foreground',
          actionButton: 'group-[.toast]:bg-primary group-[.toast]:text-primary-foreground',
          cancelButton: 'group-[.toast]:bg-muted group-[.toast]:text-muted-foreground',
          success:
            'group-[.toast]:bg-[#f0fdf4] group-[.toast]:text-[#14532d] group-[.toast]:border-[#bbf7d0] dark:group-[.toast]:bg-[#052e16] dark:group-[.toast]:text-[#f0fdf4] dark:group-[.toast]:border-[#166534]',
          error:
            'group-[.toast]:bg-[#fef2f2] group-[.toast]:text-[#7f1d1d] group-[.toast]:border-[#fecaca] dark:group-[.toast]:bg-[#450a0a] dark:group-[.toast]:text-[#fef2f2] dark:group-[.toast]:border-[#991b1b]',
          warning:
            'group-[.toast]:bg-[#fefce8] group-[.toast]:text-[#713f12] group-[.toast]:border-[#fef08a] dark:group-[.toast]:bg-[#422006] dark:group-[.toast]:text-[#fefce8] dark:group-[.toast]:border-[#854d0e]',
        },
      }}
      {...props}
      position="top-center"
    />
  )
}

export { Toaster }
