// weather.js - Weather widget functionality (server-side cache only)
// FIXED: Better error handling and debugging

// ============================================================================
// WEATHER WIDGET
// ============================================================================

async function fetchWeather() {
    const widget = document.getElementById('weather-widget');

    try {
        console.log('Fetching weather data...');
        
        const resp = await fetch('/api/weather', {
            method: 'GET',
            headers: {
                'Accept': 'application/json',
                'Cache-Control': 'no-cache'
            }
        });

        console.log('Weather API response status:', resp.status);

        if (!resp.ok) {
            throw new Error(`HTTP error! status: ${resp.status}`);
        }

        const data = await resp.json();
        console.log('Weather data received:', data);

        if (data.error) {
            throw new Error(data.error);
        }

        if (!data.current_condition || !data.current_condition[0]) {
            throw new Error('Invalid weather data format');
        }

        displayWeather(data);
        console.log('Weather displayed successfully');

    } catch (e) {
        console.error('Weather fetch error:', e);
        showWeatherError(e.message);
    }
}

function displayWeather(data) {
    const widget = document.getElementById('weather-widget');
    
    if (!widget) {
        console.error('Weather widget element not found!');
        return;
    }
    
    const current = data.current_condition[0];

    // Icon mapping using HTML entity codes
    const iconMap = {
        'Sunny': '\u2600\uFE0F',
        'Clear': '\uD83C\uDF19',
        'Partly cloudy': '\u26C5',
        'Partly Cloudy': '\u26C5',
        'Mostly Clear': '\u26C5',
        'Mostly Cloudy': '\u2601\uFE0F',
        'Cloudy': '\u2601\uFE0F',
        'Overcast': '\u2601\uFE0F',
        'Mist': '\uD83C\uDF2B\uFE0F',
        'Fog': '\uD83C\uDF2B\uFE0F',
        'Light fog': '\uD83C\uDF2B\uFE0F',
        'Light Fog': '\uD83C\uDF2B\uFE0F',
        'Light rain': '\uD83C\uDF27\uFE0F',
        'Light Rain': '\uD83C\uDF27\uFE0F',
        'Moderate rain': '\uD83C\uDF27\uFE0F',
        'Heavy rain': '\u26C8\uFE0F',
        'Heavy Rain': '\u26C8\uFE0F',
        'Light snow': '\uD83C\uDF28\uFE0F',
        'Light Snow': '\uD83C\uDF28\uFE0F',
        'Heavy snow': '\u2744\uFE0F',
        'Heavy Snow': '\u2744\uFE0F',
        'Thunderstorm': '\u26C8\uFE0F',
        'Rain': '\uD83C\uDF27\uFE0F',
        'Drizzle': '\uD83C\uDF27\uFE0F',
        'Snow': '\u2744\uFE0F',
        'Flurries': '\uD83C\uDF28\uFE0F',
        'Freezing Drizzle': '\uD83C\uDF28\uFE0F',
        'Freezing Rain': '\uD83C\uDF28\uFE0F',
        'Ice Pellets': '\uD83C\uDF28\uFE0F'
    };

    const condition = current.weatherDesc[0].value;
    const icon = iconMap[condition] || '\uD83C\uDF21\uFE0F';
    const tempF = current.temp_F;
    const feelsLike = current.FeelsLikeF;
    const humidity = Math.round(current.humidity);

    // Get location from config (passed via template)
    const location = window.BlinkConfig?.WEATHER_LOCATION || 'Unknown Location';

    widget.innerHTML = `
        <div class="weather-main">
            <div class="weather-icon">${icon}</div>
            <div>
                <div class="weather-temp">${tempF}°F</div>
                <div class="weather-details">Feels ${feelsLike}°F</div>
            </div>
        </div>
        <div class="weather-details">
            <div class="weather-location">${location}</div>
            <div class="weather-condition">${condition}</div>
            <div>Humidity: ${humidity}%</div>
        </div>
    `;
}

function showWeatherError(errorMsg) {
    const widget = document.getElementById('weather-widget');
    
    if (!widget) {
        console.error('Weather widget element not found!');
        return;
    }
    
    const location = window.BlinkConfig?.WEATHER_LOCATION || 'Unknown Location';
    
    widget.innerHTML = `
        <div class="weather-main">
            <div class="weather-icon">\uD83C\uDF21\uFE0F</div>
            <div>
                <div class="weather-temp">--°F</div>
                <div class="weather-details">Service unavailable</div>
            </div>
        </div>
        <div class="weather-details">
            <div class="weather-location">${location}</div>
            <div style="font-size:0.8em;opacity:0.8;">
                ${errorMsg || 'Weather service temporarily unavailable'}
            </div>
        </div>
    `;
}

// ============================================================================
// INITIALIZE WEATHER (ONE-TIME FETCH ON PAGE LOAD)
// ============================================================================

document.addEventListener('DOMContentLoaded', function() {
    console.log('Weather widget initializing...');
    
    // Check if widget exists
    const widget = document.getElementById('weather-widget');
    if (!widget) {
        console.error('ERROR: weather-widget element not found in DOM!');
        return;
    }
    
    // Check if config exists
    if (!window.BlinkConfig) {
        console.error('ERROR: BlinkConfig not found! Weather config missing.');
        showWeatherError('Configuration error');
        return;
    }
    
    console.log('Weather config loaded:', window.BlinkConfig.WEATHER_LOCATION);
    
    // Fetch weather once on page load
    // Server caches for 30 minutes, so we don't need client-side polling
    fetchWeather();

    console.log('Weather: Using server-side cache (30-minute refresh)');
});

// Export for manual refresh if needed
window.refreshWeather = fetchWeather;
window.showWeatherError = showWeatherError;

// Debug helper
window.debugWeather = function() {
    console.log('='.repeat(60));
    console.log('WEATHER DEBUG INFO');
    console.log('='.repeat(60));
    console.log('Widget element exists:', !!document.getElementById('weather-widget'));
    console.log('BlinkConfig exists:', !!window.BlinkConfig);
    if (window.BlinkConfig) {
        console.log('Location:', window.BlinkConfig.WEATHER_LOCATION);
        console.log('Lat/Lon:', window.BlinkConfig.WEATHER_LAT, window.BlinkConfig.WEATHER_LON);
    }
    console.log('='.repeat(60));
    console.log('Testing API call...');
    fetchWeather();
};