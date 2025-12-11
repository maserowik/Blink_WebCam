// radar.js - Radar widget with Mapbox integration, RainViewer API, and timestamps

// ============================================================================
// RADAR WIDGET CLASS
// ============================================================================

class RadarWidget {
    constructor(containerId, config) {
        this.container = document.getElementById(containerId);
        this.config = config;
        this.mapInstance = null;
        this.radarLayers = [];
        this.currentFrame = 0;
        this.animationInterval = null;
        this.availableTimes = [];
        this.timestampElement = null;

        this.init();
    }

    async init() {
        try {
            // Load Mapbox GL JS library
            if (!window.mapboxgl) {
                await this.loadMapboxLibrary();
            }

            mapboxgl.accessToken = this.config.mapbox_token;

            // Create map container
            this.container.innerHTML = '<div id="radar-map" style="width:100%;height:100%;position:relative;"></div>';

            // Create timestamp overlay
            this.timestampElement = document.createElement('div');
            this.timestampElement.id = 'radar-timestamp';
            this.timestampElement.style.cssText = `
                position: absolute;
                top: 5px;
                left: 5px;
                background: rgba(0, 0, 0, 0.6);
                color: white;
                padding: 4px 8px;
                border-radius: 4px;
                font-family: Arial, sans-serif;
                font-size: 11px;
                font-weight: bold;
                z-index: 1000;
                pointer-events: none;
                text-shadow: 1px 1px 2px rgba(0,0,0,0.8);
            `;
            document.getElementById('radar-map').appendChild(this.timestampElement);

            // Determine basemap style
            let baseStyle = this.config.basemap_style || 'mapbox://styles/mapbox/dark-v11';
            if (baseStyle && !baseStyle.startsWith('mapbox://')) {
                baseStyle = `mapbox://styles/${baseStyle}`;
            }

            // Initialize map
            this.mapInstance = new mapboxgl.Map({
                container: 'radar-map',
                style: baseStyle,
                center: [this.config.lon, this.config.lat],
                zoom: this.config.zoom || 7,
                interactive: false,
                attributionControl: false
            });

            this.mapInstance.on('load', () => {
                this.loadRadarData();
            });

        } catch (error) {
            console.error('Radar widget initialization error:', error);
            this.container.innerHTML = `
                <div style="display:flex;align-items:center;justify-content:center;height:100%;padding:15px;text-align:center;font-size:0.9em;color:var(--card-text);">
                    Error loading radar
                </div>
            `;
        }
    }

    loadMapboxLibrary() {
        return new Promise((resolve, reject) => {
            // Load Mapbox GL CSS
            const link = document.createElement('link');
            link.href = 'https://api.mapbox.com/mapbox-gl-js/v2.15.0/mapbox-gl.css';
            link.rel = 'stylesheet';
            document.head.appendChild(link);

            // Load Mapbox GL JS
            const script = document.createElement('script');
            script.src = 'https://api.mapbox.com/mapbox-gl-js/v2.15.0/mapbox-gl.js';
            script.onload = resolve;
            script.onerror = reject;
            document.head.appendChild(script);
        });
    }

    formatTimestamp(unixTimestamp) {
        const date = new Date(unixTimestamp * 1000);
        const hours = date.getHours().toString().padStart(2, '0');
        const minutes = date.getMinutes().toString().padStart(2, '0');
        return `${hours}:${minutes} RainViewer.com`;
    }

    updateTimestamp(frameIndex) {
        if (this.timestampElement && this.availableTimes[frameIndex]) {
            const timestamp = this.availableTimes[frameIndex];
            this.timestampElement.textContent = this.formatTimestamp(timestamp);
        }
    }

    async loadRadarData() {
        try {
            // First, get available radar times from RainViewer API
            const apiUrl = 'https://api.rainviewer.com/public/weather-maps.json';
            const response = await fetch(apiUrl);
            const data = await response.json();

            if (!data.radar || !data.radar.past || data.radar.past.length === 0) {
                console.error('No radar data available from RainViewer');
                return;
            }

            const frames = this.config.frames || 5;

            // Get the last N frames (most recent)
            this.availableTimes = data.radar.past.slice(-frames).map(item => item.time);

            console.log('Available radar times:', this.availableTimes);

            // Add radar layers for each available timestamp
            for (let i = 0; i < this.availableTimes.length; i++) {
                const layerId = `radar-layer-${i}`;
                const timestamp = this.availableTimes[i];

                // Use RainViewer API for radar data
                const tileUrl = `https://tilecache.rainviewer.com/v2/radar/${timestamp}/256/{z}/{x}/{y}/2/1_1.png`;

                this.mapInstance.addSource(layerId, {
                    type: 'raster',
                    tiles: [tileUrl],
                    tileSize: 256
                });

                this.mapInstance.addLayer({
                    id: layerId,
                    type: 'raster',
                    source: layerId,
                    paint: {
                        'raster-opacity': i === this.availableTimes.length - 1 ? 0.7 : 0
                    }
                });

                this.radarLayers.push(layerId);
            }

            // Set initial timestamp to most recent frame
            this.updateTimestamp(this.availableTimes.length - 1);

            // Start animation
            this.startAnimation();

            // Refresh radar data every 10 minutes
            setInterval(() => this.refreshRadarData(), 600000);

        } catch (error) {
            console.error('Error loading radar data:', error);
        }
    }

