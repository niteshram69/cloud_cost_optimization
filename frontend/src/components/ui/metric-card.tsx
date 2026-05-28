import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { TrendingDown, TrendingUp, Minus } from "lucide-react"
import { cn } from "@/lib/utils"

interface MetricCardProps {
  title: string
  value: string | number
  trend?: number
  trendLabel?: string
  icon?: React.ReactNode
}

export function MetricCard({ title, value, trend, trendLabel, icon }: MetricCardProps) {
  const isPositive = trend && trend > 0
  const isNegative = trend && trend < 0
  const isNeutral = trend === 0

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-sm font-medium text-gray-500">
          {title}
        </CardTitle>
        {icon && <div className="text-gray-400">{icon}</div>}
      </CardHeader>
      <CardContent>
        <div className="text-2xl font-bold text-gray-900">{value}</div>
        {trend !== undefined && (
          <div className="mt-1 flex items-center text-xs">
            {isPositive && <TrendingUp className="mr-1 h-3 w-3 text-success" />}
            {isNegative && <TrendingDown className="mr-1 h-3 w-3 text-success" />}
            {isNeutral && <Minus className="mr-1 h-3 w-3 text-gray-400" />}
            
            <span
              className={cn(
                "font-medium",
                isNegative ? "text-success" : isPositive ? "text-error" : "text-gray-500"
              )}
            >
              {Math.abs(trend)}%
            </span>
            {trendLabel && <span className="ml-1 text-gray-500">{trendLabel}</span>}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
