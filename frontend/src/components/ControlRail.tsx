import { formatDateTime } from '../format'
import type { Market, SavedRun, SearchConfig } from '../types'

interface Props {
  config: SearchConfig
  markets: Market[]
  runs: SavedRun[]
  busy: boolean
  canExport: boolean
  onChange: (patch: Partial<SearchConfig>) => void
  onRun: () => void
  onExport: () => void
  onReset: () => void
  onLoadRun: (run: SavedRun) => void
}

type NumericKey = {
  [K in keyof SearchConfig]: SearchConfig[K] extends number ? K : never
}[keyof SearchConfig]

export function ControlRail({
  config,
  markets,
  runs,
  busy,
  canExport,
  onChange,
  onRun,
  onExport,
  onReset,
  onLoadRun,
}: Props) {
  const numberField = (key: NumericKey, label: string, step = 1) => (
    <div className="field" key={key}>
      <label htmlFor={key}>{label}</label>
      <input
        id={key}
        type="number"
        step={step}
        value={config[key]}
        onChange={(event) => onChange({ [key]: Number(event.target.value) } as Partial<SearchConfig>)}
      />
    </div>
  )

  return (
    <aside className="rail">
      <section>
        <h2>Market</h2>
        <div className="field">
          <label htmlFor="market">Pilot market</label>
          <select
            id="market"
            value={config.market}
            onChange={(event) => onChange({ market: event.target.value })}
          >
            {markets.map((market) => (
              <option key={market.id} value={market.id}>
                {market.label}
              </option>
            ))}
          </select>
        </div>
      </section>

      <section>
        <h2>Anchor homes</h2>
        {numberField('anchor_min_price', 'Minimum price ($)', 250000)}
        {numberField('anchor_min_year_built', 'Built in or after')}
      </section>

      <section>
        <h2>Clustering</h2>
        {numberField('cluster_radius_miles', 'Cluster radius (mi)', 0.05)}
        {numberField('cluster_min_members', 'Minimum anchors per cluster')}
        <div className="field-inline">
          <input
            id="allow_singleton_clusters"
            type="checkbox"
            checked={config.allow_singleton_clusters}
            onChange={(event) => onChange({ allow_singleton_clusters: event.target.checked })}
          />
          <label htmlFor="allow_singleton_clusters">Keep lone anchors as clusters</label>
        </div>
      </section>

      <section>
        <h2>Candidate filters</h2>
        {numberField('adjacent_radius_feet', 'Search radius (ft)', 50)}
        {numberField('candidate_max_value', 'Maximum value ($)', 50000)}
        {numberField('candidate_max_year_built', 'Built in or before')}
        <div className="field-inline">
          <input
            id="include_trusts"
            type="checkbox"
            checked={config.include_trusts}
            onChange={(event) => onChange({ include_trusts: event.target.checked })}
          />
          <label htmlFor="include_trusts">Include trust-owned parcels</label>
        </div>
        <div className="field-inline">
          <input
            id="exclude_corporate_owners"
            type="checkbox"
            checked={config.exclude_corporate_owners}
            onChange={(event) => onChange({ exclude_corporate_owners: event.target.checked })}
          />
          <label htmlFor="exclude_corporate_owners">Exclude LLC / corporate owners</label>
        </div>
      </section>

      <section>
        <h2>Ranking weights</h2>
        {numberField('weight_proximity', 'Proximity', 0.05)}
        {numberField('weight_value_gap', 'Value gap', 0.05)}
        {numberField('weight_lot_size', 'Lot size', 0.05)}
        {numberField('max_candidates_per_cluster', 'Candidates per cluster')}
        {numberField('max_data_age_days', 'Freshness limit (days)')}
      </section>

      <div className="actions">
        <button className="btn btn-primary" onClick={onRun} disabled={busy}>
          {busy ? 'Scanning…' : 'Run scan'}
        </button>
        <button className="btn" onClick={onExport} disabled={busy || !canExport}>
          Export CSV
        </button>
        <button className="btn" onClick={onReset} disabled={busy}>
          Reset to defaults
        </button>
      </div>

      <section>
        <h2>Saved runs</h2>
        {runs.length === 0 && <p className="runs-empty">Every scan is saved here automatically.</p>}
        <ul className="run-list">
          {runs.map((run) => (
            <li key={run.id}>
              <button type="button" className="run-item" onClick={() => onLoadRun(run)}>
                <strong>{formatDateTime(run.created_at)}</strong>
                <small>
                  {run.clusters_found} cluster{run.clusters_found === 1 ? '' : 's'} · {run.anchors_found}{' '}
                  anchor{run.anchors_found === 1 ? '' : 's'} · {run.candidates_returned} candidate
                  {run.candidates_returned === 1 ? '' : 's'}
                </small>
                <small>{run.listing_source}</small>
              </button>
            </li>
          ))}
        </ul>
      </section>
    </aside>
  )
}
