import { Footer } from '@/components/layout/footer'
import { AppSidebar } from '@/components/layout/sidebar'
import PageTransition from '@/components/layout/page-transition'
import RouteGuard from '@/components/layout/route-guard'
import { TopLoadingBar } from '@/components/layout/top-loading-bar'
import { VersionUpdateBanner } from '@/components/layout/version-update-banner'
import DonationPopup from '@/components/common/donation-popup'
import { SidebarInset, SidebarProvider } from '@/components/ui/sidebar'
import { getCurrentAdmin } from '@/service/api'
import { Outlet } from 'react-router'
import TopbarAd from '@/components/common/topbar-ad'

export const clientLoader = async (): Promise<any> => {
  try {
    const response = await getCurrentAdmin()
    return response
  } catch (error) {
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
            <div className="flex min-h-screen w-full flex-col justify-between gap-y-4">
              <PageTransition duration={250}>
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
