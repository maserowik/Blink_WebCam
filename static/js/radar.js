// radar.js - Radar widget with Mapbox integration

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
            this.container.innerHTML = '<div id="radar-map" style="width:100%;height:100%;"></div>';

            // Determine basemap style
            let baseStyle = this.config.basemap_style || 'mapbox://styles/mapbox/dark-v11';
            if (!baseStyle.startsWith('mapbox://')) {
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

    async loadRadarData() {
        try {
            const frames = this.config.frames || 5;
            const times = [];
            const now = Math.floor(Date.now() / 1000);

            // Generate timestamps for radar frames (every 10 minutes back)
            for (let i = 0; i < frames; i++) {
                times.push(now - (i * 600)); // 600 seconds = 10 minutes
            }

            times.reverse(); // Oldest to newest

            // Add radar layers for each timestamp
            for (let i = 0; i < times.length; i++) {
                const layerId = `radar-layer-${i}`;
                const timestamp = times[i];

                // Use RainViewer API for radar data (free, no key required)
                const tileUrl = `https://tilecache.rainviewer.com/v2/radar/${timestamp}/256/{z}/{x}/{y}/2/1_1.png`;

                this.mapInstance.addSource(layerId, {
                    type: 'raster',
                    tiles: [tileUrl],
                    tileSize: 256,
                    opacity: 0.6
                });

                this.mapInstance.addLayer({
                    id: layerId,
                    type: 'raster',
                    source: layerId,
                    paint: {
                        'raster-opacity': i === times.length - 1 ? 0.7 : 0
                    }
                });

                this.radarLayers.push(layerId);
            }

            // Start animation
            this.startAnimation();

        } catch (error) {
            console.error('Error loading radar data:', error);
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