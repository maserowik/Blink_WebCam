// camera-refresh.js - Enhanced camera auto-refresh with better reliability
// COMPLETE REPLACEMENT FOR static/js/camera-refresh.js

// ============================================================================
// DYNAMIC CAMERA REFRESH - ENHANCED VERSION
// ============================================================================

let lastRefreshTime = null;
let refreshInProgress = false;

async function refreshCameras() {
    // Prevent concurrent refreshes
    if (refreshInProgress) {
        console.log('Refresh already in progress, skipping...');
        return;
    }

    refreshInProgress = true;
    console.log('='.repeat(60));
    console.log('Refreshing camera data...');
    console.log('Last refresh:', lastRefreshTime ? lastRefreshTime.toLocaleTimeString() : 'Never');

    try {
        const response = await fetch('/api/cameras/refresh', {
            method: 'GET',
            headers: {
                'Accept': 'application/json',
                'Cache-Control': 'no-cache'
            }
        });

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        const data = await response.json();

        if (!data.success) {
            throw new Error(data.error || 'Failed to refresh cameras');
        }

        const cameras = data.cameras;
        console.log(`Received data for ${cameras.length} camera(s)`);

        // Track update statistics
        let updatedCount = 0;
        let skippedCount = 0;

        // Update each camera card dynamically
        for (const camera of cameras) {
            const card = document.querySelector(`.camera-card[data-camera="${camera.normalized_name}"]`);
            if (!card) {
                console.warn(`Card not found for camera: ${camera.normalized_name}`);
                continue;
            }

            console.log(`Processing camera: ${camera.name}`);

            // Update timestamp
            const timestampEl = document.getElementById(`timestamp-${camera.normalized_name}`);
            if (timestampEl && camera.last_update_formatted) {
                const oldTimestamp = timestampEl.textContent;
                timestampEl.textContent = camera.last_update_formatted;
                if (oldTimestamp !== camera.last_update_formatted) {
                    console.log(`  ✓ Timestamp updated: ${camera.last_update_formatted}`);
                }
            }

            // Update temperature
            updateTemperature(camera, card);

            // Update battery
            updateBattery(camera, card);

            // Update WiFi bars
            updateWiFi(camera, card);

            // Update images if new images are available
            const imagesUpdated = await updateCameraImages(camera, card);
            if (imagesUpdated) {
                updatedCount++;
            } else {
                skippedCount++;
            }

            // Update offline status
            updateOfflineStatus(camera, card);

            // Update alert badges
            updateAlertBadges(camera, card);
        }

        // Refresh snooze badges
        await refreshSnoozeBadges();

        // Recheck stale images
        checkForStaleImages();

        lastRefreshTime = new Date();
        console.log(`Camera refresh complete: ${updatedCount} updated, ${skippedCount} unchanged`);
        console.log('='.repeat(60));

    } catch (error) {
        console.error('ERROR: Camera refresh failed:', error);
        console.error('Stack trace:', error.stack);
    } finally {
        refreshInProgress = false;
    }
}

// ============================================================================
// UPDATE TEMPERATURE
// ============================================================================

function updateTemperature(camera, card) {
    const tempEl = document.getElementById(`temp-${camera.normalized_name}`);
    const tempStat = card.querySelector(`[data-temperature]`);
    
    if (!tempEl || !tempStat) return;

    const oldTemp = tempEl.textContent;
    tempEl.textContent = camera.temperature;
    tempStat.setAttribute('data-temperature', camera.temperature);

    // Recheck temperature alerts
    const temp = parseTemperature(camera.temperature);
    tempStat.classList.remove('alert', 'critical');

    if (temp !== null) {
        if (temp >= window.BlinkConfig.TEMP_HOT_THRESHOLD) {
            tempStat.classList.add('alert');
            if (!tempEl.textContent.includes('🔥')) {
                tempEl.innerHTML = '&#x1F525; ' + camera.temperature;
            }
        } else if (temp <= window.BlinkConfig.TEMP_COLD_THRESHOLD) {
            tempStat.classList.add('alert');
            if (!tempEl.textContent.includes('❄')) {
                tempEl.innerHTML = '&#x2744;&#xFE0F; ' + camera.temperature;
            }
        }
    }

    if (oldTemp !== camera.temperature) {
        console.log(`  ✓ Temperature updated: ${camera.temperature}`);
    }
}

// ============================================================================
// UPDATE BATTERY
// ============================================================================

