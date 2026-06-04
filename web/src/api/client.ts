const API_ROOT = (import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000').replace(/\/+$/, '')

export const apiRoot = API_ROOT.endsWith('/api') ? API_ROOT.slice(0, -4) : API_ROOT
