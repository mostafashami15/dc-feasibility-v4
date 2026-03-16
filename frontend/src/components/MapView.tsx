import { useEffect } from "react";
import {
  Circle,
  CircleMarker,
  MapContainer,
  Marker,
  Polygon,
  Polyline,
  Popup,
  TileLayer,
  useMap,
} from "react-leaflet";
import L from "leaflet";
import type { DivIcon, LatLngBoundsExpression } from "leaflet";
import type { GridAsset, SiteResponse } from "../types";

const ITALY_CENTER: [number, number] = [42.8, 12.6];
const ITALY_BOUNDS: LatLngBoundsExpression = [
  [35.4, 6.2],
  [47.3, 18.9],
];
const DEFAULT_TILE_URL = "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png";
const DEFAULT_TILE_ATTRIBUTION =
  '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>';

type ImportedGeometry = NonNullable<SiteResponse["site"]["imported_geometry"]>;
type MapMode = "overview" | "detail";
type MarkerTone = "overview" | "detail" | "terrain" | "draft";

function buildMarkerIcon(tone: MarkerTone, selected = false): DivIcon {
  const isLarge = tone === "detail" || tone === "terrain";
  const size = tone === "terrain" ? 34 : isLarge ? 30 : 24;
  const height = tone === "terrain" ? 48 : isLarge ? 42 : 36;
  const className = [
    "site-map-pin",
    `site-map-pin--${tone}`,
    selected ? "is-selected" : "",
  ]
    .filter(Boolean)
    .join(" ");

  return L.divIcon({
    className: "site-map-pin-wrapper",
    html: `<span class="${className}"><span class="site-map-pin__core"></span></span>`,
    iconSize: [size, height],
    iconAnchor: [size / 2, height - 2],
    popupAnchor: [0, -height + 8],
  });
}

const OVERVIEW_ICON = buildMarkerIcon("overview");
const OVERVIEW_SELECTED_ICON = buildMarkerIcon("overview", true);
const DETAIL_ICON = buildMarkerIcon("detail");
const DETAIL_SELECTED_ICON = buildMarkerIcon("detail", true);
const TERRAIN_ICON = buildMarkerIcon("terrain");
const TERRAIN_SELECTED_ICON = buildMarkerIcon("terrain", true);
const DRAFT_ICON = buildMarkerIcon("draft", true);

function resolveMarkerIcon(tone: MarkerTone, selected: boolean): DivIcon {
  if (tone === "terrain") {
    return selected ? TERRAIN_SELECTED_ICON : TERRAIN_ICON;
  }
  if (tone === "detail") {
    return selected ? DETAIL_SELECTED_ICON : DETAIL_ICON;
  }
  if (tone === "draft") {
    return DRAFT_ICON;
  }
  return selected ? OVERVIEW_SELECTED_ICON : OVERVIEW_ICON;
}

function collectGeometryPoints(geometry?: ImportedGeometry | null): Array<[number, number]> {
  return geometry?.coordinates ?? [];
}

function collectGridPoints(gridAssets?: GridAsset[]): Array<[number, number]> {
  if (!gridAssets) {
    return [];
  }
  return gridAssets.flatMap((asset) =>
    asset.coordinates.map(([lat, lon]) => [lat, lon] as [number, number])
  );
}

function radiusBoundsPoints(
  center?: { lat: number; lon: number } | null,
  radiusKm?: number | null
): Array<[number, number]> {
  if (!center || !radiusKm || radiusKm <= 0) {
    return [];
  }

  const latDelta = radiusKm / 110.574;
  const lonDelta = radiusKm / (111.32 * Math.max(Math.cos(center.lat * Math.PI / 180), 0.01));
  return [
    [center.lat + latDelta, center.lon],
    [center.lat - latDelta, center.lon],
    [center.lat, center.lon + lonDelta],
    [center.lat, center.lon - lonDelta],
  ];
}

function gridVoltageColor(voltageKv: number | null): string {
  if (voltageKv === null || voltageKv <= 36) {
    return "#6b7280";
  }
  if (voltageKv <= 132) {
    return "#d97706";
  }
  if (voltageKv < 380) {
    return "#ea580c";
  }
  return "#dc2626";
}

