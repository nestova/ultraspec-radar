import type { Cluster } from '../types'
import { formatCurrency, formatFeet, formatNumber } from '../format'

interface Props {
  cluster: Cluster | null
}

export function CandidateTable({ cluster }: Props) {
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
            <th scope="col">Developer fit</th>
            <th scope="col">Parcel</th>
            <th scope="col">Records</th>
          </tr>
        </thead>
        <tbody>
          {cluster.candidates.map((candidate, index) => (
            <tr key={candidate.parcel.parcel_id}>
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
              <td>
                {(() => {
                  const best = candidate.developer_matches?.[0]
                  if (!best) return '—'
                  return (
                    <span className="dev-match" title={best.rationale}>
                      <strong>{best.developer}</strong>
                      <span className="mono">up to {formatCurrency(best.max_offer)}</span>
                    </span>
                  )
                })()}
              </td>
              <td className="mono">{candidate.parcel.parcel_id}</td>
              <td>
                {candidate.parcel.assessor_url && (
                  <a href={candidate.parcel.assessor_url} target="_blank" rel="noreferrer">
                    assessor
                  </a>
                )}
                {candidate.parcel.zillow_url && (
                  <>
                    {' · '}
                    <a href={candidate.parcel.zillow_url} target="_blank" rel="noreferrer">
                      zillow
                    </a>
                  </>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
