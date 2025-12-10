// weather.js - Weather widget functionality

// ============================================================================
// WEATHER WIDGET
// ============================================================================

async function fetchWeather() {
    const widget = document.getElementById('weather-widget');
    
    try {
        const resp = await fetch('/api/weather', {
            method: 'GET',
            headers: {
                'Accept': 'application/json'
            }
        });

        if (!resp.ok) {
            throw new Error(`HTTP error! status: ${resp.status}`);
        }

        const data = await resp.json();

        if (data.error || !data.current_condition || !data.current_condition[0]) {
            throw new Error('Invalid weather data format');
        }

        const current = data.current_condition[0];
        
        // Icon mapping
        const iconMap = {
            'Sunny': '&#x2600;&#xFE0F;',
            'Clear': '&#x1F319;',
            'Partly cloudy': '&#x26C5;',
            'Cloudy': '&#x2601;&#xFE0F;',
            'Overcast': '&#x2601;&#xFE0F;',
            'Mist': '&#x1F32B;&#xFE0F;',
            'Fog': '&#x1F32B;&#xFE0F;',
            'Light rain': '&#x1F327;&#xFE0F;',
            'Moderate rain': '&#x1F327;&#xFE0F;',
            'Heavy rain': '&#x26C8;&#xFE0F;',
            'Light snow': '&#x1F328;&#xFE0F;',
            'Heavy snow': '&#x2744;&#xFE0F;',
            'Thunderstorm': '&#x26C8;&#xFE0F;'
        };

        const icon = iconMap[current.weatherDesc[0].value] || '&#x1F321;&#xFE0F;';
        const tempF = current.temp_F;
        const feelsLike = current.FeelsLikeF;
        const condition = current.weatherDesc[0].value;
        const humidity = current.humidity;

        widget.innerHTML = `
            <div class="weather-main">
                <div class="weather-icon">${icon}</div>
                <div>
                    <div class="weather-temp">${tempF}°F</div>
                    <div class="weather-details">Feels ${feelsLike}°F</div>
                </div>
            </div>
            <div class="weather-details">
                <div class="weather-location">${window.BlinkConfig.WEATHER_LOCATION}</div>
                <div class="weather-condition">${condition}</div>
                <div>Humidity: ${humidity}%</div>
            </div>
        `;

    } catch (e) {
        console.error('Weather fetch error:', e);
        widget.innerHTML = `
            <div class="weather-main">
                <div class="weather-icon">&#x1F321;&#xFE0F;</div>
                <div>
                    <div class="weather-temp">--°F</div>
                    <div class="weather-details">Service unavailable</div>
                </div>
            </div>
            <div class="weather-details">
                <div class="weather-location">${window.BlinkConfig.WEATHER_LOCATION}</div>
                <div style="font-size:0.8em;opacity:0.8;">Weather service temporarily unavailable</div>
            </div>
        `;
    }
}

// ============================================================================
// INITIALIZE WEATHER
// ============================================================================

document.addEventListener('DOMContentLoaded', function() {
    fetchWeather();
    setInterval(fetchWeather, 900000); // Refresh every 15 minutes
});