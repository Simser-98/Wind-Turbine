const API_URL = "/api/v1/predictions/bbox";

const CATEGORY_COLORS = {
    high: "#16a34a",
    medium: "#f59e0b",
    low: "#dc2626"
};
const UNKNOWN_COLOR = "#94a3b8";

// RdYlGn ramp: low power -> red, high power -> green.
const POWER_RAMP = [
    [0.0, [215, 25, 28]],
    [0.25, [253, 174, 97]],
    [0.5, [255, 255, 191]],
    [0.75, [166, 217, 106]],
    [1.0, [26, 150, 64]]
];

// Heatmap intensity gradient: low -> cool, high -> hot.
const HEAT_GRADIENT = {
    0.2: "#2c7bb6",
    0.5: "#ffff8c",
    0.8: "#f59e0b",
    1.0: "#d7191c"
};

const map = L.map("map").fitBounds([
    [51.87, 4.20],  // south-west: below Rotterdam
    [52.13, 4.55]   // north-east: above The Hague
]);

L.tileLayer("https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png", {
    maxZoom: 19,
    attribution: "© OpenStreetMap contributors © CARTO"
}).addTo(map);

const markersLayer = L.layerGroup().addTo(map);
const loadedPoints = new Set();
const points = [];   // { marker, lat, lng, power, category }

let heatLayer = null;
let mode = "category";
let powerMin = Infinity;
let powerMax = -Infinity;
let loadTimeout = null;

const statusEl = document.getElementById("status");
const countEl = document.getElementById("count");
const legendEl = document.getElementById("legend");
const legendTitleEl = document.getElementById("legend-title");

function rampColor(t) {
    t = Math.max(0, Math.min(1, t));
    for (let i = 1; i < POWER_RAMP.length; i++) {
        const [stop, color] = POWER_RAMP[i];
        const [prevStop, prevColor] = POWER_RAMP[i - 1];
        if (t <= stop) {
            const f = (t - prevStop) / (stop - prevStop || 1);
            const c = prevColor.map((v, k) => Math.round(v + (color[k] - v) * f));
            return `rgb(${c[0]}, ${c[1]}, ${c[2]})`;
        }
    }
    return "rgb(26, 150, 64)";
}

function categoryColor(category) {
    return CATEGORY_COLORS[category] || UNKNOWN_COLOR;
}

function powerColor(power) {
    if (power == null || !isFinite(power)) {
        return UNKNOWN_COLOR;
    }
    const span = powerMax - powerMin;
    const t = span > 0 ? (power - powerMin) / span : 0.5;
    return rampColor(t);
}

function colorFor(point) {
    return mode === "category" ? categoryColor(point.category) : powerColor(point.power);
}

function applyStyles() {
    points.forEach(point => {
        const color = colorFor(point);
        point.marker.setStyle({ color: color, fillColor: color });
    });
}

function heatData() {
    const span = powerMax - powerMin;
    return points.map(point => {
        const intensity = span > 0 && point.power != null
            ? (point.power - powerMin) / span
            : 0.5;
        return [point.lat, point.lng, Math.max(0.05, intensity)];
    });
}

function refreshHeat() {
    if (!heatLayer) {
        heatLayer = L.heatLayer([], {
            radius: 25,
            blur: 18,
            maxZoom: 17,
            minOpacity: 0.25,
            gradient: HEAT_GRADIENT
        });
    }
    heatLayer.setLatLngs(heatData());
}

function renderLegend() {
    if (mode === "category") {
        legendTitleEl.textContent = "Power category";
        legendEl.innerHTML = `
            <div class="legend-row"><span class="legend-swatch" style="background:${CATEGORY_COLORS.high}"></span> High output</div>
            <div class="legend-row"><span class="legend-swatch" style="background:${CATEGORY_COLORS.medium}"></span> Medium output</div>
            <div class="legend-row"><span class="legend-swatch" style="background:${CATEGORY_COLORS.low}"></span> Low output</div>
        `;
        return;
    }

    const hasRange = isFinite(powerMin) && isFinite(powerMax);
    const lo = hasRange ? powerMin.toFixed(1) : "–";
    const hi = hasRange ? powerMax.toFixed(1) : "–";

    if (mode === "heatmap") {
        legendTitleEl.textContent = "Output density";
        const gradient = Object.entries(HEAT_GRADIENT)
            .map(([stop, color]) => `${color} ${Math.round(Number(stop) * 100)}%`)
            .join(", ");
        legendEl.innerHTML = `
            <div class="legend-gradient" style="background:linear-gradient(90deg, ${gradient})"></div>
            <div class="legend-scale"><span>${lo} kW</span><span>${hi} kW</span></div>
        `;
        return;
    }

    legendTitleEl.textContent = "Power output (kW)";
    const gradient = POWER_RAMP
        .map(([stop, c]) => `rgb(${c[0]}, ${c[1]}, ${c[2]}) ${Math.round(stop * 100)}%`)
        .join(", ");
    legendEl.innerHTML = `
        <div class="legend-gradient" style="background:linear-gradient(90deg, ${gradient})"></div>
        <div class="legend-scale"><span>${lo} kW</span><span>${hi} kW</span></div>
    `;
}

