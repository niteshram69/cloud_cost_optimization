"use client";

import { useEffect, useState } from "react";

import { PageState } from "@/components/PageState";
import { ProtectedView } from "@/components/ProtectedView";
import { fetchBillingCatalog, fetchBillingOverview, getApiErrorMessage } from "@/lib/api";
import type { BillingCatalog, BillingOverview } from "@/lib/types";

export default function BillingPage() {
  const [overview, setOverview] = useState<BillingOverview | null>(null);
  const [catalog, setCatalog] = useState<BillingCatalog | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const run = async () => {
      setLoading(true);
      setError(null);
      try {
        const [overviewData, catalogData] = await Promise.all([
          fetchBillingOverview(),
          fetchBillingCatalog(),
        ]);
        setOverview(overviewData);
        setCatalog(catalogData);
      } catch (err: unknown) {
        setError(getApiErrorMessage(err));
      } finally {
        setLoading(false);
      }
    };
    void run();
  }, []);

  return (
    <ProtectedView>
      <div className="min-h-screen bg-transparent text-slate-900">
        <main className="mx-auto w-full max-w-7xl px-6 py-8">
          {loading ? <PageState title="Loading billing" message="Preparing your plan and usage details..." /> : null}
          {error ? <PageState title="Failed to load billing" message={error} /> : null}

          {!loading && !error && overview && catalog ? (
            <div className="space-y-6">
              <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
                <h2 className="text-lg font-semibold text-slate-900">Current Plan</h2>
                <p className="mt-2 text-sm text-slate-600">
                  Plan: <span className="font-semibold">{overview.plan_code}</span> | Account State:{" "}
                  <span className="font-semibold">{overview.account_state}</span>
                </p>
                <p className="mt-1 text-sm text-slate-600">
                  Usage: {overview.usage_count.toLocaleString()} / {overview.included_quota.toLocaleString()} (
                  {overview.usage_percent.toFixed(2)}%)
                </p>
                <p className="mt-1 text-xs text-slate-500">
                  Payment enforcement: {overview.payment_enforcement_enabled ? "Enabled" : "Disabled (non-blocking mode)"}
                </p>
                <div className="mt-4 flex flex-wrap gap-3">
                  <button
                    type="button"
                    className="rounded-md bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-500"
                  >
                    {overview.upgrade_cta}
                  </button>
                  <button
                    type="button"
                    className="rounded-md border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 hover:border-slate-400 hover:bg-slate-50"
                  >
                    {overview.contact_sales_cta}
                  </button>
                </div>
              </section>

              <section className="grid gap-4 md:grid-cols-3">
                {catalog.plans.map((plan) => (
                  <article key={plan.code} className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
                    <h3 className="text-lg font-semibold text-slate-900">{plan.name}</h3>
                    <p className="mt-2 text-sm text-slate-600">
                      ${plan.monthly_price}/month · {plan.included_requests.toLocaleString()} included calls
                    </p>
                    <p className="text-xs text-slate-500">
                      Overage ${plan.overage_price_per_request} per request
                    </p>
                    <ul className="mt-3 space-y-2 text-sm text-slate-600">
                      {plan.features.map((feature) => (
                        <li key={feature}>{feature}</li>
                      ))}
                    </ul>
                    <button
                      type="button"
                      className="mt-4 w-full rounded-md border border-blue-200 px-4 py-2 text-sm font-semibold text-blue-700 hover:bg-blue-50"
                    >
                      {plan.cta}
                    </button>
                  </article>
                ))}
              </section>

              <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
                <h2 className="text-lg font-semibold text-slate-900">FAQ</h2>
                <div className="mt-3 space-y-3">
                  {catalog.faq.map((item) => (
                    <div key={item.q} className="rounded-lg border border-slate-200 bg-slate-50 p-3">
                      <p className="text-sm font-semibold text-slate-900">{item.q}</p>
                      <p className="mt-1 text-sm text-slate-600">{item.a}</p>
                    </div>
                  ))}
                </div>
              </section>
            </div>
          ) : null}
        </main>
      </div>
    </ProtectedView>
  );
}
