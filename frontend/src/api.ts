import type { Market, OwnerContact, RunResult, SearchConfig } from './types'

async function parseError(response: Response): Promise<never> {
  let detail = `Request failed (${response.status})`
  try {
    const body = await response.json()
    if (body?.detail) detail = String(body.detail)
  } catch {
    // response had no JSON body; keep the status-based message
  }
  throw new Error(detail)
}

export async function fetchMarkets(): Promise<Market[]> {
  const response = await fetch('/api/markets')
  if (!response.ok) await parseError(response)
  return response.json()
}

export async function fetchDefaults(): Promise<SearchConfig> {
  const response = await fetch('/api/config/defaults')
  if (!response.ok) await parseError(response)
  return response.json()
}

export async function runSearch(config: SearchConfig): Promise<RunResult> {
  const response = await fetch('/api/run', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(config),
  })
  if (!response.ok) await parseError(response)
  return response.json()
}

export async function skipTrace(
  parcelId: string | null,
  address: string,
  city: string,
  state: string,
  zipCode: string,
): Promise<OwnerContact> {
  const response = await fetch('/api/skip-trace', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      parcel_id: parcelId,
      address,
      city,
      state,
      zip_code: zipCode,
    }),
  })
  if (!response.ok) await parseError(response)
  return response.json()
}

export async function downloadCsv(config: SearchConfig): Promise<void> {
  const response = await fetch('/api/run/export.csv', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(config),
  })
  if (!response.ok) await parseError(response)
  const blob = await response.blob()
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `ultraspec-${config.market}.csv`
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}
