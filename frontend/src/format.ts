const currency = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  maximumFractionDigits: 0,
})

const number = new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 })

export function formatCurrency(value: number | null | undefined): string {
  return value == null ? '—' : currency.format(value)
}

export function formatNumber(value: number | null | undefined): string {
  return value == null ? '—' : number.format(value)
}

export function formatFeet(value: number | null | undefined): string {
  return value == null ? '—' : `${number.format(value)} ft`
}

export function formatDateTime(value: string): string {
  return new Date(value).toLocaleString('en-US', { dateStyle: 'medium', timeStyle: 'short' })
}
