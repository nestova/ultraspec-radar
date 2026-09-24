import { useState } from 'react'
import type { Cluster, OwnerContact } from '../types'
import { formatCurrency, formatFeet, formatNumber } from '../format'
import { skipTrace } from '../api'

interface Props {
  cluster: Cluster | null
}

export function CandidateTable({ cluster }: Props) {
  const [contacts, setContacts] = useState<Record<string, OwnerContact>>({})
  const [tracing, setTracing] = useState<Set<string>>(new Set())
  const [errors, setErrors] = useState<Record<string, string>>({})

  if (!cluster) {
    return (
      <div className="empty">
        <h3>No cluster selected</h3>
        <p>Pick a cluster to see its ranked teardown and value-gap candidates.</p>
      </div>
    )
  }

  if (cluster.candidates.length === 0) {
    return (
      <div className="empty">
        <h3>No candidates survived the filters</h3>
        <p>
          Every nearby parcel was too new, too expensive, or corporate-owned. Loosen the value ceiling, move
          the age cutoff, or widen the search radius.
        </p>
      </div>
    )
  }

  const handleSkipTrace = async (candidate: (typeof cluster.candidates)[0]) => {
    const parcelId = candidate.parcel.parcel_id
    setTracing((prev) => new Set(prev).add(parcelId))
    setErrors((prev) => {
      const next = { ...prev }
      delete next[parcelId]
      return next
    })
    try {
      const contact = await skipTrace(
        parcelId,
        candidate.parcel.address,
        candidate.parcel.city,
        candidate.parcel.state,
        candidate.parcel.zip_code,
      )
      setContacts((prev) => ({ ...prev, [parcelId]: contact }))
    } catch (err) {
      setErrors((prev) => ({ ...prev, [parcelId]: (err as Error).message }))
    } finally {
      setTracing((prev) => {
        const next = new Set(prev)
        next.delete(parcelId)
        return next
      })
    }
  }

  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th scope="col">#</th>
            <th scope="col">Address</th>
            <th scope="col">Owner</th>
            <th scope="col">Type</th>
            <th scope="col">Built</th>
            <th scope="col">Lot (sqft)</th>
            <th scope="col">Est. value</th>
            <th scope="col">Value gap</th>
            <th scope="col">To anchor</th>
            <th scope="col">Score</th>
            <th scope="col">Phone</th>
            <th scope="col">Email</th>
            <th scope="col">Skip Trace</th>
          </tr>
        </thead>
        <tbody>
          {cluster.candidates.map((candidate, index) => {
            const parcelId = candidate.parcel.parcel_id
            const contact = contacts[parcelId]
            const isTracing = tracing.has(parcelId)
            const error = errors[parcelId]

            return (
              <tr key={parcelId}>
                <td className="rank">{index + 1}</td>
                <td>{candidate.parcel.address}</td>
                <td>{candidate.parcel.owner_name}</td>
                <td>
                  <span className={`tag ${candidate.ownership.ownership_type === 'trust' ? 'tag-trust' : ''}`}>
                    {candidate.ownership.ownership_type}
                  </span>
                  {candidate.ownership.needs_review && <span className="tag tag-review">review</span>}
                </td>
                <td className="mono">{candidate.parcel.year_built}</td>
                <td className="mono">{formatNumber(candidate.parcel.lot_size_sqft)}</td>
                <td className="mono">{formatCurrency(candidate.parcel.estimated_value)}</td>
                <td className="mono">{formatCurrency(candidate.value_gap)}</td>
                <td className="mono">{formatFeet(candidate.distance_to_anchor_ft)}</td>
                <td className="mono">{candidate.score.toFixed(3)}</td>
                <td className="mono">
                  {contact?.phones.length ? contact.phones.join(', ') : '—'}
                </td>
                <td className="mono">
                  {contact?.emails.length ? contact.emails.join(', ') : '—'}
                </td>
                <td>
                  <button
                    type="button"
                    className="skip-trace-btn"
                    disabled={isTracing || !!contact}
                    onClick={() => void handleSkipTrace(candidate)}
                  >
                    {isTracing ? 'Tracing…' : contact ? 'Done' : error ? 'Retry' : 'Skip Trace'}
                  </button>
                  {error && <span className="skip-trace-error">{error}</span>}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
