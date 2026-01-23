// camera-refresh.js - FIXED: Proper camera auto-refresh with cache busting
// This version properly detects new images and forces browser to reload them

// ============================================================================
// DYNAMIC CAMERA REFRESH - FIXED VERSION
// ============================================================================

async function refreshCameras() {
    console.log('=== CAMERA REFRESH CYCLE START ===');
    console.log('Time:', new Date().toLocaleTimeString());

    try {
        const response = await fetch('/api/cameras/refresh?' + Date.now()); // Cache bust API call
        const data = await response.json();

        if (!data.success) {
            throw new Error('Failed to refresh cameras');
        }

        const cameras = data.cameras;
        console.log(`Received data for ${cameras.length} cameras`);

        // Update each camera card dynamically
        for (const camera of cameras) {
            console.log(`\n--- Processing: ${camera.name} ---`);
            const card = document.querySelector(`.camera-card[data-camera="${camera.normalized_name}"]`);
            if (!card) {
                console.warn(`Card not found for ${camera.name}`);
                continue;
            }

            // Update timestamp
            const timestampEl = document.getElementById(`timestamp-${camera.normalized_name}`);
            if (timestampEl && camera.last_update_formatted) {
                timestampEl.textContent = camera.last_update_formatted;
            }

            // Update temperature
            const tempEl = document.getElementById(`temp-${camera.normalized_name}`);
            const tempStat = document.querySelector(`[data-camera="${camera.normalized_name}"][data-temperature]`);
            if (tempEl && tempStat) {
                tempEl.textContent = camera.temperature;
                tempStat.setAttribute('data-temperature', camera.temperature);

                // Recheck temperature alerts
                const temp = parseTemperature(camera.temperature);
                tempStat.classList.remove('alert', 'critical');

                if (temp !== null) {
                    if (temp >= window.BlinkConfig.TEMP_HOT_THRESHOLD) {
                        tempStat.classList.add('alert');
                        if (!tempEl.textContent.includes('\uD83D\uDD25')) {
                            tempEl.innerHTML = '&#x1F525; ' + camera.temperature;
                        }
                    } else if (temp <= window.BlinkConfig.TEMP_COLD_THRESHOLD) {
                        tempStat.classList.add('alert');
                        if (!tempEl.textContent.includes('\u2744')) {
                            tempEl.innerHTML = '&#x2744;&#xFE0F; ' + camera.temperature;
                        }
                    }
                }
            }

            // Update battery
            const batteryEl = document.getElementById(`battery-${camera.normalized_name}`);
            const batteryStat = document.querySelector(`[data-camera="${camera.normalized_name}"][data-battery]`);
            if (batteryEl && batteryStat) {
                batteryEl.textContent = camera.battery;
                batteryStat.setAttribute('data-battery', camera.battery);

                // Recheck battery alerts
                const battery = parseBattery(camera.battery);
                batteryStat.classList.remove('critical');

                if (battery !== null && battery <= window.BlinkConfig.BATTERY_LOW_THRESHOLD) {
                    batteryStat.classList.add('critical');
                    if (!batteryEl.textContent.includes('\u26A0')) {
                        batteryEl.innerHTML = '&#x26A0;&#xFE0F; ' + camera.battery;
                    }
                }
            }

            // Update WiFi bars
            const wifiBarsContainer = card.querySelector('.wifi-bars');
            if (wifiBarsContainer) {
                const bars = wifiBarsContainer.querySelectorAll('.wifi-bar');
                bars.forEach((bar, index) => {
                    if (index < camera.wifi) {
                        bar.classList.add('active');
                    } else {
                        bar.classList.remove('active');
                    }
                });
            }

            // Update images if new images are available
            if (camera.images && camera.images.length > 0) {
                await updateCameraImages(camera);
            }

            // Update offline status
            if (camera.images.length === 0) {
                card.classList.add('offline');
            } else {
                card.classList.remove('offline');
            }
        }

        // Refresh snooze badges
        await refreshSnoozeBadges();

        // Recheck stale images
        checkForStaleImages();

        console.log('=== CAMERA REFRESH CYCLE COMPLETE ===\n');

    } catch (error) {
        console.error('ERROR in camera refresh:', error);
    }
}

// ============================================================================
// UPDATE CAMERA IMAGES DYNAMICALLY - FIXED VERSION
// ============================================================================

