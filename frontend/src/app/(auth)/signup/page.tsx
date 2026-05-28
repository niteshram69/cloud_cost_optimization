 "use client"

import Link from "next/link"
import { useRouter } from "next/navigation"
import { type FormEvent, useState } from "react"

import { Button } from "@/components/ui/button"
import { getApiErrorMessage, requestRegistrationOtp } from "@/lib/api"
import { useAuth } from "@/hooks/useAuth"
import type { CloudProvider } from "@/lib/types"

const providerOptions: CloudProvider[] = ["AWS", "AZURE", "GCP", "MULTI"]
const OTP_ENABLED = process.env.NEXT_PUBLIC_OTP_ENABLED === "true"

export default function SignupPage() {
  const router = useRouter()
  const { register } = useAuth()
  const [form, setForm] = useState({
    name: "",
    email: "",
    password: "",
    company_name: "",
    cloud_provider: "MULTI" as CloudProvider,
    otp_code: "",
  })
  const [submitting, setSubmitting] = useState(false)
  const [sendingOtp, setSendingOtp] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  const [otpStatus, setOtpStatus] = useState<string | null>(null)

  const handleRequestOtp = async () => {
    if (!OTP_ENABLED) return
    if (!form.email) {
      setError("Enter your email before requesting OTP.")
      return
    }
    setSendingOtp(true)
    setError(null)
    setOtpStatus(null)
    try {
      const result = await requestRegistrationOtp({ email: form.email })
      const debugOtpLine = result.debug_otp ? ` Dev OTP: ${result.debug_otp}` : ""
      setOtpStatus(`OTP sent. Expires in ${result.expires_in_seconds}s.${debugOtpLine}`)
    } catch (err: unknown) {
      setError(getApiErrorMessage(err))
    } finally {
      setSendingOtp(false)
    }
  }

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setSubmitting(true)
    setError(null)
    setSuccess(null)
    try {
      await register({
        ...form,
        email: form.email.trim().toLowerCase(),
        name: form.name.trim(),
        company_name: form.company_name.trim(),
        otp_code: OTP_ENABLED ? form.otp_code : undefined,
      })
      setSuccess("Account created successfully. Redirecting to login...")
      setTimeout(() => router.push("/login"), 700)
    } catch (err: unknown) {
      setError(getApiErrorMessage(err))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="mx-auto w-full max-w-sm">
      <div className="mb-8">
        <Link href="/" className="inline-block text-2xl font-bold tracking-tight text-brand-900 lg:hidden mb-6">
          Cloud<span className="text-brand-600">teck</span>
        </Link>
        <h2 className="text-2xl font-bold leading-9 tracking-tight text-gray-900">
          Create an account
        </h2>
        <p className="mt-2 text-sm leading-6 text-gray-500">
          Already have an account?{' '}
          <Link href="/login" className="font-semibold text-brand-600 hover:text-brand-500">
            Sign in
          </Link>
        </p>
      </div>

      <div className="mt-8">
        <form className="space-y-5" onSubmit={handleSubmit}>
          <div>
            <label htmlFor="name" className="block text-sm font-medium leading-6 text-gray-900">
              Full Name
            </label>
            <div className="mt-2">
              <input
                id="name"
                name="name"
                type="text"
                autoComplete="name"
                required
                value={form.name}
                onChange={(event) => setForm((prev) => ({ ...prev, name: event.target.value }))}
                className="block w-full rounded-md border-0 py-1.5 text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 placeholder:text-gray-400 focus:ring-2 focus:ring-inset focus:ring-brand-600 sm:text-sm sm:leading-6"
              />
            </div>
          </div>

          <div>
            <label htmlFor="company" className="block text-sm font-medium leading-6 text-gray-900">
              Company Name
            </label>
            <div className="mt-2">
              <input
                id="company"
                name="company"
                type="text"
                required
                value={form.company_name}
                onChange={(event) => setForm((prev) => ({ ...prev, company_name: event.target.value }))}
                className="block w-full rounded-md border-0 py-1.5 text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 placeholder:text-gray-400 focus:ring-2 focus:ring-inset focus:ring-brand-600 sm:text-sm sm:leading-6"
              />
            </div>
          </div>

          <div>
            <label htmlFor="email" className="block text-sm font-medium leading-6 text-gray-900">
              Work Email address
            </label>
            <div className="mt-2">
              <input
                id="email"
                name="email"
                type="email"
                autoComplete="email"
                required
                value={form.email}
                onChange={(event) => setForm((prev) => ({ ...prev, email: event.target.value }))}
                className="block w-full rounded-md border-0 py-1.5 text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 placeholder:text-gray-400 focus:ring-2 focus:ring-inset focus:ring-brand-600 sm:text-sm sm:leading-6"
              />
            </div>
          </div>

          <div>
            <label htmlFor="password" className="block text-sm font-medium leading-6 text-gray-900">
              Password
            </label>
            <div className="mt-2">
              <input
                id="password"
                name="password"
                type="password"
                autoComplete="new-password"
                required
                minLength={8}
                value={form.password}
                onChange={(event) => setForm((prev) => ({ ...prev, password: event.target.value }))}
                className="block w-full rounded-md border-0 py-1.5 text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 placeholder:text-gray-400 focus:ring-2 focus:ring-inset focus:ring-brand-600 sm:text-sm sm:leading-6"
              />
            </div>
          </div>

          <div>
            <label htmlFor="cloud_provider" className="block text-sm font-medium leading-6 text-gray-900">
              Cloud Provider
            </label>
            <div className="mt-2">
              <select
                id="cloud_provider"
                name="cloud_provider"
                value={form.cloud_provider}
                onChange={(event) =>
                  setForm((prev) => ({ ...prev, cloud_provider: event.target.value as CloudProvider }))
                }
                className="block w-full rounded-md border-0 py-1.5 text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 focus:ring-2 focus:ring-inset focus:ring-brand-600 sm:text-sm sm:leading-6"
              >
                {providerOptions.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {OTP_ENABLED ? (
            <div>
              <label htmlFor="otp_code" className="block text-sm font-medium leading-6 text-gray-900">
                OTP Code
              </label>
              <div className="mt-2 flex gap-2">
                <input
                  id="otp_code"
                  name="otp_code"
                  type="text"
                  value={form.otp_code}
                  onChange={(event) => setForm((prev) => ({ ...prev, otp_code: event.target.value }))}
                  minLength={6}
                  maxLength={6}
                  pattern="^\\d{6}$"
                  required
                  className="block w-full rounded-md border-0 py-1.5 text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 focus:ring-2 focus:ring-inset focus:ring-brand-600 sm:text-sm sm:leading-6"
                />
                <Button
                  type="button"
                  variant="outline"
                  onClick={handleRequestOtp}
                  disabled={sendingOtp}
                  className="h-10"
                >
                  {sendingOtp ? "Sending..." : "Send OTP"}
                </Button>
              </div>
            </div>
          ) : (
            <p className="rounded-md border border-gray-200 bg-gray-50 px-3 py-2 text-xs text-gray-500">
              OTP verification is currently disabled for this environment.
            </p>
          )}

          <div className="flex items-center">
            <input
              id="terms"
              name="terms"
              type="checkbox"
              required
              className="h-4 w-4 rounded border-gray-300 text-brand-600 focus:ring-brand-600"
            />
            <label htmlFor="terms" className="ml-2 block text-sm text-gray-900">
              I accept the <Link href="#" className="font-semibold text-brand-600 hover:text-brand-500">Terms of Service</Link> and <Link href="#" className="font-semibold text-brand-600 hover:text-brand-500">Privacy Policy</Link>
            </label>
          </div>

          {error ? (
            <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>
          ) : null}
          {otpStatus ? (
            <p className="rounded-md border border-blue-200 bg-blue-50 px-3 py-2 text-sm text-blue-700">{otpStatus}</p>
          ) : null}
          {success ? (
            <p className="rounded-md border border-green-200 bg-green-50 px-3 py-2 text-sm text-green-700">{success}</p>
          ) : null}

          <div>
            <Button type="submit" className="w-full flex justify-center h-10 mt-6" disabled={submitting}>
              {submitting ? "Creating account..." : "Create Account"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  )
}
