import * as React from 'react'
import * as DialogPrimitive from '@radix-ui/react-dialog'
import { X } from 'lucide-react'

import { cn } from '@/lib/utils'
import useDirDetection from '@/hooks/use-dir-detection'
import { useIsMobile } from '@/hooks/use-mobile'
import { Drawer, DrawerClose, DrawerContent, DrawerDescription, DrawerFooter, DrawerPortal, DrawerTitle, DrawerTrigger } from '@/components/ui/drawer'

const DialogDrawerContext = React.createContext(false)

const useDialogDrawer = () => React.useContext(DialogDrawerContext)

type DialogProps = React.ComponentProps<typeof DialogPrimitive.Root> & { desktopRoot?: typeof DialogPrimitive.Root }

function Dialog({ desktopRoot: DesktopRoot = DialogPrimitive.Root, open, defaultOpen = false, onOpenChange, ...props }: DialogProps) {
  const isDrawer = useIsMobile()
  const nested = useDialogDrawer()
  const [uncontrolledOpen, setUncontrolledOpen] = React.useState(defaultOpen)
  const rootProps = {
    ...props,
    open: open ?? uncontrolledOpen,
    onOpenChange: (nextOpen: boolean) => {
      if (open === undefined) setUncontrolledOpen(nextOpen)
      onOpenChange?.(nextOpen)
    },
  }

  return (
    <DialogDrawerContext.Provider value={isDrawer}>
      {isDrawer ? <Drawer {...rootProps} autoFocus handleOnly nested={nested} shouldScaleBackground={false} /> : <DesktopRoot {...rootProps} />}
    </DialogDrawerContext.Provider>
  )
}

const DialogTrigger = React.forwardRef<React.ElementRef<typeof DialogPrimitive.Trigger>, React.ComponentPropsWithoutRef<typeof DialogPrimitive.Trigger>>((props, ref) => {
  const Trigger = useDialogDrawer() ? DrawerTrigger : DialogPrimitive.Trigger
  return <Trigger ref={ref} {...props} />
})
DialogTrigger.displayName = 'DialogTrigger'

function DialogPortal(props: React.ComponentProps<typeof DialogPrimitive.Portal>) {
  const Portal = useDialogDrawer() ? DrawerPortal : DialogPrimitive.Portal
  return <Portal {...props} />
}

const DialogClose = React.forwardRef<React.ElementRef<typeof DialogPrimitive.Close>, React.ComponentPropsWithoutRef<typeof DialogPrimitive.Close>>((props, ref) => {
  const Close = useDialogDrawer() ? DrawerClose : DialogPrimitive.Close
  return <Close ref={ref} {...props} />
})
DialogClose.displayName = 'DialogClose'

const DialogOverlay = React.forwardRef<React.ElementRef<typeof DialogPrimitive.Overlay>, React.ComponentPropsWithoutRef<typeof DialogPrimitive.Overlay>>(({ className, ...props }, ref) => (
  <DialogPrimitive.Overlay
    ref={ref}
    className={cn('data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 fixed inset-0 z-50 bg-black/50 backdrop-blur-sm', className)}
    {...props}
  />
))
DialogOverlay.displayName = DialogPrimitive.Overlay.displayName

const DialogContent = React.forwardRef<
  React.ElementRef<typeof DialogPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Content> & { showCloseButton?: boolean; showDragHandle?: boolean }
