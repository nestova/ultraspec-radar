import { useState, type FormEvent } from 'react'

import type { Market, SavedPropertyInput } from '../types'

interface Props {
  markets: Market[]
  onAdd: (input: SavedPropertyInput) => Promise<boolean>
  onCancel: () => void
}

interface Draft {
  market: string
  address: string
  city: string
  state: string
  zip_code: string
  parcel_id: string
  year_built: string
  lot_size_sqft: string
  estimated_value: string
  owner_name: string
  waterfront: boolean
}

function parseNumber(value: string): number | null {
  if (!value.trim()) return null
  const parsed = Number(value.replace(/,/g, ''))
  return Number.isFinite(parsed) ? parsed : null
}

export function AddPropertyForm({ markets, onAdd, onCancel }: Props) {
  const [draft, setDraft] = useState<Draft>({
    market: markets[0]?.id ?? '',
    address: '',
    city: '',
    state: '',
    zip_code: '',
    parcel_id: '',
    year_built: '',
    lot_size_sqft: '',
    estimated_value: '',
    owner_name: '',
    waterfront: false,
  })
  const [busy, setBusy] = useState(false)

  const set = (field: keyof Draft, value: Draft[keyof Draft]) =>
    setDraft({ ...draft, [field]: value })

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (!draft.address.trim() || !draft.market) return
    setBusy(true)
    try {
      const ok = await onAdd({
        market: draft.market,
        address: draft.address.trim(),
        city: draft.city.trim() || undefined,
        state: draft.state.trim() || undefined,
        zip_code: draft.zip_code.trim() || undefined,
        parcel_id: draft.parcel_id.trim() || undefined,
        year_built: parseNumber(draft.year_built),
        lot_size_sqft: parseNumber(draft.lot_size_sqft),
        estimated_value: parseNumber(draft.estimated_value),
        owner_name: draft.owner_name.trim() || null,
        waterfront: draft.waterfront,
      })
      if (ok) onCancel()
    } finally {
      setBusy(false)
    }
  }

  const field = (
    label: string,
    key: keyof Draft,
    opts: { placeholder?: string } = {},
  ) => (
    <div className="add-field">
      <label htmlFor={`add-${key}`}>{label}</label>
      <input
        id={`add-${key}`}
        className="prop-input"
        value={String(draft[key])}
        placeholder={opts.placeholder}
        onChange={(event) => set(key, event.target.value)}
      />
    </div>
  )

  return (
    <form className="add-form" onSubmit={(event) => void submit(event)}>
      {field('Address *', 'address', { placeholder: '123 Ocean Dr' })}
      <div className="add-field">
        <label htmlFor="add-market">Market *</label>
        <select
          id="add-market"
          className="prop-input"
          value={draft.market}
          onChange={(event) => set('market', event.target.value)}
        >
          {markets.map((market) => (
            <option key={market.id} value={market.id}>
              {market.label}
            </option>
          ))}
        </select>
      </div>
      {field('City', 'city')}
      {field('State', 'state')}
      {field('ZIP', 'zip_code')}
      {field('Parcel ID', 'parcel_id', { placeholder: 'auto if blank' })}
      {field('Year built', 'year_built')}
      {field('Lot (sqft)', 'lot_size_sqft')}
      {field('Est. value', 'estimated_value')}
      {field('Owner', 'owner_name')}
      <label className="add-check">
        <input
          type="checkbox"
          checked={draft.waterfront}
          onChange={(event) => set('waterfront', event.target.checked)}
        />
        Waterfront
      </label>
      <div className="add-actions">
        <button type="button" className="btn btn-sm" onClick={onCancel}>
          Cancel
        </button>
        <button type="submit" className="btn btn-sm btn-primary" disabled={busy}>
          Add property
        </button>
      </div>
    </form>
  )
}
