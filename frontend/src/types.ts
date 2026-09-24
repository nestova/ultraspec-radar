export interface SearchConfig {
  market: string
  anchor_min_price: number
  anchor_min_year_built: number
  cluster_radius_miles: number
  cluster_min_members: number
  allow_singleton_clusters: boolean
  adjacent_radius_feet: number
  candidate_max_value: number
  candidate_max_year_built: number
  exclude_corporate_owners: boolean
  include_trusts: boolean
  weight_proximity: number
  weight_value_gap: number
  weight_lot_size: number
  max_candidates_per_cluster: number
  max_data_age_days: number
}

export interface Provenance {
  source: string
  source_url: string | null
  retrieved_at: string
}

export interface AnchorHome {
  id: string
  address: string
  city: string
  state: string
  zip_code: string
  lat: number
  lon: number
  price: number
  status: 'listed' | 'under_contract' | 'sold'
  year_built: number
  builder: string | null
  parcel_id: string | null
  listing_url: string | null
  provenance: Provenance
}

export interface Parcel {
  parcel_id: string
  address: string
  city: string
  state: string
  zip_code: string
  lat: number
  lon: number
  year_built: number | null
  lot_size_sqft: number | null
  estimated_value: number | null
  owner_name: string | null
  assessor_url: string | null
  zillow_url: string | null
  provenance: Provenance
}

export interface OwnershipClassification {
  owner_name: string
  ownership_type: 'individual' | 'trust' | 'corporate' | 'government' | 'unknown'
  confidence: number
  matched_rule: string
  needs_review: boolean
}

export interface Candidate {
  parcel: Parcel
  ownership: OwnershipClassification
  nearest_anchor_id: string
  distance_to_anchor_ft: number
  value_gap: number
  score: number
  score_breakdown: Record<string, number>
}

export interface Cluster {
  id: string
  anchor_ids: string[]
  anchors: AnchorHome[]
  centroid_lat: number
  centroid_lon: number
  bbox: [number, number, number, number]
  avg_anchor_price: number
  is_singleton: boolean
  candidates: Candidate[]
}

export interface RunSummary {
  market: string
  generated_at: string
  config: SearchConfig
  anchors_found: number
  clusters_found: number
  parcels_scanned: number
  candidates_returned: number
  stale_sources: string[]
  review_queue: OwnershipClassification[]
}

export interface RunResult {
  summary: RunSummary
  clusters: Cluster[]
}

export interface OwnerContact {
  parcel_id: string | null
  owner_name: string | null
  phones: string[]
  emails: string[]
}

export interface Market {
  id: string
  label: string
}
