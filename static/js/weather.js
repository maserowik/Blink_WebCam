// weather.js - Weather widget functionality with scheduled updates

// ============================================================================
// WEATHER WIDGET
// ============================================================================

let cachedWeatherData = null;
let lastFetchTime = null;

async function fetchWeather(forceRefresh = false) {
    const widget = document.getElementById('weather-widget');
    
    // Check if we should use cached data
    if (!forceRefresh && cachedWeatherData && lastFetchTime) {
        const now = new Date();
        const timeSinceLastFetch = now - lastFetchTime;
        
        // Use cache if less than 30 minutes old
        if (timeSinceLastFetch < 30 * 60 * 1000) {
            console.log('Using cached weather data');
            displayWeather(cachedWeatherData);
            return;
        }
    }
    
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

        // Cache the data
        cachedWeatherData = data;
        lastFetchTime = new Date();
        
        console.log(`Weather fetched at ${lastFetchTime.toLocaleTimeString()}`);
        displayWeather(data);

    } catch (e) {
        console.error('Weather fetch error:', e);
        
        // If we have cached data, use it even if expired
        if (cachedWeatherData) {
            console.log('Using expired cache due to fetch error');
            displayWeather(cachedWeatherData);
        } else {
            showWeatherError();
        }
    }
}

function displayWeather(data) {
    const widget = document.getElementById('weather-widget');
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
}

function showWeatherError() {
    const widget = document.getElementById('weather-widget');
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

// ============================================================================
// SCHEDULED WEATHER UPDATES
// ============================================================================

function getMillisecondsUntilNextScheduledTime() {
    const now = new Date();
    const minutes = now.getMinutes();
    const seconds = now.getSeconds();
    const milliseconds = now.getMilliseconds();
    
    let minutesUntilNext;
    
    if (minutes < 30) {
        // Next update at :30
        minutesUntilNext = 30 - minutes;
    } else {
        // Next update at :00 (next hour)
        minutesUntilNext = 60 - minutes;
    }
    
    // Calculate total milliseconds, accounting for current seconds/milliseconds
    const totalMs = (minutesUntilNext * 60 * 1000) - (seconds * 1000) - milliseconds;
    
    return totalMs;
}

function scheduleNextWeatherUpdate() {
    const msUntilNext = getMillisecondsUntilNextScheduledTime();
    const nextUpdate = new Date(Date.now() + msUntilNext);
    
    console.log(`Next weather update scheduled for ${nextUpdate.toLocaleTimeString()}`);
    
    setTimeout(() => {
        console.log('Scheduled weather update running...');
        fetchWeather(true); // Force refresh
        
        // Schedule the next update (30 minutes from now)
        setTimeout(() => {
            scheduleNextWeatherUpdate();
        }, 100); // Small delay to ensure we're past the update time
        
    }, msUntilNext);
}

// ============================================================================
// INITIALIZE WEATHER
// ============================================================================

document.addEventListener('DOMContentLoaded', function() {
    // Initial fetch on page load
    fetchWeather(true);
    
    // Schedule future updates at :00 and :30
    scheduleNextWeatherUpdate();
    
    // Also set up a 30-minute interval as backup (uses cache if not at scheduled time)
    setInterval(() => fetchWeather(false), 30 * 60 * 1000);
});