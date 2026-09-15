import { useEffect } from 'react'
import { Circle, CircleMarker, MapContainer, Popup, TileLayer, useMap } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'

import type { Cluster, SearchConfig } from '../types'
import { formatCurrency, formatFeet } from '../format'

interface Props {
  clusters: Cluster[]
  selected: Cluster | null
  config: SearchConfig
  onSelectCluster: (clusterId: string) => void
}

function ViewSync({ selected, clusters }: { selected: Cluster | null; clusters: Cluster[] }) {
  const map = useMap()

  useEffect(() => {
    if (selected) {
      const [minLat, minLon, maxLat, maxLon] = selected.bbox
      map.fitBounds(
        [
          [minLat, minLon],
          [maxLat, maxLon],
        ],
        { padding: [64, 64], maxZoom: 16 },
      )
      return
    }
    if (clusters.length > 0) {
      map.fitBounds(
        clusters.map((cluster) => [cluster.centroid_lat, cluster.centroid_lon] as [number, number]),
        { padding: [48, 48], maxZoom: 13 },
      )
    }
  }, [map, selected, clusters])

  return null
}

export function ClusterMap({ clusters, selected, config, onSelectCluster }: Props) {
  const visible = selected ? [selected] : clusters
  const center: [number, number] = clusters.length
    ? [clusters[0].centroid_lat, clusters[0].centroid_lon]
    : [25.79, -80.14]

  return (
    <div className="map-panel">
      <MapContainer center={center} zoom={12} scrollWheelZoom>
        <TileLayer
          url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
          attribution="&copy; OpenStreetMap contributors"
        />
        <ViewSync selected={selected} clusters={clusters} />

        {visible.map((cluster) =>
          cluster.anchors.map((anchor) => (
            <div key={anchor.id}>
              <Circle
                center={[anchor.lat, anchor.lon]}
                radius={config.adjacent_radius_feet * 0.3048}
                pathOptions={{ color: '#d9a441', weight: 1, dashArray: '4 4', fillOpacity: 0.05 }}
              />
              <CircleMarker
                center={[anchor.lat, anchor.lon]}
                radius={8}
                pathOptions={{ color: '#d9a441', fillColor: '#d9a441', fillOpacity: 0.85, weight: 1 }}
                eventHandlers={{ click: () => onSelectCluster(cluster.id) }}
              >
                <Popup>
                  <strong>{anchor.address}</strong>
                  <br />
                  {formatCurrency(anchor.price)} · built {anchor.year_built} · {anchor.status.replace('_', ' ')}
                </Popup>
              </CircleMarker>
            </div>
          )),
        )}

        {visible.map((cluster) =>
          cluster.candidates.map((candidate) => (
            <CircleMarker
              key={`${cluster.id}-${candidate.parcel.parcel_id}`}
              center={[candidate.parcel.lat, candidate.parcel.lon]}
              radius={6}
              pathOptions={{ color: '#4ec3c0', fillColor: '#4ec3c0', fillOpacity: 0.8, weight: 1 }}
              eventHandlers={{ click: () => onSelectCluster(cluster.id) }}
            >
              <Popup>
                <strong>{candidate.parcel.address}</strong>
                <br />
                {candidate.parcel.owner_name} · {candidate.ownership.ownership_type}
                <br />
                {formatCurrency(candidate.parcel.estimated_value)} · built {candidate.parcel.year_built} ·{' '}
                {formatFeet(candidate.distance_to_anchor_ft)} from anchor
              </Popup>
            </CircleMarker>
          )),
        )}
      </MapContainer>

      <div className="legend">
        <span>
          <i className="swatch swatch-anchor" /> $15M+ new construction
        </span>
        <span>
          <i className="swatch swatch-candidate" /> Ranked candidate parcel
        </span>
      </div>
    </div>
  )
}
