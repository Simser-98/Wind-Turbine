const API_URL = "/api/v1/predictions/bbox";

const CATEGORY_COLORS = {
    high: "#16a34a",
    medium: "#f59e0b",
    low: "#dc2626"
};
const UNKNOWN_COLOR = "#94a3b8";

// Simple red -> yellow -> green ramp: low power -> red, high power -> green.
const POWER_RAMP = [
    [0.0, [220, 38, 38]],    // red
    [0.5, [250, 204, 21]],   // yellow
    [1.0, [22, 163, 74]]     // green
];

// Predictions sit on a regular 0.2 degree grid; half-step = cell radius.
const GRID_HALF = 0.1;

// Power (kW) -> ramp position, anchored to the category boundaries observed in
// the data: low < 150, medium 150-351, high > 351. Keeps the power colouring
// consistent with the category colouring.
const POWER_BREAKS = [
    [0, 0.0],      // red
    [150, 0.34],   // low / medium boundary
    [351, 0.66],   // medium / high boundary
    [700, 1.0]     // solidly high -> green
];

const map = L.map("map").fitBounds([
    [51.87, 4.20],  // south-west: below Rotterdam
    [52.13, 4.55]   // north-east: above The Hague
]);

L.tileLayer("https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png", {
    maxZoom: 19,
    attribution: "© OpenStreetMap contributors © CARTO"
}).addTo(map);

const markersLayer = L.layerGroup().addTo(map);
const gridLayer = L.layerGroup();
const loadedPoints = new Set();
const points = [];   // { marker, cell, lat, lng, power, category }

let mode = "category";   // "category" | "power" | "heatmap"
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

// Map a power value to a ramp position using the category-aligned breakpoints.
function normPower(power) {
    if (power == null || !isFinite(power)) {
        return null;
    }
    if (power <= POWER_BREAKS[0][0]) {
        return 0;
    }
    for (let i = 1; i < POWER_BREAKS.length; i++) {
        const [hx, ht] = POWER_BREAKS[i];
        const [lx, lt] = POWER_BREAKS[i - 1];
        if (power <= hx) {
            return lt + (ht - lt) * ((power - lx) / (hx - lx));
        }
    }
    return 1;
}

function categoryColor(category) {
    return CATEGORY_COLORS[category] || UNKNOWN_COLOR;
}

function powerColor(power) {
    const t = normPower(power);
    return t == null ? UNKNOWN_COLOR : rampColor(t);
}

function markerColor(point) {
    return mode === "category" ? categoryColor(point.category) : powerColor(point.power);
}

// Repaint markers (mode-dependent) and grid cells (always power, log-scaled).
function applyStyles() {
    points.forEach(point => {
        const mColor = markerColor(point);
        point.marker.setStyle({ color: mColor, fillColor: mColor });
        const cColor = powerColor(point.power);
        point.cell.setStyle({ fillColor: cColor });
    });
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

    const gradient = POWER_RAMP
        .map(([stop, c]) => `rgb(${c[0]}, ${c[1]}, ${c[2]}) ${Math.round(stop * 100)}%`)
        .join(", ");
    legendTitleEl.textContent = mode === "heatmap" ? "Output heatmap (kW)" : "Power output (kW)";
    legendEl.innerHTML = `
        <div class="legend-gradient" style="background:linear-gradient(90deg, ${gradient})"></div>
        <div class="legend-scale"><span>0</span><span>150</span><span>351</span><span>700+ kW</span></div>
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
        gridLayer.addTo(map);
    } else {
        map.removeLayer(gridLayer);
        markersLayer.addTo(map);
    }
    applyStyles();
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

            const mColor = markerColor(point);
            point.marker = L.circleMarker([latitude, longitude], {
                radius: 6,
                weight: 1.5,
                color: mColor,
                fillColor: mColor,
                fillOpacity: 0.8
            })
                .addTo(markersLayer)
                .bindPopup(popupHtml(properties, latitude, longitude));

            point.cell = L.rectangle(
                [[latitude - GRID_HALF, longitude - GRID_HALF], [latitude + GRID_HALF, longitude + GRID_HALF]],
                { stroke: false, fillColor: powerColor(power), fillOpacity: 0.6 }
            )
                .addTo(gridLayer)
                .bindPopup(popupHtml(properties, latitude, longitude));

            points.push(point);
        });

        // New min/max shifts the whole log scale -> repaint so cells stay comparable.
        if (rangeChanged) {
            applyStyles();
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
