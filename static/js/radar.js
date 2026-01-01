// radar.js - Radar widget with Mapbox integration, RainViewer API, and timestamps
// FIXED: 12-hour time format with AM/PM

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
        this.isRefreshing = false;

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

        // Get hours and convert to 12-hour format
        let hours = date.getHours();
        const ampm = hours >= 12 ? 'PM' : 'AM';
        hours = hours % 12;
        hours = hours ? hours : 12; // Convert 0 to 12

        // Get minutes with leading zero
        const minutes = date.getMinutes().toString().padStart(2, '0');

        return `${hours}:${minutes} ${ampm} RainViewer.com`;
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
                this.showRadarError('No radar data available');
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

                // Use RainViewer API for radar data with cache busting
                const tileUrl = `https://tilecache.rainviewer.com/v2/radar/${timestamp}/256/{z}/{x}/{y}/2/1_1.png`;

                this.mapInstance.addSource(layerId, {
                    type: 'raster',
                    tiles: [tileUrl],
                    tileSize: 256,
                    maxzoom: 12
                });

                this.mapInstance.addLayer({
                    id: layerId,
                    type: 'raster',
                    source: layerId,
                    paint: {
                        'raster-opacity': i === this.availableTimes.length - 1 ? 0.7 : 0,
                        'raster-fade-duration': 0
                    }
                });

                this.radarLayers.push(layerId);
            }

            // Wait for tiles to load
            await this.waitForTilesToLoad();

            // Set initial timestamp to most recent frame
            this.updateTimestamp(this.availableTimes.length - 1);

            // Start animation
            this.startAnimation();

            // Refresh radar data every 10 minutes
            setInterval(() => this.refreshRadarData(), 600000);

        } catch (error) {
            console.error('Error loading radar data:', error);
            this.showRadarError('Failed to load radar');
        }
    }

    async waitForTilesToLoad() {
        return new Promise((resolve) => {
            let tilesLoaded = 0;
            const totalLayers = this.radarLayers.length;

            const checkInterval = setInterval(() => {
                // Check if map has loaded tiles
                if (this.mapInstance.loaded()) {
                    tilesLoaded++;
                }

                if (tilesLoaded > 0 || Date.now() - startTime > 5000) {
                    clearInterval(checkInterval);
                    resolve();
                }
            }, 500);

            const startTime = Date.now();
        });
    }

    showRadarError(message) {
        if (this.timestampElement) {
            this.timestampElement.textContent = message;
            this.timestampElement.style.background = 'rgba(220, 38, 38, 0.8)';
        }
    }

    async refreshRadarData() {
        if (this.isRefreshing) {
            console.log('Refresh already in progress, skipping...');
            return;
        }

        this.isRefreshing = true;
        console.log('Refreshing radar data...');

        const oldLayers = [...this.radarLayers];
        const oldInterval = this.animationInterval;

        try {
            const apiUrl = 'https://api.rainviewer.com/public/weather-maps.json';
            const response = await fetch(apiUrl, {
                cache: 'no-cache'
            });

            if (!response.ok) {
                throw new Error(`API returned ${response.status}`);
            }

            const data = await response.json();

            if (!data.radar || !data.radar.past || data.radar.past.length === 0) {
                console.error('No radar data in refresh response');
                this.isRefreshing = false;
                return;
            }

            const frames = this.config.frames || 5;
            const newTimes = data.radar.past.slice(-frames).map(item => item.time);

            const latestOld = this.availableTimes[this.availableTimes.length - 1];
            const latestNew = newTimes[newTimes.length - 1];

            if (latestNew <= latestOld) {
                console.log('No new radar data available yet');
                this.isRefreshing = false;
                return;
            }

            console.log('New radar data detected, updating layers...');

            const newLayers = [];
            const newLayerPrefix = `radar-layer-new-${Date.now()}-`;

            for (let i = 0; i < newTimes.length; i++) {
                const layerId = `${newLayerPrefix}${i}`;
                const timestamp = newTimes[i];
                const tileUrl = `https://tilecache.rainviewer.com/v2/radar/${timestamp}/256/{z}/{x}/{y}/2/1_1.png`;

                let retries = 3;
                let success = false;

                while (retries > 0 && !success) {
                    try {
                        this.mapInstance.addSource(layerId, {
                            type: 'raster',
                            tiles: [tileUrl],
                            tileSize: 256,
                            maxzoom: 12
                        });

                        this.mapInstance.addLayer({
                            id: layerId,
                            type: 'raster',
                            source: layerId,
                            paint: {
                                'raster-opacity': 0,
                                'raster-fade-duration': 0
                            }
                        });

                        newLayers.push(layerId);
                        success = true;

                    } catch (err) {
                        console.warn(`Retry ${4 - retries}/3 for layer ${layerId}:`, err);
                        retries--;

                        if (retries > 0) {
                            await new Promise(resolve => setTimeout(resolve, 500));
                        }
                    }
                }
            }

            if (newLayers.length === 0) {
                console.error('CRITICAL: No new radar layers created!');
                this.showRadarError('Radar refresh failed');
                this.isRefreshing = false;
                return;
            }

            await new Promise(resolve => setTimeout(resolve, 3000));

            if (oldInterval) {
                clearInterval(oldInterval);
                this.animationInterval = null;
            }

            this.radarLayers = newLayers;
            this.availableTimes = newTimes;
            this.currentFrame = 0;

            for (const layerId of oldLayers) {
                try {
                    if (this.mapInstance.getLayer(layerId)) {
                        this.mapInstance.removeLayer(layerId);
                    }
                    if (this.mapInstance.getSource(layerId)) {
                        this.mapInstance.removeSource(layerId);
                    }
                } catch (err) {
                    console.warn(`Error removing old layer ${layerId}:`, err);
                }
            }

            const latestFrame = this.radarLayers[this.radarLayers.length - 1];
            if (this.mapInstance.getLayer(latestFrame)) {
                this.mapInstance.setPaintProperty(latestFrame, 'raster-opacity', 0.7);
            }

            this.updateTimestamp(this.availableTimes.length - 1);
            this.startAnimation();

            console.log('Radar refresh complete!');

        } catch (error) {
            console.error('Error refreshing radar data:', error);
            this.showRadarError('Refresh failed');

            if (!this.animationInterval && oldLayers.length > 0) {
                this.radarLayers = oldLayers;
                this.startAnimation();
            }

        } finally {
            this.isRefreshing = false;
        }
    }

    startAnimation() {
        if (this.animationInterval) {
            clearInterval(this.animationInterval);
            this.animationInterval = null;
        }

        if (this.radarLayers.length <= 1) {
            console.log('Not enough layers to animate');
            return;
        }

        this.currentFrame = this.radarLayers.length - 1;

        this.animationInterval = setInterval(() => {
            try {
                const currentLayer = this.radarLayers[this.currentFrame];
                if (!this.mapInstance.getLayer(currentLayer)) {
                    console.error(`Layer ${currentLayer} disappeared! Stopping animation.`);
                    clearInterval(this.animationInterval);
                    this.animationInterval = null;
                    this.showRadarError('Radar lost - refresh page');
                    return;
                }

                this.mapInstance.setPaintProperty(
                    currentLayer,
                    'raster-opacity',
                    0
                );

                this.currentFrame = (this.currentFrame + 1) % this.radarLayers.length;

                const nextLayer = this.radarLayers[this.currentFrame];
                if (!this.mapInstance.getLayer(nextLayer)) {
                    console.error(`Layer ${nextLayer} disappeared! Stopping animation.`);
                    clearInterval(this.animationInterval);
                    this.animationInterval = null;
                    this.showRadarError('Radar lost - refresh page');
                    return;
                }

                this.mapInstance.setPaintProperty(
                    nextLayer,
                    'raster-opacity',
                    0.7
                );

                this.updateTimestamp(this.currentFrame);

            } catch (err) {
                console.error('Error in animation loop:', err);
                clearInterval(this.animationInterval);
                this.animationInterval = null;
                this.showRadarError('Animation error');
            }

        }, 800);

        console.log('Radar animation started');
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