function buildGridSubstationIcon(voltageKv: number | null, focused = false): DivIcon {
  const accentColor = gridVoltageColor(voltageKv);
  const frameColor = focused ? "#0f172a" : "#334155";
  const size = focused ? 24 : 20;
  const inset = focused ? 3 : 2;
  const innerSize = focused ? 8 : 7;

  return L.divIcon({
    className: "grid-substation-marker-wrapper",
    html: `
      <span style="position:relative;display:block;width:${size}px;height:${size}px;">
        <span style="
          position:absolute;
          inset:${inset}px;
          background:rgba(255,255,255,0.96);
          border:${focused ? 3 : 2}px solid ${frameColor};
          border-radius:2px;
          transform:rotate(45deg);
          box-shadow:0 2px 8px rgba(15,23,42,0.22);
        "></span>
        <span style="
          position:absolute;
          left:50%;
          top:50%;
          width:${innerSize}px;
          height:${innerSize}px;
          background:${accentColor};
          border-radius:2px;
          transform:translate(-50%, -50%);
        "></span>
      </span>
    `,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
    popupAnchor: [0, -size / 2],
  });
}

function formatGridConfidence(confidence: GridAsset["confidence"]): string {
  if (confidence === "mapped_public") {
    return "Mapped-public";
  }
  if (confidence === "official_aggregate") {
    return "Official aggregate";
  }
  if (confidence === "user_confirmed") {
    return "User confirmed";
  }
  return confidence;
}

function formatGridSourceLayer(source: string): string {
  if (source === "mapped_public_osm_overpass") {
    return "OSM / Overpass mapped-public";
  }
  if (source === "mapped_public_fixture") {
    return "Mapped-public fixture";
  }
  if (source === "user_confirmed_manual") {
    return "Manual official evidence";
  }
  return source
    .split("_")
    .map((token) => token.charAt(0).toUpperCase() + token.slice(1))
    .join(" ");
}

function MapViewportController({
  mode,
  sites,
  singlePoint,
  singleGeometry,
  gridAssets,
  gridSiteCenter,
  gridRadiusKm,
  singlePointZoom,
  fitMaxZoom,
}: {
  mode: MapMode;
  sites: SiteResponse[];
  singlePoint?: { lat: number; lon: number } | null;
  singleGeometry?: ImportedGeometry | null;
  gridAssets?: GridAsset[];
  gridSiteCenter?: { lat: number; lon: number } | null;
  gridRadiusKm?: number | null;
  singlePointZoom: number;
  fitMaxZoom: number;
}) {
  const map = useMap();

  useEffect(() => {
    if (mode === "overview") {
      map.fitBounds(ITALY_BOUNDS, { padding: [24, 24] });
      return;
    }

    const geometryPoints = sites.flatMap((site) =>
      collectGeometryPoints(site.site.imported_geometry)
    );
    const previewGeometryPoints = collectGeometryPoints(singleGeometry);
    const gridPoints = collectGridPoints(gridAssets);
    const circlePoints = radiusBoundsPoints(gridSiteCenter, gridRadiusKm);
    const markerPoints = sites
      .filter((site) => site.site.latitude !== null && site.site.longitude !== null)
      .map((site) => [site.site.latitude!, site.site.longitude!] as [number, number]);

    if (singlePoint) {
      markerPoints.push([singlePoint.lat, singlePoint.lon]);
    }

    const points = [
      ...geometryPoints,
      ...previewGeometryPoints,
      ...gridPoints,
      ...circlePoints,
      ...markerPoints,
    ];

    if (points.length === 0) {
      map.fitBounds(ITALY_BOUNDS, { padding: [24, 24] });
      return;
    }

    if (points.length === 1) {
      map.setView(points[0], singlePointZoom);
      return;
    }

    map.fitBounds(points, {
      padding: [36, 36],
      maxZoom: fitMaxZoom,
    });
  }, [
    fitMaxZoom,
    gridAssets,
    gridRadiusKm,
    gridSiteCenter,
    map,
    mode,
    singleGeometry,
    singlePoint,
    singlePointZoom,
    sites,
  ]);

  return null;
}

function renderGeometry(
  site: SiteResponse,
  selectedId: string | null | undefined,
  onSelect?: (id: string) => void,
) {
  const geometry = site.site.imported_geometry;
  if (!geometry?.coordinates?.length) {
    return null;
  }

  const isSelected = selectedId === site.id;
  const color = isSelected ? "#2563eb" : "#0f766e";

  if (geometry.geometry_type === "polygon") {
    return (
      <Polygon
        key={`geometry-${site.id}`}
        positions={geometry.coordinates}
        pathOptions={{
          color,
          weight: isSelected ? 3 : 2,
          fillColor: color,
          fillOpacity: isSelected ? 0.18 : 0.08,
        }}
        eventHandlers={{
          click: () => onSelect?.(site.id),
        }}
      />
    );
  }

  return (
    <Polyline
      key={`geometry-${site.id}`}
      positions={geometry.coordinates}
      pathOptions={{
        color,
        weight: isSelected ? 4 : 3,
        opacity: isSelected ? 0.92 : 0.74,
      }}
      eventHandlers={{
        click: () => onSelect?.(site.id),
      }}
    />
  );
}

