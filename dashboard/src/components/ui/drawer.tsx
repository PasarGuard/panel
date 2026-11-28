import * as React from 'react'
import { Drawer as DrawerPrimitive } from 'vaul'

import { cn } from '@/lib/utils'

const Drawer = ({ shouldScaleBackground = true, ...props }: React.ComponentProps<typeof DrawerPrimitive.Root>) => <DrawerPrimitive.Root shouldScaleBackground={shouldScaleBackground} {...props} />
Drawer.displayName = 'Drawer'

const DrawerTrigger = DrawerPrimitive.Trigger

const DrawerPortal = DrawerPrimitive.Portal

const DrawerClose = DrawerPrimitive.Close

const DrawerOverlay = React.forwardRef<React.ElementRef<typeof DrawerPrimitive.Overlay>, React.ComponentPropsWithoutRef<typeof DrawerPrimitive.Overlay>>(({ className, ...props }, ref) => (
  <DrawerPrimitive.Overlay ref={ref} className={cn('fixed inset-0 z-50 bg-black/80', className)} {...props} />
))
DrawerOverlay.displayName = DrawerPrimitive.Overlay.displayName

const DrawerContent = React.forwardRef<React.ElementRef<typeof DrawerPrimitive.Content>, React.ComponentPropsWithoutRef<typeof DrawerPrimitive.Content> & { showHandle?: boolean }>(
  ({ className, children, showHandle = true, ...props }, ref) => (
    <DrawerPortal>
      <DrawerOverlay />
      <DrawerPrimitive.Content
        ref={ref}
        className={cn('bg-background fixed inset-x-0 bottom-0 z-50 flex max-h-dvh touch-auto! flex-col overflow-hidden rounded-t-xl border outline-none select-auto!', className)}
        {...props}
      >
        {showHandle && <DrawerPrimitive.Handle preventCycle className="bg-muted-foreground/40! z-10 mt-3 mb-1 w-16! shrink-0 touch-none!" />}
        {children}
      </DrawerPrimitive.Content>
    </DrawerPortal>
  ),
)
DrawerContent.displayName = 'DrawerContent'

const DrawerHeader = ({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) => <div className={cn('grid gap-1 px-4 py-2 text-center sm:text-start', className)} {...props} />
DrawerHeader.displayName = 'DrawerHeader'

const DrawerFooter = ({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) => <div data-slot="drawer-footer" className={cn('mt-auto flex flex-col gap-2 p-4', className)} {...props} />
DrawerFooter.displayName = 'DrawerFooter'

const DrawerTitle = React.forwardRef<React.ElementRef<typeof DrawerPrimitive.Title>, React.ComponentPropsWithoutRef<typeof DrawerPrimitive.Title>>(({ className, ...props }, ref) => (
  <DrawerPrimitive.Title ref={ref} className={cn('text-base/5 font-medium tracking-tight [&>svg]:size-4 [&>svg]:shrink-0', className)} {...props} />
))
DrawerTitle.displayName = DrawerPrimitive.Title.displayName

const DrawerDescription = React.forwardRef<React.ElementRef<typeof DrawerPrimitive.Description>, React.ComponentPropsWithoutRef<typeof DrawerPrimitive.Description>>(({ className, ...props }, ref) => (
  <DrawerPrimitive.Description ref={ref} className={cn('text-muted-foreground text-sm', className)} {...props} />
))
DrawerDescription.displayName = DrawerPrimitive.Description.displayName

export { Drawer, DrawerPortal, DrawerOverlay, DrawerTrigger, DrawerClose, DrawerContent, DrawerHeader, DrawerFooter, DrawerTitle, DrawerDescription }
