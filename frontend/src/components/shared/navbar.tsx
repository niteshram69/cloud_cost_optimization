import Link from 'next/link';
import { Button } from '@/components/ui/button';

export function GlobalNavbar() {
  return (
    <header className="sticky top-0 z-50 w-full border-b border-gray-100 bg-white/80 backdrop-blur-md">
      <div className="container mx-auto flex h-16 items-center justify-between px-4 lg:px-8">
        <div className="flex items-center gap-8">
          <Link href="/" className="flex items-center gap-2">
            <span className="text-2xl font-bold tracking-tight text-brand-900">
              Cloud<span className="text-brand-600">teck</span>
            </span>
          </Link>
          <nav className="hidden md:flex gap-6">
            <Link href="#platform" className="text-sm font-medium text-gray-600 hover:text-brand-600 transition-colors">
              Platform
            </Link>
            <Link href="#solutions" className="text-sm font-medium text-gray-600 hover:text-brand-600 transition-colors">
              Solutions
            </Link>
            <Link href="/dashboard/integrations" className="text-sm font-medium text-gray-600 hover:text-brand-600 transition-colors">
              Integrations
            </Link>
            <Link href="/pricing" className="text-sm font-medium text-gray-600 hover:text-brand-600 transition-colors">
              Pricing
            </Link>
            <Link href="/docs" className="text-sm font-medium text-gray-600 hover:text-brand-600 transition-colors">
              Docs
            </Link>
          </nav>
        </div>
        <div className="flex items-center gap-4">
          <div className="hidden sm:flex items-center gap-2">
            <Link href="/login">
              <Button variant="ghost">Login</Button>
            </Link>
            <Link href="/signup">
              <Button variant="outline">Sign Up</Button>
            </Link>
          </div>
          <Link href="/signup">
            <Button>Request Demo</Button>
          </Link>
        </div>
      </div>
    </header>
  );
}
