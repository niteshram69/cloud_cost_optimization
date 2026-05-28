import Link from 'next/link';

export function EnterpriseFooter() {
  return (
    <footer className="bg-surface-dark border-t border-gray-800 py-12 text-gray-400">
      <div className="container mx-auto px-4 lg:px-8">
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-5 gap-8 mb-12">
          <div className="col-span-2 lg:col-span-1">
            <Link href="/" className="flex items-center gap-2 mb-4">
              <span className="text-2xl font-bold tracking-tight text-white">
                Cloud<span className="text-brand-500">teck</span>
              </span>
            </Link>
            <p className="text-sm text-gray-500 max-w-xs">
              Intelligent multi-cloud cost optimization. Analyze, predict, and optimize cloud spending with AI-powered FinOps intelligence.
            </p>
          </div>
          <div>
            <h4 className="font-semibold text-white mb-4">Platform</h4>
            <ul className="space-y-2 text-sm">
              <li><Link href="#" className="hover:text-brand-400 transition-colors">Features</Link></li>
              <li><Link href="#" className="hover:text-brand-400 transition-colors">Integrations</Link></li>
              <li><Link href="#" className="hover:text-brand-400 transition-colors">Security</Link></li>
              <li><Link href="/pricing" className="hover:text-brand-400 transition-colors">Pricing</Link></li>
            </ul>
          </div>
          <div>
            <h4 className="font-semibold text-white mb-4">Resources</h4>
            <ul className="space-y-2 text-sm">
              <li><Link href="#" className="hover:text-brand-400 transition-colors">Docs</Link></li>
              <li><Link href="#" className="hover:text-brand-400 transition-colors">API Reference</Link></li>
              <li><Link href="#" className="hover:text-brand-400 transition-colors">Blog</Link></li>
              <li><Link href="#" className="hover:text-brand-400 transition-colors">Case Studies</Link></li>
            </ul>
          </div>
          <div>
            <h4 className="font-semibold text-white mb-4">Company</h4>
            <ul className="space-y-2 text-sm">
              <li><Link href="/about" className="hover:text-brand-400 transition-colors">About</Link></li>
              <li><Link href="#" className="hover:text-brand-400 transition-colors">Careers</Link></li>
              <li><Link href="#" className="hover:text-brand-400 transition-colors">Contact</Link></li>
            </ul>
          </div>
        </div>
        <div className="flex flex-col md:flex-row items-center justify-between pt-8 border-t border-gray-800 text-sm">
          <p>&copy; {new Date().getFullYear()} Cloudteck Inc. All rights reserved.</p>
          <div className="flex gap-4 mt-4 md:mt-0">
            <Link href="#" className="hover:text-brand-400 transition-colors">Privacy Policy</Link>
            <Link href="#" className="hover:text-brand-400 transition-colors">Terms of Service</Link>
          </div>
        </div>
      </div>
    </footer>
  );
}