async function updateCameraImages(camera) {
    const card = document.querySelector(`.camera-card[data-camera="${camera.normalized_name}"]`);
    if (!card) return;

    const imageContainer = card.querySelector('.camera-image-container');
    if (!imageContainer) return;

    // Get existing image PATHS from data-filename attributes
    const existingImages = Array.from(card.querySelectorAll('.camera-image'));
    const existingPaths = existingImages.map(img => img.dataset.filename || '');

    console.log(`  Existing images (${existingPaths.length}):`, existingPaths.slice(0, 2));
    console.log(`  New images (${camera.images.length}):`, camera.images.slice(0, 2));

    // Compare the NEWEST image (first in array) to see if it's different
    const newestExisting = existingPaths[0];
    const newestNew = camera.images[0];

    const hasNewImage = newestNew !== newestExisting;

    if (hasNewImage) {
        console.log(`  \u2705 NEW IMAGE DETECTED!`);
        console.log(`    Old: ${newestExisting}`);
        console.log(`    New: ${newestNew}`);

        // Save current active index before rebuilding
        const currentActiveImg = card.querySelector('.camera-image.active');
        let currentIndex = 0;
        if (currentActiveImg) {
            currentIndex = parseInt(currentActiveImg.dataset.index) || 0;
        }

        // Remove old images and navigation
        existingImages.forEach(img => img.remove());
        const oldNav = card.querySelector('.image-nav');
        if (oldNav) oldNav.remove();

        // Add new images with cache-busting timestamp
        const cacheBuster = Date.now();
        camera.images.forEach((imagePath, index) => {
            const img = document.createElement('img');
            // CRITICAL: Add cache-busting query parameter to force browser reload
            img.src = `/image/${camera.normalized_name}/${imagePath}?t=${cacheBuster}`;
            img.alt = camera.name;
            img.className = `camera-image ${index === 0 ? 'active' : ''}`;
            img.dataset.camera = camera.normalized_name;
            img.dataset.index = index;
            img.dataset.filename = imagePath;

            // Force image to load immediately
            img.loading = 'eager';

            imageContainer.appendChild(img);
        });

        // Add navigation dots if multiple images
        if (camera.images.length > 1) {
            const nav = document.createElement('div');
            nav.className = 'image-nav';

            camera.images.forEach((imagePath, index) => {
                const dot = document.createElement('div');
                dot.className = `nav-dot ${index === 0 ? 'active' : ''}`;
                dot.dataset.camera = camera.normalized_name;
                dot.dataset.index = index;
                dot.addEventListener('click', (e) => {
                    switchImage(camera.normalized_name, index);
                });
                nav.appendChild(dot);
            });

            imageContainer.appendChild(nav);
        }

        // Reinitialize camera data structure in camera.js
        if (window.cameras && window.cameras[camera.normalized_name]) {
            window.cameras[camera.normalized_name] = {
                currentIndex: 0,
                images: document.querySelectorAll(`.camera-image[data-camera="${camera.normalized_name}"]`),
                dots: document.querySelectorAll(`.nav-dot[data-camera="${camera.normalized_name}"]`)
            };
        }

        // Update timestamp for first (newest) image
        if (camera.images.length > 0) {
            updateImageTimestamp(camera.normalized_name, camera.images[0]);
        }

        console.log(`  \u2705 Images refreshed successfully`);
    } else {
        console.log(`  - No new images (newest image unchanged)`);
    }
}

// ============================================================================
// SCHEDULED CAMERA REFRESH - OPTIMIZED TIMING
// ============================================================================

function startCameraAutoRefresh() {
    const pollIntervalMinutes = window.BlinkConfig.POLL_INTERVAL_MINUTES || 5;
    const pollIntervalMs = pollIntervalMinutes * 60 * 1000;

    console.log(`\u2705 Camera auto-refresh enabled: every ${pollIntervalMinutes} minutes`);
    console.log(`Next refresh at: ${new Date(Date.now() + pollIntervalMs).toLocaleTimeString()}`);

    // CRITICAL FIX: Refresh IMMEDIATELY after 30 seconds (catch first update quickly)
    setTimeout(() => {
        console.log('\n\u27A1 Running INITIAL camera refresh (30s after page load)...');
        refreshCameras().then(() => {
            const nextRefresh = new Date(Date.now() + pollIntervalMs);
            console.log(`Next scheduled refresh: ${nextRefresh.toLocaleTimeString()}\n`);
        });
    }, 30000);

    // Then refresh at poll interval (every 5 minutes by default)
    setInterval(() => {
        console.log('\n\u27A1 Running SCHEDULED camera refresh...');
        refreshCameras().then(() => {
            const nextRefresh = new Date(Date.now() + pollIntervalMs);
            console.log(`Next scheduled refresh: ${nextRefresh.toLocaleTimeString()}\n`);
        });
    }, pollIntervalMs);

    // ADDITIONAL: Check more frequently during first 15 minutes (catch updates faster)
    let quickCheckCount = 0;
    const maxQuickChecks = 3; // Check at 2min, 4min, 6min marks
    const quickCheckInterval = setInterval(() => {
        quickCheckCount++;
        if (quickCheckCount > maxQuickChecks) {
            clearInterval(quickCheckInterval);
            console.log('Quick-check period ended, switching to normal schedule');
            return;
        }
        console.log(`\n\u27A1 Running QUICK CHECK #${quickCheckCount}...`);
        refreshCameras();
    }, 120000); // Every 2 minutes for first 6 minutes
}

// ============================================================================
// INITIALIZE AUTO-REFRESH
// ============================================================================

document.addEventListener('DOMContentLoaded', function() {
    console.log('\n==============================================');
    console.log('CAMERA AUTO-REFRESH SYSTEM INITIALIZED');
    console.log('==============================================');
    console.log('Strategy:');
    console.log('  1. Initial check: 30 seconds after page load');
    console.log('  2. Quick checks: Every 2 minutes (first 6 minutes)');
    console.log(`  3. Normal schedule: Every ${window.BlinkConfig.POLL_INTERVAL_MINUTES} minutes`);
    console.log('==============================================\n');

    startCameraAutoRefresh();
});

// ============================================================================
// MANUAL REFRESH FUNCTION (for testing)
// ============================================================================

window.manualRefreshCameras = refreshCameras;

// ============================================================================
// DEBUG: Monitor image loading
// ============================================================================

if (window.location.search.includes('debug=1')) {
    document.addEventListener('DOMContentLoaded', function() {
        // Log when images load
        document.addEventListener('load', function(e) {
            if (e.target.tagName === 'IMG' && e.target.classList.contains('camera-image')) {
                console.log('Image loaded:', e.target.src.split('/').pop());
            }
        }, true);

        // Log when images fail to load
        document.addEventListener('error', function(e) {
            if (e.target.tagName === 'IMG' && e.target.classList.contains('camera-image')) {
                console.error('Image failed to load:', e.target.src);
            }
        }, true);
    });
}