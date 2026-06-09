const map = L.map("map").setView([52.2, 5.3], 7);

L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 18,
    attribution: "© OpenStreetMap contributors"
}).addTo(map);

function getColor(power, lowThreshold, highThreshold) {
    if (power < lowThreshold) {
        return "red";
    } else if (power < highThreshold) {
        return "orange";
    } else {
        return "green";
    }
}

async function loadPredictions() {
    try {
        const response = await fetch("/predictions");

        if (!response.ok) {
            throw new Error("Failed to fetch predictions from API");
        }

        const predictions = await response.json();

        if (!predictions || predictions.length === 0) {
            console.log("No predictions found.");
            return;
        }

        const powerValues = predictions
            .map(prediction => Number(
                prediction.expectedPowerOutput ?? prediction.expected_power_output
            ))
            .filter(value => !isNaN(value));

        const sortedPowerValues = [...powerValues].sort((a, b) => a - b);

        const lowThreshold = sortedPowerValues[Math.floor(sortedPowerValues.length * 0.33)];
        const highThreshold = sortedPowerValues[Math.floor(sortedPowerValues.length * 0.66)];

        predictions.forEach(prediction => {
            const coordinates = prediction.location.coordinates;

            // GeoJSON uses [longitude, latitude]
            const longitude = Number(coordinates[0]);
            const latitude = Number(coordinates[1]);

            const power = Number(
                prediction.expectedPowerOutput ?? prediction.expected_power_output
            );

            if (isNaN(latitude) || isNaN(longitude) || isNaN(power)) {
                return;
            }

            const color = getColor(power, lowThreshold, highThreshold);

            L.circleMarker([latitude, longitude], {
                radius: 6,
                color: color,
                fillColor: color,
                fillOpacity: 0.75
            })
            .addTo(map)
            .bindPopup(`
                <strong>Predicted Power Output:</strong> ${power.toFixed(2)} KW<br>
                <strong>Latitude:</strong> ${latitude}<br>
                <strong>Longitude:</strong> ${longitude}
            `);
        });

    } catch (error) {
        console.error("Error loading predictions:", error);
    }
}

loadPredictions();