function renderGridAssetPopup(asset: GridAsset) {
  return (
    <Popup>
      <div className="text-sm">
        <p className="font-bold">{asset.name || "Mapped grid asset"}</p>
        <p className="mt-0.5 text-gray-600 capitalize">{asset.asset_type}</p>
        <p className="mt-1 text-xs text-gray-500">
          {asset.distance_km.toFixed(2)} km away
          {asset.voltage_kv !== null ? ` · ${asset.voltage_kv.toFixed(0)} kV` : ""}
        </p>
        <p className="mt-1 text-xs text-gray-500">
          {asset.operator || "Operator not tagged"} · {formatGridConfidence(asset.confidence)}
        </p>
        {asset.circuits !== null && (
          <p className="mt-1 text-xs text-gray-500">{asset.circuits} mapped circuits</p>
        )}
        <p className="mt-1 text-xs text-gray-500">
          {formatGridSourceLayer(asset.source)} · screening-grade input
        </p>
      </div>
    </Popup>
  );
}

function renderGridAsset(asset: GridAsset, isFocused = false) {
  const color = gridVoltageColor(asset.voltage_kv);

  if (asset.geometry_type === "point" && asset.coordinates.length > 0) {
    const [lat, lon] = asset.coordinates[0];
    if (asset.asset_type === "substation") {
      return (
        <Marker
          key={`grid-${asset.asset_id}`}
          position={[lat, lon]}
          icon={buildGridSubstationIcon(asset.voltage_kv, isFocused)}
          zIndexOffset={isFocused ? 900 : 500}
        >
          {renderGridAssetPopup(asset)}
        </Marker>
      );
    }

    return (
      <CircleMarker
        key={`grid-${asset.asset_id}`}
        center={[lat, lon]}
        radius={isFocused ? 10 : 8}
        pathOptions={{
          color,
          fillColor: color,
          fillOpacity: isFocused ? 0.98 : 0.85,
          weight: isFocused ? 3 : 2,
        }}
      >
        {renderGridAssetPopup(asset)}
      </CircleMarker>
    );
  }

  if (asset.geometry_type === "polygon" && asset.coordinates.length > 0) {
    return (
      <Polygon
        key={`grid-${asset.asset_id}`}
        positions={asset.coordinates}
        pathOptions={{
          color,
          weight: isFocused ? 3 : 2,
          fillColor: color,
          fillOpacity: isFocused ? 0.2 : 0.12,
        }}
      >
        {renderGridAssetPopup(asset)}
      </Polygon>
    );
  }

  if (asset.coordinates.length > 0) {
    return (
      <Polyline
        key={`grid-${asset.asset_id}`}
        positions={asset.coordinates}
        pathOptions={{
          color,
          weight: asset.asset_type === "line"
            ? (isFocused ? 6 : 4)
            : (isFocused ? 4 : 2),
          opacity: isFocused ? 1 : 0.92,
        }}
      >
        {renderGridAssetPopup(asset)}
      </Polyline>
    );
  }

  return null;
}

interface MapViewProps {
  sites: SiteResponse[];
  selectedId?: string | null;
  onSelect?: (id: string) => void;
  singlePoint?: { lat: number; lon: number } | null;
  singleGeometry?: ImportedGeometry | null;
  gridAssets?: GridAsset[];
  focusedGridAssetId?: string | null;
  showGridOverlay?: boolean;
  gridRadiusKm?: number | null;
  gridSiteCenter?: { lat: number; lon: number } | null;
  height?: string;
  mode?: MapMode;
  tileUrl?: string;
  tileAttribution?: string;
  markerTone?: Exclude<MarkerTone, "draft">;
  selectedMarkerTone?: Exclude<MarkerTone, "draft">;
  singlePointZoom?: number;
  fitMaxZoom?: number;
}