    async refreshRadarData() {
        try {
            console.log('Refreshing radar data...');

            // Get new available times
            const apiUrl = 'https://api.rainviewer.com/public/weather-maps.json';
            const response = await fetch(apiUrl);
            const data = await response.json();

            if (!data.radar || !data.radar.past || data.radar.past.length === 0) {
                console.error('No radar data available');
                return;
            }

            const frames = this.config.frames || 5;
            const newTimes = data.radar.past.slice(-frames).map(item => item.time);

            // Check if we have new data
            const latestOld = this.availableTimes[this.availableTimes.length - 1];
            const latestNew = newTimes[newTimes.length - 1];

            if (latestNew > latestOld) {
                console.log('New radar data available, updating...');

                // Remove old layers
                for (const layerId of this.radarLayers) {
                    if (this.mapInstance.getLayer(layerId)) {
                        this.mapInstance.removeLayer(layerId);
                    }
                    if (this.mapInstance.getSource(layerId)) {
                        this.mapInstance.removeSource(layerId);
                    }
                }

                // Reset
                this.radarLayers = [];
                this.availableTimes = newTimes;
                this.currentFrame = 0;

                // Add new layers
                for (let i = 0; i < this.availableTimes.length; i++) {
                    const layerId = `radar-layer-${i}`;
                    const timestamp = this.availableTimes[i];
                    const tileUrl = `https://tilecache.rainviewer.com/v2/radar/${timestamp}/256/{z}/{x}/{y}/2/1_1.png`;

                    this.mapInstance.addSource(layerId, {
                        type: 'raster',
                        tiles: [tileUrl],
                        tileSize: 256
                    });

                    this.mapInstance.addLayer({
                        id: layerId,
                        type: 'raster',
                        source: layerId,
                        paint: {
                            'raster-opacity': i === this.availableTimes.length - 1 ? 0.7 : 0
                        }
                    });

                    this.radarLayers.push(layerId);
                }

                // Update timestamp
                this.updateTimestamp(this.availableTimes.length - 1);
            }

        } catch (error) {
            console.error('Error refreshing radar data:', error);
        }
    }

    startAnimation() {
        if (this.radarLayers.length <= 1) return;

        this.currentFrame = this.radarLayers.length - 1;

        this.animationInterval = setInterval(() => {
            // Hide current frame
            this.mapInstance.setPaintProperty(
                this.radarLayers[this.currentFrame],
                'raster-opacity',
                0
            );

            // Move to next frame
            this.currentFrame = (this.currentFrame + 1) % this.radarLayers.length;

            // Show next frame
            this.mapInstance.setPaintProperty(
                this.radarLayers[this.currentFrame],
                'raster-opacity',
                0.7
            );

            // Update timestamp for current frame
            this.updateTimestamp(this.currentFrame);

        }, 800); // Change frame every 800ms
    }

    destroy() {
        if (this.animationInterval) {
            clearInterval(this.animationInterval);
        }
        if (this.mapInstance) {
            this.mapInstance.remove();
        }
    }
}

// ============================================================================
// LOAD RADAR
// ============================================================================

let radarWidget = null;

async function loadRadar() {
    try {
        const response = await fetch('/api/radar/config');
        const data = await response.json();

        console.log('Radar config response:', data);

        if (!data.success) {
            throw new Error('Failed to load radar config');
        }

        const config = data.radar_config;

        console.log('Radar enabled:', config.enabled);
        console.log('Mapbox token present:', !!config.mapbox_token);

        // Handle both boolean and string values for enabled
        const isEnabled = (config.enabled === true || config.enabled === 'true');
        const hasToken = config.mapbox_token && config.mapbox_token.trim() !== '';

        if (isEnabled && hasToken) {
            console.log('Initializing radar widget...');
            radarWidget = new RadarWidget('radar-widget', config);
        } else {
            console.log('Radar not configured - missing requirements');
            document.getElementById('radar-widget').innerHTML =
                '<div style="display:flex;align-items:center;justify-content:center;height:100%;padding:15px;text-align:center;font-size:0.9em;color:var(--card-text);">Radar not configured. Run: python blink_config_setup.py</div>';
        }

    } catch (error) {
        console.error('Failed to load radar:', error);
        document.getElementById('radar-widget').innerHTML =
            '<div style="display:flex;align-items:center;justify-content:center;height:100%;padding:15px;text-align:center;font-size:0.9em;color:var(--card-text);">Radar unavailable</div>';
    }
}

// ============================================================================
// INITIALIZE RADAR
// ============================================================================

document.addEventListener('DOMContentLoaded', function() {
    loadRadar();
});