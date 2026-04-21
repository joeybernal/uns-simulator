import { useState } from 'react'
import { useAuthStore } from '../../store/auth.store.js'

export default function LoginPage() {
  const login = useAuthStore((s) => s.login)
  const [key, setKey]       = useState('')
  const [error, setError]   = useState('')
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e) {
    e.preventDefault()
    if (!key.trim()) return
    setLoading(true)
    setError('')
    const result = await login(key.trim())
    setLoading(false)
    if (!result.ok) setError(result.error)
  }

  return (
    <div className="min-h-screen bg-gray-950 flex items-center justify-center px-4">
      <div className="w-full max-w-sm">
        {/* Logo */}
        <div className="flex items-center gap-3 mb-8 justify-center">
          <div className="w-9 h-9 rounded-xl bg-brand-600 flex items-center justify-center">
            <i className="fa-solid fa-tower-broadcast text-white text-sm" />
          </div>
          <div>
            <div className="text-white font-bold text-base leading-none">UNS Simulator</div>
            <div className="text-gray-500 text-xs mt-0.5">IoTAuto GmbH</div>
          </div>
        </div>

        {/* Card */}
        <div className="bg-gray-900 border border-gray-800 rounded-2xl p-6 shadow-xl">
          <h1 className="text-white font-semibold text-lg mb-1">Sign in</h1>
          <p className="text-gray-400 text-sm mb-5">Enter your API key to access the simulator.</p>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1.5">API Key</label>
              <input
                type="password"
                value={key}
                onChange={(e) => setKey(e.target.value)}
                placeholder="••••••••••••••••"
                autoComplete="current-password"
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2.5
                           text-white text-sm placeholder-gray-600
                           focus:outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500
                           transition-colors"
              />
            </div>

            {error && (
              <p className="text-red-400 text-xs flex items-center gap-1.5">
                <i className="fa-solid fa-circle-xmark" />
                {error}
              </p>
            )}

            <button
              type="submit"
              disabled={loading || !key.trim()}
              className="w-full bg-brand-600 hover:bg-brand-700 disabled:opacity-50 disabled:cursor-not-allowed
                         text-white font-medium text-sm py-2.5 rounded-lg transition-colors
                         flex items-center justify-center gap-2"
            >
              {loading && <i className="fa-solid fa-spinner fa-spin text-xs" />}
              {loading ? 'Signing in…' : 'Sign in'}
            </button>
          </form>
        </div>

        <p className="text-center text-gray-600 text-xs mt-6">
          Need access? Contact your IoT platform admin.
        </p>
      </div>
    </div>
  )
}
