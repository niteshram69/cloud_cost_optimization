import { Button } from "@/components/ui/button"
import { Check } from "lucide-react"

export default function PricingPage() {
  return (
    <div className="bg-surface-muted py-24 sm:py-32">
      <div className="mx-auto max-w-7xl px-6 lg:px-8">
        <div className="mx-auto max-w-4xl text-center">
          <h2 className="text-base font-semibold leading-7 text-brand-600">Pricing</h2>
          <p className="mt-2 text-4xl font-bold tracking-tight text-brand-900 sm:text-5xl">
            Scale your cloud ROI, not your bill
          </p>
        </div>
        <p className="mx-auto mt-6 max-w-2xl text-center text-lg leading-8 text-gray-600">
          Distinct plans built for agile teams and enterprise-scale organizations. Connect unlimited cloud accounts with no seat limits.
        </p>

        <div className="isolate mx-auto mt-16 grid max-w-md grid-cols-1 gap-y-8 sm:mt-20 lg:mx-0 lg:max-w-none lg:grid-cols-3 lg:gap-x-8 xl:gap-x-12">
          {/* Free Tier */}
          <PricingCard
            name="Free Overview"
            price="$0"
            description="Perfect for individuals analyzing a single cloud environment."
            features={[
              "1 Cloud Account (AWS/Azure/GCP)",
              "Basic Storage Read/Write Metrics",
              "7-day data retention",
              "Community Support",
            ]}
            cta="Start Free"
            variant="outline"
          />

          {/* Starter Tier */}
          <PricingCard
            name="FinOps Starter"
            price="$299"
            period="/month"
            description="Automated recommendations and basic tiering migration."
            features={[
              "Up to 5 Cloud Accounts",
              "AI Storage Optimization Engine",
              "1-Click Manual Approvals",
              "30-day data retention",
              "Standard Email Support",
            ]}
            cta="Start 14-Day Trial"
            isPopular
          />

          {/* Enterprise Tier */}
          <PricingCard
            name="Enterprise Control"
            price="Custom"
            description="Zero-trust automation and complex multi-cloud forecasting."
            features={[
              "Unlimited Cloud Accounts",
              "Fully Automated Migration Execution",
              "SSO & Custom RBAC",
              "Multi-year data retention",
              "24/7 Dedicated Account Manager",
            ]}
            cta="Contact Sales"
            variant="outline"
          />
        </div>
      </div>
    </div>
  )
}

function PricingCard({ name, price, period, description, features, cta, isPopular, variant = "primary" }: any) {
  return (
    <div className={`rounded-3xl p-8 ring-1 ${isPopular ? "ring-brand-600 shadow-premium bg-white" : "ring-gray-200 bg-white shadow-sm"}`}>
      <h3 className={`text-lg font-semibold leading-8 ${isPopular ? "text-brand-600" : "text-gray-900"}`}>
        {name}
        {isPopular && <span className="ml-2 inline-flex items-center rounded-full bg-brand-50 px-2.5 py-0.5 text-xs font-medium text-brand-600">Most popular</span>}
      </h3>
      <p className="mt-4 text-sm leading-6 text-gray-600">{description}</p>
      <div className="mt-6 flex items-baseline gap-x-1">
        <span className="text-4xl font-bold tracking-tight text-gray-900">{price}</span>
        {period && <span className="text-sm font-semibold leading-6 text-gray-600">{period}</span>}
      </div>
      <Button 
        className="mt-6 w-full h-12 rounded-xl text-md" 
        variant={variant === "outline" ? "outline" : "default"}
      >
        {cta}
      </Button>
      <ul role="list" className="mt-8 space-y-3 text-sm leading-6 text-gray-600 xl:mt-10">
        {features.map((feature: string) => (
          <li key={feature} className="flex gap-x-3">
            <Check className="h-6 w-5 flex-none text-brand-600" aria-hidden="true" />
            {feature}
          </li>
        ))}
      </ul>
    </div>
  )
}
