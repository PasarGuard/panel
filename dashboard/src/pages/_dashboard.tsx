import DonationPopup from '@/components/common/donation-popup'
import TopbarAd from '@/components/common/topbar-ad'
import { Footer } from '@/components/layout/footer'
import PageTransition from '@/components/layout/page-transition'
import RouteGuard from '@/components/layout/route-guard'
import { AppSidebar } from '@/components/layout/sidebar'
import { TopLoadingBar } from '@/components/layout/top-loading-bar'
import { VersionUpdateBanner } from '@/components/layout/version-update-banner'
import { SidebarInset, SidebarProvider } from '@/components/ui/sidebar'
import { AdminDetails, getCurrentAdmin } from '@/service/api'
import { clearAuthSession } from '@/utils/authSession'
import { getAuthToken } from '@/utils/authStorage'
import { Outlet } from 'react-router'

export const clientLoader = async (): Promise<AdminDetails> => {
  if (!getAuthToken()) {
    throw Response.redirect('/login')
  }

  try {
    const response = await getCurrentAdmin()
    return response
  } catch {
    await clearAuthSession()
    throw Response.redirect('/login')
  }
}

export default function DashboardLayout() {
  return (
    <SidebarProvider className="">
      <RouteGuard>
        <TopLoadingBar />
        <DonationPopup />
        <div className="flex w-full flex-col lg:flex-row">
          <AppSidebar />
          <SidebarInset className="scroll-smooth">
            <TopbarAd />
            <VersionUpdateBanner />
            <div className="flex min-h-0 w-full flex-1 flex-col justify-between gap-y-4">
              <PageTransition duration={250} className="flex min-h-0 flex-1 flex-col">
                <Outlet />
              </PageTransition>
              <Footer />
            </div>
          </SidebarInset>
        </div>
      </RouteGuard>
    </SidebarProvider>
  )
}
