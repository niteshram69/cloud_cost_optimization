import Link from 'next/link'

export default function AuthLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <div className="flex min-h-screen bg-white">
      {/* Left Pane - Branding Graphic */}
      <div className="hidden lg:flex lg:w-1/2 flex-col justify-between bg-brand-900 p-12 relative overflow-hidden">
        <div className="absolute inset-0 bg-brand-600/20 mix-blend-multiply"></div>
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[800px] h-[800px] bg-accent-500 rounded-full mix-blend-screen filter blur-3xl opacity-20"></div>
        
        <div className="relative z-10">
          <Link href="/" className="inline-block text-2xl font-bold tracking-tight text-white mb-8">
            Cloud<span className="text-brand-400">teck</span>
          </Link>
          <blockquote className="mt-12">
            <p className="text-3xl font-semibold leading-relaxed text-white">
              "Cloudteck's AI tiering recommendations saved our enterprise architecture team over $4M in redundant cloud storage costs within the first quarter."
            </p>
            <footer className="mt-8">
              <p className="text-base font-medium text-brand-200">Sarah Jenkins</p>
              <p className="text-sm font-medium text-brand-400">Chief Cloud Architect, DataNexus</p>
            </footer>
          </blockquote>
        </div>
        
        <div className="relative z-10 flex gap-4 text-sm text-brand-300">
          <Link href="#" className="hover:text-white transition-colors">Privacy Policy</Link>
          <Link href="#" className="hover:text-white transition-colors">Terms of Service</Link>
        </div>
      </div>

      {/* Right Pane - Form Area */}
      <div className="flex w-full lg:w-1/2 flex-col justify-center px-4 py-12 sm:px-6 lg:px-20 xl:px-24">
        {children}
      </div>
    </div>
  )
}
