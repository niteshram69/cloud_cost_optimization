"use client"

import Link from "next/link"
import { useRouter } from "next/navigation"
import { type FormEvent, useState } from "react"

import { Button } from "@/components/ui/button"
import { confirmPasswordReset, getApiErrorMessage, requestPasswordResetOtp } from "@/lib/api"

const OTP_ENABLED = process.env.NEXT_PUBLIC_OTP_ENABLED === "true"

export default function ResetPasswordPage() {
  const router = useRouter()
  const [form, setForm] = useState({
    email: "",
    otp_code: "",
    new_password: "",
  })
  const [sendingOtp, setSendingOtp] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [status, setStatus] = useState<string | null>(null)

  const handleRequestOtp = async () => {
    if (!OTP_ENABLED) return
    if (!form.email) {
      setError("Enter your email before requesting OTP.")
      return
    }

    setSendingOtp(true)
    setError(null)
    setStatus(null)
    try {
      const result = await requestPasswordResetOtp({ email: form.email })
      const debugOtpLine = result.debug_otp ? ` Dev OTP: ${result.debug_otp}` : ""
      setStatus(`OTP sent. Expires in ${result.expires_in_seconds}s.${debugOtpLine}`)
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
    setStatus(null)

    try {
      await confirmPasswordReset({
        ...form,
        otp_code: OTP_ENABLED ? form.otp_code : undefined,
      })
      setStatus("Password reset successful. Redirecting to login...")
      setTimeout(() => router.push("/login"), 700)
    } catch (err: unknown) {
      setError(getApiErrorMessage(err))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="mx-auto w-full max-w-sm">
      <div>
        <h2 className="mt-8 text-2xl font-bold leading-9 tracking-tight text-gray-900">
          Reset password
        </h2>
        <p className="mt-2 text-sm leading-6 text-gray-500">
          Verify with OTP and set a new password.
        </p>
      </div>

      <div className="mt-10">
        <form className="space-y-6" onSubmit={handleSubmit}>
          <div>
            <label htmlFor="email" className="block text-sm font-medium leading-6 text-gray-900">
              Email address
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

          <div>
            <label htmlFor="new_password" className="block text-sm font-medium leading-6 text-gray-900">
              New Password
            </label>
            <div className="mt-2">
              <input
                id="new_password"
                name="new_password"
                type="password"
                required
                minLength={8}
                value={form.new_password}
                onChange={(event) => setForm((prev) => ({ ...prev, new_password: event.target.value }))}
                className="block w-full rounded-md border-0 py-1.5 text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 placeholder:text-gray-400 focus:ring-2 focus:ring-inset focus:ring-brand-600 sm:text-sm sm:leading-6"
              />
            </div>
          </div>

          {error ? (
            <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>
          ) : null}
          {status ? (
            <p className="rounded-md border border-blue-200 bg-blue-50 px-3 py-2 text-sm text-blue-700">{status}</p>
          ) : null}

          <div>
            <Button type="submit" className="w-full flex justify-center h-10" disabled={submitting}>
              {submitting ? "Resetting..." : "Reset password"}
            </Button>
          </div>
        </form>

        <p className="mt-6 text-sm text-gray-500">
          Back to{" "}
          <Link href="/login" className="font-semibold text-brand-600 hover:text-brand-500">
            Sign in
          </Link>
        </p>
      </div>
    </div>
  )
}