function updateBattery(camera, card) {
    const batteryEl = document.getElementById(`battery-${camera.normalized_name}`);
    const batteryStat = card.querySelector(`[data-battery]`);
    
    if (!batteryEl || !batteryStat) return;

    const oldBattery = batteryEl.textContent;
    batteryEl.textContent = camera.battery;
    batteryStat.setAttribute('data-battery', camera.battery);

    // Recheck battery alerts
    const battery = parseBattery(camera.battery);
    batteryStat.classList.remove('critical');

    if (battery !== null && battery <= window.BlinkConfig.BATTERY_LOW_THRESHOLD) {
        batteryStat.classList.add('critical');
        if (!batteryEl.textContent.includes('⚠')) {
            batteryEl.innerHTML = '&#x26A0;&#xFE0F; ' + camera.battery;
        }
    }

    if (oldBattery !== camera.battery) {
        console.log(`  ✓ Battery updated: ${camera.battery}`);
    }
}

// ============================================================================
// UPDATE WIFI
// ============================================================================

function updateWiFi(camera, card) {
    const wifiBarsContainer = card.querySelector('.wifi-bars');
    if (!wifiBarsContainer) return;

    const bars = wifiBarsContainer.querySelectorAll('.wifi-bar');
    bars.forEach((bar, index) => {
        if (index < camera.wifi) {
            bar.classList.add('active');
        } else {
            bar.classList.remove('active');
        }
    });
}

// ============================================================================
// UPDATE OFFLINE STATUS
// ============================================================================

function updateOfflineStatus(camera, card) {
    if (camera.images.length === 0) {
        card.classList.add('offline', 'camera-offline');
    } else {
        card.classList.remove('offline', 'camera-offline');
    }
}

// ============================================================================
// UPDATE ALERT BADGES
// ============================================================================

function updateAlertBadges(camera, card) {
    // Update offline badge
    const offlineBadge = card.querySelector('.camera-offline-badge');
    if (camera.alerts && camera.alerts.is_offline) {
        if (!offlineBadge) {
            const badge = document.createElement('div');
            badge.className = 'camera-offline-badge';
            badge.innerHTML = `
                <div style="font-size: 1.2em;">&#x1F534; OFFLINE</div>
                <div style="font-size: 0.85em; margin-top: 2px;">
                    ${camera.alerts.offline_reason}
                </div>
            `;
            card.querySelector('.camera-image-container').appendChild(badge);
        }
    } else if (offlineBadge) {
        offlineBadge.remove();
    }

    // Update duplicate badge
    const duplicateBadge = card.querySelector('.camera-duplicate-badge');
    if (camera.alerts && camera.alerts.has_duplicates && !camera.alerts.is_offline) {
        if (!duplicateBadge) {
            const badge = document.createElement('div');
            badge.className = 'camera-duplicate-badge';
            badge.innerHTML = '&#x26A0;&#xFE0F; DUPLICATE IMAGES';
            card.querySelector('.camera-image-container').appendChild(badge);
        }
    } else if (duplicateBadge) {
        duplicateBadge.remove();
    }
}

// ============================================================================
// UPDATE CAMERA IMAGES DYNAMICALLY - ENHANCED
// ============================================================================

async function updateCameraImages(camera, card) {
    const imageContainer = card.querySelector('.camera-image-container');
    if (!imageContainer) {
        console.warn(`  No image container found for ${camera.name}`);
        return false;
    }

    // Get existing image elements and their paths
    const existingImages = Array.from(card.querySelectorAll('.camera-image'));
    const existingPaths = existingImages.map(img => {
        // Extract path from src: /image/{camera-name}/{path}
        const src = img.src;
        const match = src.match(/\/image\/[^\/]+\/(.+)$/);
        return match ? decodeURIComponent(match[1]) : '';
    }).filter(Boolean);

    console.log(`  Existing images (${existingPaths.length}):`, existingPaths);
    console.log(`  New images (${camera.images.length}):`, camera.images);

    // Compare paths to detect changes
    const hasNewImages = !arraysEqual(camera.images, existingPaths);

    if (!hasNewImages) {
        console.log(`  - No changes detected for ${camera.name}`);
        return false;
    }

    console.log(`  ✓ NEW IMAGES DETECTED for ${camera.name}`);

    // Save current active index to restore after rebuild
    const currentActiveImage = card.querySelector('.camera-image.active');
    let currentFilename = null;
    if (currentActiveImage) {
        currentFilename = currentActiveImage.dataset.filename;
    }

    // Remove old images and nav
    existingImages.forEach(img => img.remove());
    const oldNav = card.querySelector('.image-nav');
    if (oldNav) oldNav.remove();

    // Add new images
    camera.images.forEach((imagePath, index) => {
        const img = document.createElement('img');
        img.src = `/image/${camera.normalized_name}/${encodeURIComponent(imagePath)}`;
        img.alt = camera.name;
        img.className = `camera-image ${index === 0 ? 'active' : ''}`;
        img.dataset.camera = camera.normalized_name;
        img.dataset.index = index;
        img.dataset.filename = imagePath;

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
            dot.addEventListener('click', () => {
                switchImage(camera.normalized_name, index);
            });
            nav.appendChild(dot);
        });

        imageContainer.appendChild(nav);
    }

    // Reinitialize camera data structure in carousel
    if (window.cameras) {
        window.cameras[camera.normalized_name] = {
            currentIndex: 0,
            images: document.querySelectorAll(`.camera-image[data-camera="${camera.normalized_name}"]`),
            dots: document.querySelectorAll(`.nav-dot[data-camera="${camera.normalized_name}"]`)
        };
    }

    // Update timestamp for first image
    if (camera.images.length > 0) {
        updateImageTimestamp(camera.normalized_name, camera.images[0]);
    }

    console.log(`  ✓ Images refreshed for ${camera.name}`);
    return true;
}

