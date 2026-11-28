import * as React from 'react'
import * as AlertDialogPrimitive from '@radix-ui/react-alert-dialog'

import { cn } from '@/lib/utils'
import { buttonVariants } from '@/components/ui/button'
import { VariantProps } from 'class-variance-authority'
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogPortal, DialogTitle, DialogTrigger, useDialogDrawer } from '@/components/ui/dialog'

function AlertDialog(props: React.ComponentProps<typeof AlertDialogPrimitive.Root>) {
  return <Dialog desktopRoot={AlertDialogPrimitive.Root} {...props} />
}

const AlertDialogTrigger = React.forwardRef<React.ElementRef<typeof AlertDialogPrimitive.Trigger>, React.ComponentPropsWithoutRef<typeof AlertDialogPrimitive.Trigger>>((props, ref) => {
  const Trigger = useDialogDrawer() ? DialogTrigger : AlertDialogPrimitive.Trigger
  return <Trigger ref={ref} {...props} />
})
AlertDialogTrigger.displayName = 'AlertDialogTrigger'

function AlertDialogPortal(props: React.ComponentProps<typeof AlertDialogPrimitive.Portal>) {
  const Portal = useDialogDrawer() ? DialogPortal : AlertDialogPrimitive.Portal
  return <Portal {...props} />
}

const AlertDialogOverlay = React.forwardRef<React.ElementRef<typeof AlertDialogPrimitive.Overlay>, React.ComponentPropsWithoutRef<typeof AlertDialogPrimitive.Overlay>>(
  ({ className, ...props }, ref) => (
    <AlertDialogPrimitive.Overlay
      className={cn('data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 fixed inset-0 z-50 bg-black/80', className)}
      {...props}
      ref={ref}
    />
  ),
)
AlertDialogOverlay.displayName = AlertDialogPrimitive.Overlay.displayName

const AlertDialogContent = React.forwardRef<React.ElementRef<typeof AlertDialogPrimitive.Content>, React.ComponentPropsWithoutRef<typeof AlertDialogPrimitive.Content>>(
  ({ className, onOpenAutoFocus, ...props }, ref) => {
    if (useDialogDrawer()) {
      return (
        <DialogContent
          {...props}
          ref={ref}
          role="alertdialog"
          className={className}
          showCloseButton={false}
          showDragHandle={false}
          onInteractOutside={event => event.preventDefault()}
          onOpenAutoFocus={event => {
            onOpenAutoFocus?.(event)
            if (event.defaultPrevented) return

            // Give keyboard focus to Cancel, as the desktop alert dialog does.
            event.preventDefault()
            const content = event.target as HTMLElement
            const focusTarget = content.querySelector<HTMLElement>('[data-alert-dialog-cancel]:not(:disabled)') ?? content
            focusTarget.focus({ preventScroll: true })
          }}
        />
      )
    }

    return (
      <AlertDialogPortal>
        <AlertDialogOverlay />
        <AlertDialogPrimitive.Content
          ref={ref}
          className={cn(
            'bg-background data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95 fixed top-[50%] left-[50%] z-50 grid w-full max-w-lg translate-x-[-50%] translate-y-[-50%] gap-3 border p-6 pt-4 shadow-lg duration-200 sm:rounded-lg',
            className,
          )}
          onOpenAutoFocus={onOpenAutoFocus}
          {...props}
        />
      </AlertDialogPortal>
    )
  },
)
AlertDialogContent.displayName = AlertDialogPrimitive.Content.displayName

const AlertDialogHeader = ({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) => <DialogHeader className={cn('pe-0', className)} {...props} />
AlertDialogHeader.displayName = 'AlertDialogHeader'

const AlertDialogFooter = DialogFooter

const AlertDialogTitle = React.forwardRef<React.ElementRef<typeof AlertDialogPrimitive.Title>, React.ComponentPropsWithoutRef<typeof AlertDialogPrimitive.Title>>(({ className, ...props }, ref) => {
  const Title = useDialogDrawer() ? DialogTitle : AlertDialogPrimitive.Title
  return <Title ref={ref} className={cn('text-base/5 font-medium tracking-tight [&>svg]:size-4 [&>svg]:shrink-0', className)} {...props} />
})
AlertDialogTitle.displayName = AlertDialogPrimitive.Title.displayName

const AlertDialogDescription = React.forwardRef<React.ElementRef<typeof AlertDialogPrimitive.Description>, React.ComponentPropsWithoutRef<typeof AlertDialogPrimitive.Description>>(
  ({ className, ...props }, ref) => {
    const Description = useDialogDrawer() ? DialogDescription : AlertDialogPrimitive.Description
    return <Description ref={ref} className={cn('text-muted-foreground text-sm', className)} {...props} />
  },
)
AlertDialogDescription.displayName = AlertDialogPrimitive.Description.displayName

const AlertDialogAction = React.forwardRef<
  React.ElementRef<typeof AlertDialogPrimitive.Action>,
  { variant?: VariantProps<typeof buttonVariants>['variant'] } & React.ComponentPropsWithoutRef<typeof AlertDialogPrimitive.Action>
>(({ className, variant, ...props }, ref) => {
  const Action = useDialogDrawer() ? DialogClose : AlertDialogPrimitive.Action
  return <Action ref={ref} className={cn(buttonVariants({ variant }), className)} data-variant={variant ?? 'default'} {...props} />
})
AlertDialogAction.displayName = AlertDialogPrimitive.Action.displayName

const AlertDialogCancel = React.forwardRef<React.ElementRef<typeof AlertDialogPrimitive.Cancel>, React.ComponentPropsWithoutRef<typeof AlertDialogPrimitive.Cancel>>(({ className, ...props }, ref) => {
  const Cancel = useDialogDrawer() ? DialogClose : AlertDialogPrimitive.Cancel
  return <Cancel ref={ref} className={cn(buttonVariants({ variant: 'outline' }), className)} data-variant="outline" data-alert-dialog-cancel="" {...props} />
})
AlertDialogCancel.displayName = AlertDialogPrimitive.Cancel.displayName

export {
  AlertDialog,
  AlertDialogPortal,
  AlertDialogOverlay,
  AlertDialogTrigger,
  AlertDialogContent,
  AlertDialogHeader,
  AlertDialogFooter,
  AlertDialogTitle,
  AlertDialogDescription,
  AlertDialogAction,
  AlertDialogCancel,
}
