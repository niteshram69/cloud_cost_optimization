import { LucideIcon } from "lucide-react"
import Link from "next/link"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"

interface FeatureCardProps {
  icon: LucideIcon
  title: string
  description: string
  href?: string
}

export function FeatureCard({ icon: Icon, title, description, href }: FeatureCardProps) {
  return (
    <Card className="flex flex-col h-full hover:shadow-premium transition-shadow duration-300">
      <CardHeader>
        <div className="mb-4 inline-flex h-12 w-12 items-center justify-center rounded-lg bg-brand-50 text-brand-600">
          <Icon className="h-6 w-6" />
        </div>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent className="flex-1 flex flex-col">
        <CardDescription className="text-base flex-1">
          {description}
        </CardDescription>
        {href && (
          <div className="mt-6">
            <Link href={href} className="text-sm font-semibold text-brand-600 hover:text-brand-700 flex items-center gap-1">
              Learn more <span aria-hidden="true">&rarr;</span>
            </Link>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