>(({ className, children, showCloseButton = true, showDragHandle = true, dir, ...props }, ref) => {
  const isDrawer = useDialogDrawer()
  const languageDir = useDirDetection()
  const closeButton = showCloseButton && (
    <DialogClose
      className={cn(
        'focus:ring-ring data-[state=open]:bg-accent data-[state=open]:text-muted-foreground absolute grid size-6 cursor-pointer place-items-center rounded-sm opacity-70 transition-opacity hover:opacity-100 focus:ring-2 focus:outline-none disabled:pointer-events-none',
        isDrawer ? 'inset-e-3 top-1.5 sm:inset-e-5' : 'inset-e-5 top-3.5',
      )}
      dir={dir ?? languageDir}
      data-dialog-close=""
    >
      <X className="h-4 w-4" />
      <span className="sr-only">Close</span>
    </DialogClose>
  )

  if (isDrawer) {
    return (
      <DrawerContent ref={ref} dir={dir ?? languageDir} className="pb-[env(safe-area-inset-bottom)]" showHandle={showDragHandle} {...props}>
        <div
          className={cn(
            'relative grid min-h-0 w-full gap-3 overflow-y-auto overscroll-contain p-4 pt-2 sm:p-6 sm:pt-2 [&:has([data-slot=drawer-footer])>[data-dialog-close]]:hidden',
            className,
            'w-full! max-w-none!',
          )}
        >
          {children}
          {closeButton}
        </div>
      </DrawerContent>
    )
  }

  return (
    <DialogPortal>
      <DialogOverlay />
      <DialogPrimitive.Content
        ref={ref}
        className={cn(
          'bg-background data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95 fixed top-[50%] left-[50%] z-50 grid w-full max-w-lg translate-x-[-50%] translate-y-[-50%] gap-3 border p-6 pt-4 shadow-lg duration-200 outline-none sm:rounded-lg',
          className,
        )}
        dir={dir}
        {...props}
      >
        {children}
        {closeButton}
      </DialogPrimitive.Content>
    </DialogPortal>
  )
})
DialogContent.displayName = DialogPrimitive.Content.displayName

const DialogHeader = ({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) => {
  const dir = useDirDetection()
  return <div dir={dir} className={cn('flex shrink-0 flex-col gap-1 pe-8 text-start', className)} {...props} />
}
DialogHeader.displayName = 'DialogHeader'

const DialogFooter = ({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) => {
  if (useDialogDrawer()) {
    return (
      <DrawerFooter
        className={cn(
          'bg-background sticky bottom-0 z-10 mt-0 shrink-0 flex-col-reverse px-0 pt-2 pb-0',
          '[&>button]:h-8 [&>button]:w-full [&>button]:gap-1.5 [&>button]:rounded-lg [&>button]:px-2.5',
          '[&>button[data-variant=default]:hover]:bg-primary/80 [&>button[data-variant=default]]:border [&>button[data-variant=default]]:border-transparent',
          '[&>button[data-variant=outline]:hover]:bg-muted dark:[&>button[data-variant=outline]]:bg-input/30 dark:[&>button[data-variant=outline]:hover]:bg-input/50',
          className,
        )}
        {...props}
      />
    )
  }

  return <div className={cn('flex flex-col-reverse gap-2 sm:flex-row sm:justify-end', className)} {...props} />
}
DialogFooter.displayName = 'DialogFooter'

const DialogTitle = React.forwardRef<React.ElementRef<typeof DialogPrimitive.Title>, React.ComponentPropsWithoutRef<typeof DialogPrimitive.Title>>(({ className, ...props }, ref) => {
  const Title = useDialogDrawer() ? DrawerTitle : DialogPrimitive.Title
  return <Title ref={ref} className={cn('text-base/5 font-medium tracking-tight [&>svg]:size-4 [&>svg]:shrink-0', className)} {...props} />
})
DialogTitle.displayName = DialogPrimitive.Title.displayName

const DialogDescription = React.forwardRef<React.ElementRef<typeof DialogPrimitive.Description>, React.ComponentPropsWithoutRef<typeof DialogPrimitive.Description>>(({ className, ...props }, ref) => {
  const Description = useDialogDrawer() ? DrawerDescription : DialogPrimitive.Description
  return <Description ref={ref} className={cn('text-muted-foreground text-sm', className)} {...props} />
})
DialogDescription.displayName = DialogPrimitive.Description.displayName

export { Dialog, DialogPortal, DialogOverlay, DialogTrigger, DialogClose, DialogContent, DialogHeader, DialogFooter, DialogTitle, DialogDescription, useDialogDrawer }
