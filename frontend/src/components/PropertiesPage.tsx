import { useState } from 'react'

import { formatCurrency, formatDateTime } from '../format'
import { AddPropertyForm } from './AddPropertyForm'
import type { ContactUpdate, Market, SavedProperty, SavedPropertyInput } from '../types'

interface Props {
  properties: SavedProperty[]
  markets: Market[]
  onAdd: (input: SavedPropertyInput) => Promise<boolean>
  onUpdate: (parcelId: string, contact: ContactUpdate) => Promise<void>
  onDelete: (parcelId: string) => Promise<void>
}

interface Draft {
  contact_name: string
  contact_phone: string
  contact_email: string
  notes: string
}

function toDraft(property: SavedProperty): Draft {
  return {
    contact_name: property.contact_name ?? '',
    contact_phone: property.contact_phone ?? '',
    contact_email: property.contact_email ?? '',
    notes: property.notes ?? '',
  }
}

function isDirty(property: SavedProperty, draft: Draft): boolean {
  const current = toDraft(property)
  return (
    draft.contact_name !== current.contact_name ||
    draft.contact_phone !== current.contact_phone ||
    draft.contact_email !== current.contact_email ||
    draft.notes !== current.notes
  )
}

function PropertyRow({
  property,
  onUpdate,
  onDelete,
}: {
  property: SavedProperty
  onUpdate: Props['onUpdate']
  onDelete: Props['onDelete']
}) {
  const [draft, setDraft] = useState<Draft>(() => toDraft(property))
  const [busy, setBusy] = useState(false)

  const dirty = isDirty(property, draft)

  const save = async () => {
    setBusy(true)
    try {
      await onUpdate(property.parcel_id, draft)
    } finally {
      setBusy(false)
    }
  }

  const remove = async () => {
    if (!window.confirm(`Remove ${property.address} from saved properties?`)) return
    setBusy(true)
    try {
      await onDelete(property.parcel_id)
    } finally {
      setBusy(false)
    }
  }

  return (
    <tr>
      <td>
        <strong>{property.address}</strong>
        <small className="prop-sub">
          {property.city}, {property.state} · {property.market}
        </small>
        {property.waterfront && <span className="tag tag-water">waterfront</span>}
      </td>
      <td>{property.owner_name}</td>
      <td className="mono">{formatCurrency(property.estimated_value)}</td>
      <td className="mono">{property.year_built ?? '—'}</td>
      <td>
        <input
          className="prop-input"
          aria-label="Contact name"
          value={draft.contact_name}
          onChange={(event) => setDraft({ ...draft, contact_name: event.target.value })}
        />
      </td>
      <td>
        <input
          className="prop-input"
          aria-label="Contact phone"
          value={draft.contact_phone}
          onChange={(event) => setDraft({ ...draft, contact_phone: event.target.value })}
        />
      </td>
      <td>
        <input
          className="prop-input"
          aria-label="Contact email"
          value={draft.contact_email}
          onChange={(event) => setDraft({ ...draft, contact_email: event.target.value })}
        />
      </td>
      <td>
        <input
          className="prop-input prop-notes"
          aria-label="Notes"
          value={draft.notes}
          onChange={(event) => setDraft({ ...draft, notes: event.target.value })}
        />
      </td>
      <td className="row-actions">
        <button type="button" className="btn btn-sm" disabled={!dirty || busy} onClick={() => void save()}>
          {dirty ? 'Save' : 'Saved'}
        </button>
        <button type="button" className="btn btn-sm" disabled={busy} onClick={() => void remove()}>
          Remove
        </button>
      </td>
    </tr>
  )
}

export function PropertiesPage({ properties, markets, onAdd, onUpdate, onDelete }: Props) {
  const [adding, setAdding] = useState(false)

  return (
    <div className="props-page">
      <div className="props-head">
        <h2>Saved properties</h2>
        <small>{properties.length} tracked · contact edits save per row</small>
        <button type="button" className="btn btn-sm" onClick={() => setAdding(true)}>
          + Add property
        </button>
      </div>
      {adding && <AddPropertyForm markets={markets} onAdd={onAdd} onCancel={() => setAdding(false)} />}
      {properties.length === 0 ? (
        !adding && (
          <div className="empty">
            <h3>No saved properties yet</h3>
            <p>Run a scan and hit “Save” on candidate rows — or add one manually with the button above.</p>
          </div>
        )
      ) : (
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th scope="col">Address</th>
              <th scope="col">Owner</th>
              <th scope="col">Est. value</th>
              <th scope="col">Built</th>
              <th scope="col">Contact name</th>
              <th scope="col">Phone</th>
              <th scope="col">Email</th>
              <th scope="col">Notes</th>
              <th scope="col">Actions</th>
            </tr>
          </thead>
          <tbody>
            {properties.map((property) => (
              <PropertyRow key={property.parcel_id} property={property} onUpdate={onUpdate} onDelete={onDelete} />
            ))}
          </tbody>
        </table>
      </div>
      )}
      {properties.length > 0 && (
        <small className="props-updated">
          Last change {formatDateTime(properties[0].updated_at)}
        </small>
      )}
    </div>
  )
}
