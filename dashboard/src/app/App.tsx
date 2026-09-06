import { ThemeProvider } from '@/app/providers/theme-provider'
import { router } from '@/app/router'
import { ErrorBoundary } from '@/components/layout/error-boundary'
import { QueryClientProvider } from '@tanstack/react-query'
import { RouterProvider } from 'react-router'
import { Toaster } from '@/components/ui/sonner'
import { SidebarProvider } from '@/components/ui/sidebar'
import '@/lib/dayjs'
import { queryClient } from '@/utils/query-client'

export default function App() {
  return (
    <ThemeProvider defaultTheme="system" storageKey="theme">
      <QueryClientProvider client={queryClient}>
        <SidebarProvider className="contents">
          <main>
            <Toaster />
            <ErrorBoundary>
              <RouterProvider router={router} />
            </ErrorBoundary>
          </main>
        </SidebarProvider>
      </QueryClientProvider>
    </ThemeProvider>
  )
}
