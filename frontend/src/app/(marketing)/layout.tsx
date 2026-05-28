import { GlobalNavbar } from "@/components/shared/navbar"
import { EnterpriseFooter } from "@/components/shared/footer"

export default function MarketingLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <div className="flex min-h-screen flex-col">
      <GlobalNavbar />
      <main className="flex-1">
        {children}
      </main>
      <EnterpriseFooter />
    </div>
  )
}
