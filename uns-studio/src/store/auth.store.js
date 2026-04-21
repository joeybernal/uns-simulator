import { create } from 'zustand'
import { persist } from 'zustand/middleware'

const API_KEY_STORAGE = 'uns-sim-api-key'

export const useAuthStore = create(
  persist(
    (set, get) => ({
      apiKey: null,
      authed: false,

      /** Try the given key against the server health endpoint */
      login: async (key) => {
        try {
          const res = await fetch('/health', {
            headers: { 'X-API-Key': key },
          })
          if (res.ok) {
            set({ apiKey: key, authed: true })
            return { ok: true }
          }
          if (res.status === 401 || res.status === 403) {
            return { ok: false, error: 'Invalid API key' }
          }
          return { ok: false, error: `Server returned ${res.status}` }
        } catch (err) {
          return { ok: false, error: 'Could not reach server' }
        }
      },

      logout: () => set({ apiKey: null, authed: false }),
    }),
    {
      name: API_KEY_STORAGE,
      partialize: (s) => ({ apiKey: s.apiKey, authed: s.authed }),
    }
  )
)
