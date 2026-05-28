import { Button } from "@/components/ui/button"
import { FeatureCard } from "@/components/ui/feature-card"
import { ArrowRight, BarChart3, CloudCog, ShieldCheck, Zap } from "lucide-react"

export default function HomePage() {
  return (
    <>
      {/* Hero Section */}
      <section className="relative overflow-hidden bg-surface-muted pt-24 pb-32 lg:pt-36 lg:pb-40">
        <div className="absolute inset-0 bg-[linear-gradient(to_right,#80808012_1px,transparent_1px),linear-gradient(to_bottom,#80808012_1px,transparent_1px)] bg-[size:24px_24px]"></div>
        <div className="container relative mx-auto px-4 lg:px-8">
          <div className="grid lg:grid-cols-2 gap-12 items-center">
            <div className="max-w-2xl">
              <div className="inline-flex items-center rounded-full border border-brand-200 bg-brand-50 px-3 py-1 text-sm font-medium text-brand-600 mb-6">
                <Zap className="mr-2 h-4 w-4" /> v2 AI Engine Now Live
              </div>
              <h1 className="text-4xl font-extrabold tracking-tight text-brand-900 sm:text-5xl lg:text-6xl text-balance">
                Intelligent Multi-Cloud <span className="text-brand-600">Cost Optimization</span>
              </h1>
              <p className="mt-6 text-xl text-gray-600 max-w-lg text-balance">
                Analyze, predict, and optimize cloud spending across AWS, Azure, and GCP with AI-powered FinOps intelligence.
              </p>
              <div className="mt-10 flex flex-col sm:flex-row gap-4">
                <Button size="lg" className="h-14 px-8 text-lg rounded-xl">
                  Start Free Full Scan
                </Button>
                <Button variant="outline" size="lg" className="h-14 px-8 text-lg rounded-xl bg-white border-brand-200 text-brand-700">
                  Request Demo
                </Button>
              </div>
            </div>
            {/* Dashboard Mockup Graphic */}
            <div className="relative mx-auto w-full max-w-lg lg:max-w-none">
              <div className="absolute -inset-0.5 rounded-2xl bg-gradient-to-tr from-brand-600 to-accent-500 opacity-20 blur-2xl"></div>
              <div className="relative rounded-2xl border border-gray-200 bg-white/50 p-2 shadow-2xl backdrop-blur-xl">
                <div className="rounded-xl overflow-hidden bg-gray-50 border border-gray-100 flex flex-col h-[400px]">
                  {/* Mockup Topbar */}
                  <div className="h-12 border-b border-gray-200 bg-white flex items-center px-4 gap-2">
                    <div className="flex gap-1.5 border-r pr-4 border-gray-200">
                      <div className="w-3 h-3 rounded-full bg-red-400"></div>
                      <div className="w-3 h-3 rounded-full bg-yellow-400"></div>
                      <div className="w-3 h-3 rounded-full bg-green-400"></div>
                    </div>
                    <div className="bg-gray-100 h-6 w-64 rounded text-xs text-gray-400 flex items-center px-2">cloudteck.io/dashboard</div>
                  </div>
                  {/* Mockup UI Component */}
                  <div className="p-6">
                    <div className="flex justify-between items-end mb-8">
                      <div>
                        <div className="text-sm font-medium text-gray-500 mb-1">Total Cloud Spend (YTD)</div>
                        <div className="text-4xl font-bold text-gray-900">$2,405,102.50</div>
                      </div>
                      <div className="px-3 py-1 bg-green-100 text-green-800 rounded-lg text-sm font-semibold flex items-center">
                        <ArrowRight className="w-4 h-4 mr-1 md:-ml-1" />
                        Est. Savings: $405k
                      </div>
                    </div>
                    {/* Mock Charts */}
                    <div className="flex gap-4 mb-4">
                      <div className="flex-1 bg-white border border-gray-200 rounded-lg p-4 h-32 flex flex-col justify-end gap-1 items-end relative overflow-hidden">
                        <div className="w-full bg-blue-100 rounded-t-sm h-[40%]"></div>
                        <div className="w-[80%] bg-brand-500 rounded-t-sm h-[80%] absolute left-4 bottom-0"></div>
                        <div className="w-[60%] bg-purple-500 rounded-t-sm h-[60%] absolute right-4 bottom-0"></div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Trusted By Logos */}
      <section className="border-y border-gray-100 bg-white py-10">
        <div className="container mx-auto px-4 text-center">
          <p className="text-sm font-semibold text-gray-400 tracking-widest uppercase mb-8">Trusted by data-driven FinOps teams natively integrating with</p>
          <div className="flex flex-wrap justify-center items-center gap-12 lg:gap-24 grayscale opacity-60">
            {/* Logos represented via SVG or stylized text for mockup */}
            <div className="text-2xl font-bold font-sans">aws</div>
            <div className="text-2xl font-bold font-sans flex items-center gap-1"><CloudCog/> Azure</div>
            <div className="text-2xl font-bold font-sans flex items-center gap-1"><CloudCog/> Google Cloud</div>
            <div className="text-2xl font-bold font-serif italic">Persistent</div>
          </div>
        </div>
      </section>

      {/* Platform Capabilities */}
      <section id="platform" className="py-24 bg-white relative">
        <div className="container mx-auto px-4 lg:px-8">
          <div className="text-center max-w-3xl mx-auto mb-16">
            <h2 className="text-3xl font-bold text-brand-900 sm:text-4xl">Enterprise FinOps capabilities</h2>
            <p className="mt-4 text-lg text-gray-600">Uncover hidden waste, apply zero-trust migration controls, and let ai safely move your infrastructure objects to cheaper tiers.</p>
          </div>
          <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-6">
            <FeatureCard 
              icon={BarChart3} 
              title="Multi-Cloud Intelligence" 
              description="Unified dashboard providing sub-second querying across AWS, Azure, and Google Cloud billing records."
              href="/dashboard"
            />
            <FeatureCard 
              icon={Brain} 
              title="AI Cost Optimization" 
              description="RandomForest-powered predictive models segment hot, cold, and archival storage with confidence scoring."
              href="#ai"
            />
            <FeatureCard 
              icon={ShieldCheck} 
              title="Automated Tier Migration" 
              description="Safely move storage tiers with 1-click approvals, dry-runs, and full RBAC zero-trust controls."
              href="/docs/migration"
            />
            <FeatureCard 
              icon={Zap} 
              title="Real-Time Analytics" 
              description="Idempotent webhooks sync resource state instantly directly from your cloud provider EventBridge."
              href="/solutions"
            />
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section className="bg-brand-900 py-24 relative overflow-hidden">
        <div className="absolute inset-0 bg-brand-600/20 mix-blend-multiply"></div>
        <div className="absolute -top-40 -right-40 w-96 h-96 bg-accent-500 rounded-full mix-blend-screen filter blur-3xl opacity-30"></div>
        <div className="container mx-auto px-4 text-center relative z-10">
          <h2 className="text-4xl font-bold tracking-tight text-white mb-6">Start Optimizing Your Cloud Spend Today</h2>
          <p className="text-xl text-brand-100 max-w-2xl mx-auto mb-10">
            Join hundreds of enterprises managing millions in cloud spend. Connect your first AWS account in under 60 seconds.
          </p>
          <div className="flex flex-col sm:flex-row gap-4 justify-center">
            <Button size="lg" className="bg-white text-brand-900 hover:bg-gray-100 h-14 px-8 text-lg font-semibold rounded-xl border-0">
              Start Free Trial
            </Button>
            <Button size="lg" variant="outline" className="text-white border-white/30 hover:bg-white/10 h-14 px-8 text-lg gap-2 rounded-xl">
              Book Enterprise Demo
            </Button>
          </div>
        </div>
      </section>
    </>
  )
}

function Brain(props: any) {
  return (
    <svg
      {...props}
      xmlns="http://www.w3.org/2000/svg"
      width="24"
      height="24"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M12 5a3 3 0 1 0-5.997.125 4 4 0 0 0-2.526 5.77 4 4 0 0 0 .556 6.588A4 4 0 1 0 12 18Z" />
      <path d="M12 5a3 3 0 1 1 5.997.125 4 4 0 0 1 2.526 5.77 4 4 0 0 1-.556 6.588A4 4 0 1 1 12 18Z" />
      <path d="M15 13a4.5 4.5 0 0 1-3-4 4.5 4.5 0 0 1-3 4" />
      <path d="M17.599 6.5A3 3 0 0 0 13.6 4.4" />
      <path d="M6.401 6.5A3 3 0 0 1 10.4 4.4" />
    </svg>
  )
}
