import axios from 'axios'

const API_ROOT = (import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000').replace(/\/+$/, '')
const baseURL = API_ROOT.endsWith('/api') ? API_ROOT : `${API_ROOT}/api`

export const apiClient = axios.create({
  baseURL,
  timeout: 10000,
})

export const apiRoot = API_ROOT.endsWith('/api') ? API_ROOT.slice(0, -4) : API_ROOT