export default function MapView({
  sites,
  selectedId,
  onSelect,
  singlePoint,
  singleGeometry,
  gridAssets = [],
  focusedGridAssetId = null,
  showGridOverlay = false,
  gridRadiusKm = null,
  gridSiteCenter = null,
  height = "h-72",
  mode = "overview",
  tileUrl = DEFAULT_TILE_URL,
  tileAttribution = DEFAULT_TILE_ATTRIBUTION,
  markerTone,
  selectedMarkerTone,
  singlePointZoom = 14,
  fitMaxZoom = 14,
}: MapViewProps) {
  const center: [number, number] = singlePoint
    ? [singlePoint.lat, singlePoint.lon]
    : ITALY_CENTER;
  const zoom = mode === "overview" ? 6 : 7;
  const defaultMarkerTone: Exclude<MarkerTone, "draft"> =
    markerTone ?? (mode === "detail" ? "detail" : "overview");
  const emphasizedMarkerTone: Exclude<MarkerTone, "draft"> =
    selectedMarkerTone ?? defaultMarkerTone;
  const orderedGridAssets = focusedGridAssetId
    ? [...gridAssets].sort(
        (left, right) =>
          Number(left.asset_id === focusedGridAssetId) -
          Number(right.asset_id === focusedGridAssetId)
      )
    : gridAssets;

  return (
    <div className={`${height} w-full overflow-hidden rounded-xl`}>
      <MapContainer
        center={center}
        zoom={zoom}
        scrollWheelZoom
        className="h-full w-full"
      >
        <TileLayer
          attribution={tileAttribution}
          url={tileUrl}
        />

        <MapViewportController
          mode={mode}
          sites={sites}
          singlePoint={singlePoint}
          singleGeometry={singleGeometry}
          gridAssets={showGridOverlay ? gridAssets : []}
          gridSiteCenter={showGridOverlay ? gridSiteCenter : null}
          gridRadiusKm={showGridOverlay ? gridRadiusKm : null}
          singlePointZoom={singlePointZoom}
          fitMaxZoom={fitMaxZoom}
        />

        {sites.map((site) => renderGeometry(site, selectedId, onSelect))}

        {sites
          .filter((site) => site.site.latitude !== null && site.site.longitude !== null)
          .map((site) => {
            const isSelected = selectedId === site.id;
            const icon = resolveMarkerIcon(
              isSelected ? emphasizedMarkerTone : defaultMarkerTone,
              isSelected
            );

            return (
              <Marker
                key={site.id}
                position={[site.site.latitude!, site.site.longitude!]}
                icon={icon}
                opacity={selectedId && selectedId !== site.id ? 0.78 : 1}
                zIndexOffset={isSelected ? 1000 : 0}
                eventHandlers={{
                  click: () => onSelect?.(site.id),
                }}
              >
                <Popup>
                  <div className="text-sm">
                    <p className="font-bold">{site.site.name}</p>
                    <p className="mt-0.5 text-gray-600">
                      {site.site.city || "No city"}, {site.site.country || "-"}
                    </p>
                    <p className="mt-1 text-xs text-gray-500">
                      {site.site.land_area_m2.toLocaleString()} m2 ·{" "}
                      {site.site.available_power_mw > 0
                        ? `${site.site.available_power_mw} MW`
                        : "Area-only"}
                    </p>
                    {site.has_weather && (
                      <span className="text-xs text-green-600">Weather cached</span>
                    )}
                  </div>
                </Popup>
              </Marker>
            );
          })}

        {showGridOverlay && gridSiteCenter && gridRadiusKm && (
          <Circle
            center={[gridSiteCenter.lat, gridSiteCenter.lon]}
            radius={gridRadiusKm * 1000}
            pathOptions={{
              color: "#1d4ed8",
              weight: 2,
              dashArray: "6 6",
              fillOpacity: 0.04,
            }}
          />
        )}

        {showGridOverlay && orderedGridAssets.map((asset) => (
          renderGridAsset(asset, asset.asset_id === focusedGridAssetId)
        ))}

        {singleGeometry?.coordinates?.length && singleGeometry.geometry_type === "polygon" && (
          <Polygon
            positions={singleGeometry.coordinates}
            pathOptions={{
              color: "#dc2626",
              weight: 3,
              fillColor: "#f97316",
              fillOpacity: 0.14,
            }}
          />
        )}

        {singleGeometry?.coordinates?.length && singleGeometry.geometry_type === "line" && (
          <Polyline
            positions={singleGeometry.coordinates}
            pathOptions={{
              color: "#dc2626",
              weight: 4,
              opacity: 0.92,
            }}
          />
        )}

        {singlePoint && (
          <Marker position={[singlePoint.lat, singlePoint.lon]} icon={DRAFT_ICON}>
            <Popup>
              <p className="text-sm font-medium">Draft site preview</p>
            </Popup>
          </Marker>
        )}
      </MapContainer>
    </div>
  );
}
