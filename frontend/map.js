const map = L.map("map").setView([52.2, 5.3], 7);

L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 18,
    attribution: "© OpenStreetMap contributors"
}).addTo(map);

// This endpoint does not exist yet.
// It is the format the frontend expects from the backend.
const API_URL = "/api/v1/predictions/bbox";

const markersLayer = L.layerGroup().addTo(map);
const loadedPoints = new Set();

let loadTimeout = null;

function getColor(properties) {
    const category = properties.powerCategory;

    if (category === "high") {
        return "green";
    }

    if (category === "medium") {
        return "orange";
    }

    if (category === "low") {
        return "red";
    }

    return "gray";
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

async function loadPredictionsForVisibleArea() {
    try {
        const response = await fetch(buildBoundingBoxUrl());

        if (!response.ok) {
            throw new Error("Failed to fetch prediction data from API");
        }

        const geojson = await response.json();

        if (geojson.type !== "FeatureCollection" || !Array.isArray(geojson.features)) {
            throw new Error("Unexpected API response format");
        }

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

            const color = getColor(properties);

            L.circleMarker([latitude, longitude], {
                radius: 6,
                color: color,
                fillColor: color,
                fillOpacity: 0.75
            })
            .addTo(markersLayer)
            .bindPopup(`
                <strong>Predicted Power Output:</strong> ${properties.expectedPowerOutput ?? "N/A"} KW<br>
                <strong>Power Category:</strong> ${properties.powerCategory ?? "N/A"}<br>
                <strong>Latitude:</strong> ${latitude}<br>
                <strong>Longitude:</strong> ${longitude}
            `);
        });

    } catch (error) {
        console.error("Error loading prediction data:", error);
    }
}

function debounceMapLoad() {
    clearTimeout(loadTimeout);
    loadTimeout = setTimeout(loadPredictionsForVisibleArea, 400);
}

map.on("moveend", debounceMapLoad);

loadPredictionsForVisibleArea();