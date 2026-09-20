import { useCallback, useEffect, useMemo, useState } from 'react'

import './App.css'
import {
  deleteProperty,
  downloadCsv,
  fetchDefaults,
  fetchMarkets,
  fetchProperties,
  fetchRuns,
  fetchSavedRun,
  runSearch,
  saveProperty,
  updatePropertyContacts,
} from './api'
import { CandidateTable } from './components/CandidateTable'
import { ClusterMap } from './components/ClusterMap'
import { ControlRail } from './components/ControlRail'
import { PropertiesPage } from './components/PropertiesPage'
import { formatCurrency, formatDateTime } from './format'
import type {
  ContactUpdate,
  Market,
  Parcel,
  RunResult,
  SavedProperty,
  SavedRun,
  SearchConfig,
} from './types'

type View = 'scan' | 'properties'

export default function App() {
  const [defaults, setDefaults] = useState<SearchConfig | null>(null)
  const [config, setConfig] = useState<SearchConfig | null>(null)
  const [markets, setMarkets] = useState<Market[]>([])
  const [runs, setRuns] = useState<SavedRun[]>([])
  const [result, setResult] = useState<RunResult | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [view, setView] = useState<View>('scan')
  const [properties, setProperties] = useState<SavedProperty[]>([])

  const refreshRuns = useCallback(() => {
    fetchRuns()
      .then(setRuns)
      .catch((err: Error) => setError(err.message))
  }, [])

  const refreshProperties = useCallback(() => {
    fetchProperties()
      .then(setProperties)
      .catch((err: Error) => setError(err.message))
  }, [])

  useEffect(() => {
    Promise.all([fetchDefaults(), fetchMarkets()])
      .then(([defaultConfig, marketList]) => {
        setDefaults(defaultConfig)
        setConfig(defaultConfig)
        setMarkets(marketList)
      })
      .catch((err: Error) => setError(err.message))
    refreshRuns()
    refreshProperties()
  }, [refreshRuns, refreshProperties])

  const run = useCallback(
    async (next: SearchConfig) => {
      setBusy(true)
      setError(null)
      try {
        const data = await runSearch(next)
        setResult(data)
        setSelectedId(data.clusters[0]?.id ?? null)
        refreshRuns()
      } catch (err) {
        setError((err as Error).message)
        setResult(null)
      } finally {
        setBusy(false)
      }
    },
    [refreshRuns],
  )

  const loadRun = useCallback(async (saved: SavedRun) => {
    setError(null)
    try {
      const data = await fetchSavedRun(saved.id)
      setResult(data)
      setConfig(data.summary.config)
      setSelectedId(data.clusters[0]?.id ?? null)
    } catch (err) {
      setError((err as Error).message)
    }
  }, [])

  const saveCandidate = useCallback(
    async (parcel: Parcel) => {
      if (!config) return
      try {
        await saveProperty({ ...parcel, market: config.market })
        refreshProperties()
      } catch (err) {
        setError((err as Error).message)
      }
    },
    [config, refreshProperties],
  )

  const updateContacts = useCallback(async (parcelId: string, contact: ContactUpdate) => {
    try {
      await updatePropertyContacts(parcelId, contact)
      refreshProperties()
    } catch (err) {
      setError((err as Error).message)
    }
  }, [refreshProperties])

  const removeProperty = useCallback(async (parcelId: string) => {
    try {
      await deleteProperty(parcelId)
      refreshProperties()
    } catch (err) {
      setError((err as Error).message)
    }
  }, [refreshProperties])

  const savedIds = useMemo(
    () => new Set(properties.map((property) => property.parcel_id)),
    [properties],
  )

  const selected = useMemo(
    () => result?.clusters.find((cluster) => cluster.id === selectedId) ?? null,
    [result, selectedId],
  )

  const reviewCount = result?.summary.review_queue.length ?? 0

  if (!config) {
    return (
      <div className="empty">
        <h3>{error ? 'Cannot reach the API' : 'Loading UltraSpec Radar…'}</h3>
        {error && <p>{error}</p>}
      </div>
    )
  }

  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand">
          <h1>UltraSpec Radar</h1>
          <span>New-construction clusters &amp; adjacent teardown targets</span>
        </div>
        <nav className="tabs" aria-label="Views">
          <button type="button" className="tab" aria-current={view === 'scan'} onClick={() => setView('scan')}>
            Radar
          </button>
          <button
            type="button"
            className="tab"
            aria-current={view === 'properties'}
            onClick={() => setView('properties')}
          >
            Properties ({properties.length})
          </button>
        </nav>
        <dl className="topbar-stats">
          <div className="stat">
            <dt>Anchors</dt>
            <dd>{result?.summary.anchors_found ?? '—'}</dd>
          </div>
          <div className="stat">
            <dt>Clusters</dt>
            <dd>{result?.summary.clusters_found ?? '—'}</dd>
          </div>
          <div className="stat">
            <dt>Parcels scanned</dt>
            <dd>{result?.summary.parcels_scanned ?? '—'}</dd>
          </div>
          <div className="stat">
            <dt>Candidates</dt>
            <dd>{result?.summary.candidates_returned ?? '—'}</dd>
          </div>
          <div className="stat">
            <dt>Needs review</dt>
            <dd>{result ? reviewCount : '—'}</dd>
          </div>
          <div className="stat">
            <dt>Generated</dt>
            <dd>{result ? formatDateTime(result.summary.generated_at) : '—'}</dd>
          </div>
        </dl>
      </header>

      {error && <p className="notice">{error}</p>}
      {result && result.summary.stale_sources.length > 0 && (
        <p className="notice">
          Data older than {config.max_data_age_days} days from: {result.summary.stale_sources.join(', ')}.
          Re-ingest before using these records for outreach.
        </p>
      )}

      {view === 'properties' ? (
        <div className="props-wrap">
          <PropertiesPage
            properties={properties}
            onUpdate={updateContacts}
            onDelete={removeProperty}
          />
        </div>
      ) : (
      <div className="layout">
        <ControlRail
          config={config}
          markets={markets}
          runs={runs}
          busy={busy}
          canExport={Boolean(result && result.summary.candidates_returned > 0)}
          onChange={(patch) => setConfig({ ...config, ...patch })}
          onRun={() => void run(config)}
          onExport={() => void downloadCsv(config).catch((err: Error) => setError(err.message))}
          onReset={() => defaults && setConfig(defaults)}
          onLoadRun={(saved) => void loadRun(saved)}
        />

        <main className="main">
          <ClusterMap
            clusters={result?.clusters ?? []}
            selected={selected}
            config={config}
            onSelectCluster={setSelectedId}
          />

          <section className="results">
            <div className="cluster-list">
              {!result && (
                <div className="empty">
                  <h3>Nothing scanned yet</h3>
                  <p>Set your thresholds and run a scan.</p>
                </div>
              )}
              {result?.clusters.length === 0 && (
                <div className="empty">
                  <h3>No clusters found</h3>
                  <p>Widen the cluster radius or allow lone anchors.</p>
                </div>
              )}
              {result?.clusters.map((cluster) => (
                <button
                  key={cluster.id}
                  type="button"
                  className="cluster-item"
                  aria-current={cluster.id === selectedId}
                  onClick={() => setSelectedId(cluster.id)}
                >
                  <strong>
                    {cluster.anchors[0].city}
                    {cluster.is_singleton ? ' (lone anchor)' : ''}
                  </strong>
                  <small>
                    {cluster.anchors.length} anchor{cluster.anchors.length === 1 ? '' : 's'} ·{' '}
                    {cluster.candidates.length} candidates
                  </small>
                  <small>avg {formatCurrency(cluster.avg_anchor_price)}</small>
                </button>
              ))}
            </div>
            <CandidateTable
              cluster={selected}
              savedIds={savedIds}
              onSave={(parcel) => void saveCandidate(parcel)}
            />
          </section>
        </main>
      </div>
      )}
    </div>
  )
}
