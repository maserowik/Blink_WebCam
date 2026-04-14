// radar.js - Radar widget with Mapbox integration, RainViewer API, and timestamps
// FIXED: Uses dynamic paths from metadata to avoid 410 Gone errors

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
            if (!window.mapboxgl) {
                await this.loadMapboxLibrary();
            }

            mapboxgl.accessToken = this.config.mapbox_token;

            this.container.innerHTML = '<div id="radar-map" style="width:100%;height:100%;position:relative;"></div>';

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

            let baseStyle = this.config.basemap_style || 'mapbox://styles/mapbox/dark-v11';
            if (baseStyle && !baseStyle.startsWith('mapbox://')) {
                baseStyle = `mapbox://styles/${baseStyle}`;
            }

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
            const link = document.createElement('link');
            link.href = 'https://api.mapbox.com/mapbox-gl-js/v2.15.0/mapbox-gl.css';
            link.rel = 'stylesheet';
            document.head.appendChild(link);

            const script = document.createElement('script');
            script.src = 'https://api.mapbox.com/mapbox-gl-js/v2.15.0/mapbox-gl.js';
            script.onload = resolve;
            script.onerror = reject;
            document.head.appendChild(script);
        });
    }

    formatTimestamp(unixTimestamp) {
        const date = new Date(unixTimestamp * 1000);
        let hours = date.getHours();
        const ampm = hours >= 12 ? 'PM' : 'AM';
        hours = hours % 12;
        hours = hours ? hours : 12; 
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
            const apiUrl = 'https://api.rainviewer.com/public/weather-maps.json';
            const response = await fetch(apiUrl);
            const data = await response.json();

            if (!data.radar || !data.radar.past || data.radar.past.length === 0) {
                this.showRadarError('No radar data available');
                return;
            }

            const framesCount = this.config.frames || 5;
            const pastFrames = data.radar.past.slice(-framesCount);
            this.availableTimes = pastFrames.map(item => item.time);
            const host = data.host || 'https://tilecache.rainviewer.com';

            for (let i = 0; i < pastFrames.length; i++) {
                const layerId = `radar-layer-${i}`;
                const framePath = pastFrames[i].path; // Use path from metadata

                // Use 256 tiles and dynamic path to avoid 410 Gone errors
                const tileUrl = `${host}${framePath}/256/{z}/{x}/{y}/2/1_1.png`;     

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
                        'raster-opacity': i === pastFrames.length - 1 ? 0.7 : 0,
                        'raster-fade-duration': 0
                    }
                });

                this.radarLayers.push(layerId);
            }

            await this.waitForTilesToLoad();
            this.updateTimestamp(this.availableTimes.length - 1);
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
            const startTime = Date.now();
            const checkInterval = setInterval(() => {
                if (this.mapInstance.loaded() || Date.now() - startTime > 5000) {
                    clearInterval(checkInterval);
                    resolve();
                }
            }, 500);
        });
    }

    showRadarError(message) {
        if (this.timestampElement) {
            this.timestampElement.textContent = message;
            this.timestampElement.style.background = 'rgba(220, 38, 38, 0.8)';
        }
    }

    async refreshRadarData() {
        if (this.isRefreshing) return;
        this.isRefreshing = true;

        const oldLayers = [...this.radarLayers];
        const oldInterval = this.animationInterval;

        try {
            const apiUrl = 'https://api.rainviewer.com/public/weather-maps.json';
            const response = await fetch(apiUrl, { cache: 'no-cache' });
            const data = await response.json();

            if (!data.radar || !data.radar.past) {
                this.isRefreshing = false;
                return;
            }

            const framesCount = this.config.frames || 5;
            const newFrames = data.radar.past.slice(-framesCount);
            const newTimes = newFrames.map(item => item.time);

            if (newTimes[newTimes.length - 1] <= this.availableTimes[this.availableTimes.length - 1]) {
                this.isRefreshing = false;
                return;
            }

            const host = data.host || 'https://tilecache.rainviewer.com';
            const newLayers = [];
            const newLayerPrefix = `radar-layer-new-${Date.now()}-`;

            for (let i = 0; i < newFrames.length; i++) {
                const layerId = `${newLayerPrefix}${i}`;
                const framePath = newFrames[i].path;
                const tileUrl = `${host}${framePath}/256/{z}/{x}/{y}/2/1_1.png`;

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
                    paint: { 'raster-opacity': 0, 'raster-fade-duration': 0 }
                });

                newLayers.push(layerId);
            }

            // Short delay to let new tiles buffer
            await new Promise(resolve => setTimeout(resolve, 3000));

            if (oldInterval) clearInterval(oldInterval);

            this.radarLayers = newLayers;
            this.availableTimes = newTimes;
            this.currentFrame = 0;

            for (const layerId of oldLayers) {
                if (this.mapInstance.getLayer(layerId)) this.mapInstance.removeLayer(layerId);
                if (this.mapInstance.getSource(layerId)) this.mapInstance.removeSource(layerId);
            }

            this.startAnimation();

        } catch (error) {
            console.error('Error refreshing radar:', error);
        } finally {
            this.isRefreshing = false;
        }
    }

    startAnimation() {
        if (this.animationInterval) clearInterval(this.animationInterval);
        if (this.radarLayers.length <= 1) return;

        this.currentFrame = 0;
        this.animationInterval = setInterval(() => {
            const currentLayer = this.radarLayers[this.currentFrame];
            if (this.mapInstance.getLayer(currentLayer)) {
                this.mapInstance.setPaintProperty(currentLayer, 'raster-opacity', 0);
            }

            this.currentFrame = (this.currentFrame + 1) % this.radarLayers.length;

            const nextLayer = this.radarLayers[this.currentFrame];
            if (this.mapInstance.getLayer(nextLayer)) {
                this.mapInstance.setPaintProperty(nextLayer, 'raster-opacity', 0.7);
                this.updateTimestamp(this.currentFrame);
            }
        }, 800);
    }

    destroy() {
        if (this.animationInterval) clearInterval(this.animationInterval);
        if (this.mapInstance) this.mapInstance.remove();
    }
}

let radarWidget = null;

async function loadRadar() {
    try {
        const response = await fetch('/api/radar/config');
        const data = await response.json();

        if (data.success && data.radar_config.enabled) {
            radarWidget = new RadarWidget('radar-widget', data.radar_config);
        } else {
            document.getElementById('radar-widget').innerHTML = 
                '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:var(--card-text);">Radar disabled</div>';
        }
    } catch (error) {
        console.error('Failed to load radar:', error);
    }
}

document.addEventListener('DOMContentLoaded', loadRadar);