// ============================================================================
// UTILITY: COMPARE ARRAYS
// ============================================================================

function arraysEqual(arr1, arr2) {
    if (arr1.length !== arr2.length) return false;
    
    for (let i = 0; i < arr1.length; i++) {
        if (arr1[i] !== arr2[i]) return false;
    }
    
    return true;
}

// ============================================================================
// SCHEDULED CAMERA REFRESH - ENHANCED
// ============================================================================

let refreshTimer = null;
let missedRefreshCount = 0;

function startCameraAutoRefresh() {
    const pollIntervalMinutes = window.BlinkConfig.POLL_INTERVAL_MINUTES || 5;
    const pollIntervalMs = pollIntervalMinutes * 60 * 1000;

    console.log('='.repeat(60));
    console.log('CAMERA AUTO-REFRESH INITIALIZED');
    console.log(`Poll interval: ${pollIntervalMinutes} minutes (${pollIntervalMs}ms)`);
    console.log('='.repeat(60));

    // Initial refresh after 15 seconds (faster initial load)
    setTimeout(() => {
        console.log('Running initial camera refresh...');
        refreshCameras();
    }, 15000);

    // Then refresh at poll interval
    refreshTimer = setInterval(() => {
        const now = new Date();
        console.log(`\n[${now.toLocaleTimeString()}] Running scheduled camera refresh...`);
        
        // Check if last refresh was too long ago
        if (lastRefreshTime) {
            const timeSinceLastRefresh = now - lastRefreshTime;
            const expectedInterval = pollIntervalMs;
            
            if (timeSinceLastRefresh > expectedInterval * 1.5) {
                missedRefreshCount++;
                console.warn(`WARNING: Refresh delayed by ${Math.round((timeSinceLastRefresh - expectedInterval) / 1000)}s`);
                console.warn(`Missed refresh count: ${missedRefreshCount}`);
            }
        }
        
        refreshCameras();
    }, pollIntervalMs);

    // Health check every minute
    setInterval(() => {
        if (refreshInProgress) {
            console.warn('HEALTH CHECK: Refresh has been in progress for >1 minute');
        }
    }, 60000);
}

// ============================================================================
// STOP AUTO-REFRESH (for cleanup)
// ============================================================================

function stopCameraAutoRefresh() {
    if (refreshTimer) {
        clearInterval(refreshTimer);
        refreshTimer = null;
        console.log('Camera auto-refresh stopped');
    }
}

// ============================================================================
// INITIALIZE AUTO-REFRESH
// ============================================================================

document.addEventListener('DOMContentLoaded', function() {
    console.log('Initializing camera auto-refresh system...');
    startCameraAutoRefresh();
});

// ============================================================================
// MANUAL REFRESH FUNCTION (for testing)
// ============================================================================

window.manualRefreshCameras = refreshCameras;
window.stopCameraRefresh = stopCameraAutoRefresh;
window.startCameraRefresh = startCameraAutoRefresh;

// ============================================================================
// DEBUG: Log refresh statistics
// ============================================================================

window.getCameraRefreshStats = function() {
    return {
        lastRefreshTime: lastRefreshTime,
        refreshInProgress: refreshInProgress,
        missedRefreshCount: missedRefreshCount,
        pollInterval: window.BlinkConfig.POLL_INTERVAL_MINUTES + ' minutes'
    };
};