function setMode(nextMode) {
    if (mode === nextMode) {
        return;
    }
    mode = nextMode;
    document.getElementById("mode-category").classList.toggle("is-active", mode === "category");
    document.getElementById("mode-power").classList.toggle("is-active", mode === "power");
    document.getElementById("mode-heatmap").classList.toggle("is-active", mode === "heatmap");

    if (mode === "heatmap") {
        map.removeLayer(markersLayer);
        refreshHeat();
        heatLayer.addTo(map);
    } else {
        if (heatLayer) {
            map.removeLayer(heatLayer);
        }
        markersLayer.addTo(map);
        applyStyles();
    }
    renderLegend();
}

function popupHtml(properties, latitude, longitude) {
    const power = properties.expectedPowerOutput;
    const category = properties.powerCategory;
    const pill = categoryColor(category);
    return `
        <div class="popup-card">
            <div class="popup-title">${power != null ? power.toFixed(1) : "N/A"} kW</div>
            <span class="popup-pill" style="background:${pill}">${category ?? "unknown"}</span>
            <div class="popup-coords">${latitude.toFixed(4)}, ${longitude.toFixed(4)}</div>
        </div>
    `;
}

function buildBoundingBoxUrl() {
    const bounds = map.getBounds();
    const params = new URLSearchParams({
        west: bounds.getWest(),
        south: bounds.getSouth(),
        east: bounds.getEast(),
        north: bounds.getNorth()
    });
    return `${API_URL}?${params.toString()}`;
}

function setStatus(text, kind) {
    statusEl.textContent = text;
    statusEl.className = "status" + (kind ? ` is-${kind}` : "");
}

async function loadPredictionsForVisibleArea() {
    try {
        const response = await fetch(buildBoundingBoxUrl());
        if (!response.ok) {
            throw new Error(`API responded ${response.status}`);
        }

        const geojson = await response.json();
        if (geojson.type !== "FeatureCollection" || !Array.isArray(geojson.features)) {
            throw new Error("Unexpected API response format");
        }

        let rangeChanged = false;

        geojson.features.forEach(feature => {
            if (!feature.geometry || feature.geometry.type !== "Point") {
                return;
            }

            const [longitude, latitude] = feature.geometry.coordinates;
            const properties = feature.properties || {};
            const pointId = feature.id || `${longitude},${latitude}`;

            if (loadedPoints.has(pointId)) {
                return;
            }
            loadedPoints.add(pointId);

            const power = properties.expectedPowerOutput;
            if (power != null && isFinite(power)) {
                if (power < powerMin) { powerMin = power; rangeChanged = true; }
                if (power > powerMax) { powerMax = power; rangeChanged = true; }
            }

            const point = { lat: latitude, lng: longitude, power: power, category: properties.powerCategory };
            const color = colorFor(point);

            point.marker = L.circleMarker([latitude, longitude], {
                radius: 6,
                weight: 1.5,
                color: color,
                fillColor: color,
                fillOpacity: 0.8
            })
                .addTo(markersLayer)
                .bindPopup(popupHtml(properties, latitude, longitude));

            points.push(point);
        });

        // Power scale shifted -> recolour everything so it stays comparable.
        if (rangeChanged && mode === "power") {
            applyStyles();
        }
        if (mode === "heatmap") {
            refreshHeat();
        }
        renderLegend();

        countEl.textContent = String(points.length);
        setStatus("Up to date", "ok");
    } catch (error) {
        console.error("Error loading prediction data:", error);
        setStatus("Failed to load predictions", "error");
    }
}

function debounceMapLoad() {
    clearTimeout(loadTimeout);
    loadTimeout = setTimeout(loadPredictionsForVisibleArea, 400);
}

document.getElementById("mode-category").addEventListener("click", () => setMode("category"));
document.getElementById("mode-power").addEventListener("click", () => setMode("power"));
document.getElementById("mode-heatmap").addEventListener("click", () => setMode("heatmap"));
map.on("moveend", debounceMapLoad);

renderLegend();
loadPredictionsForVisibleArea();
