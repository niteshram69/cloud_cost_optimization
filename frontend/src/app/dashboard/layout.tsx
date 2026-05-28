 "use client"

import Link from "next/link"
import { usePathname, useRouter } from "next/navigation"
import { Home, Lightbulb, Link as LinkIcon, CreditCard, Settings, Search, Bell } from "lucide-react"

import { useAuth } from "@/hooks/useAuth"

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode
}) {
  const pathname = usePathname()
  const router = useRouter()
  const { user, logout } = useAuth()

  const nav = [
    { href: "/dashboard/overview", label: "Overview", icon: Home },
    { href: "/dashboard/recommendations", label: "Recommendations", icon: Lightbulb },
    { href: "/dashboard/integrations", label: "Integrations", icon: LinkIcon },
    { href: "/dashboard/billing", label: "Billing", icon: CreditCard },
    { href: "/dashboard/settings", label: "Settings", icon: Settings },
  ]

  return (
    <div className="flex h-screen w-full bg-slate-50 overflow-hidden">
      {/* Sidebar */}
      <aside className="hidden w-64 flex-col border-r border-slate-200 bg-white md:flex flex-shrink-0">
        <div className="flex h-16 items-center border-b border-slate-200 px-6">
          <Link href="/" className="flex items-center gap-2">
            <span className="text-xl font-semibold tracking-tight text-slate-900">
              Cloud<span className="text-blue-600">teck</span>
            </span>
          </Link>
        </div>
        <nav className="flex-1 space-y-1 px-3 py-4 overflow-y-auto">
          {nav.map((item) => (
            <SidebarItem
              key={item.href}
              href={item.href}
              icon={item.icon}
              label={item.label}
              active={pathname.startsWith(item.href)}
            />
          ))}
        </nav>
        <div className="p-4 border-t border-slate-200 flex items-center gap-3">
          <div className="w-8 h-8 rounded-full bg-blue-100 text-blue-700 flex items-center justify-center font-semibold text-xs">
            {(user?.name ?? "User").slice(0, 2).toUpperCase()}
          </div>
          <div className="flex flex-col">
            <span className="text-sm font-semibold text-gray-900 leading-none">{user?.name ?? "User"}</span>
            <span className="text-xs text-gray-500">{user?.role ?? "Member"}</span>
          </div>
        </div>
      </aside>

      {/* Main Content Area */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Topbar */}
        <header className="flex h-16 items-center gap-4 border-b border-slate-200 bg-white px-4 md:px-8 flex-shrink-0">
          <div className="md:hidden">
            <span className="text-xl font-semibold tracking-tight text-slate-900">Cloud<span className="text-blue-600">teck</span></span>
          </div>
          <div className="flex flex-1 items-center">
            <div className="relative w-full max-w-xl">
              <Search className="absolute left-3 top-3 h-4 w-4 text-slate-400" />
              <input
                type="text"
                placeholder="Search resources, integrations, docs..."
                className="w-full rounded-xl border border-slate-200 bg-gray-50 py-2.5 pl-10 pr-3 text-sm text-slate-900 focus:border-blue-400 focus:ring-2 focus:ring-blue-100"
              />
            </div>
          </div>
          <div className="flex items-center gap-3">
            <button className="relative rounded-full border border-slate-200 p-2 text-slate-500 hover:text-slate-700">
              <span className="absolute right-2 top-2 h-2 w-2 rounded-full bg-rose-500" />
              <Bell className="h-5 w-5" />
            </button>
            <div className="flex items-center gap-2 rounded-full border border-slate-200 bg-white px-2 py-1">
              <div className="h-8 w-8 rounded-full bg-blue-100 text-blue-700 flex items-center justify-center text-xs font-semibold">
                {(user?.name ?? "User").slice(0, 2).toUpperCase()}
              </div>
              <span className="hidden md:inline text-sm font-semibold text-slate-700">
                {user?.name ?? "User"}
              </span>
            </div>
            <button
              className="rounded-full border border-slate-200 px-4 py-2 text-sm font-semibold text-slate-700 hover:border-slate-300 hover:bg-slate-50"
              type="button"
              onClick={() => {
                logout()
                router.push("/login")
              }}
            >
              Logout
            </button>
          </div>
        </header>

        {/* Scrollable Page Content */}
        <main className="relative flex-1 overflow-y-auto p-4 md:p-8">
          {children}
        </main>
      </div>
    </div>
  )
}

function SidebarItem({ href, icon: Icon, label, active = false }: any) {
  return (
    <Link
      href={href}
      className={`group flex items-center rounded-xl px-3 py-2 text-sm font-medium transition ${
        active 
          ? 'bg-blue-50 text-blue-600' 
          : 'text-slate-600 hover:bg-slate-50 hover:text-blue-600'
      }`}
    >
      <Icon
        className={`mr-3 h-5 w-5 flex-shrink-0 ${
          active ? 'text-blue-600' : 'text-slate-400 group-hover:text-blue-600'
        }`}
      />
      {label}
    </Link>
  )
}
