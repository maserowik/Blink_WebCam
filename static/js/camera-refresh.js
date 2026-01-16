// camera-refresh.js - Smart camera auto-refresh without full page reload
// FIXED: Proper image path comparison for date-organized folders

// ============================================================================
// DYNAMIC CAMERA REFRESH
// ============================================================================

async function refreshCameras() {
    console.log('Refreshing camera data...');

    try {
        const response = await fetch('/api/cameras/refresh');
        const data = await response.json();

        if (!data.success) {
            throw new Error('Failed to refresh cameras');
        }

        const cameras = data.cameras;

        // Update each camera card dynamically
        for (const camera of cameras) {
            const card = document.querySelector(`.camera-card[data-camera="${camera.normalized_name}"]`);
            if (!card) continue;

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
                    if (!batteryEl.textContent.includes('⚠')) {
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

        console.log('Camera refresh complete');

    } catch (error) {
        console.error('Error refreshing cameras:', error);
        // Don't show alert - fail silently and try again next interval
    }
}

// ============================================================================
// UPDATE CAMERA IMAGES DYNAMICALLY
// ============================================================================

async function updateCameraImages(camera) {
    const card = document.querySelector(`.camera-card[data-camera="${camera.normalized_name}"]`);
    if (!card) return;

    const imageContainer = card.querySelector('.camera-image-container');
    if (!imageContainer) return;

    // Get existing image PATHS (not just filenames)
    // camera.images from API contains paths like "2025-01-16/camera_20250116_120000.jpg"
    const existingImagePaths = Array.from(card.querySelectorAll('.camera-image')).map(img => {
        // Extract the path after /image/{camera-name}/
        const src = img.src;
        const parts = src.split(`/image/${camera.normalized_name}/`);
        return parts.length > 1 ? parts[1] : '';
    });

    console.log(`[${camera.name}] Existing images:`, existingImagePaths);
    console.log(`[${camera.name}] New images:`, camera.images);

    // Check if we have new images by comparing full paths
    const hasNewImages = camera.images.some(img => !existingImagePaths.includes(img));

    if (hasNewImages) {
        console.log(`✓ New images detected for ${camera.name}`);

        // Save current active index
        const currentIndex = cameras[camera.normalized_name]?.currentIndex || 0;

        // Rebuild image elements
        const oldImages = card.querySelectorAll('.camera-image');
        const oldNav = card.querySelector('.image-nav');

        oldImages.forEach(img => img.remove());
        if (oldNav) oldNav.remove();

        // Add new images
        camera.images.forEach((imagePath, index) => {
            const img = document.createElement('img');
            img.src = `/image/${camera.normalized_name}/${imagePath}`;
            img.alt = camera.name;
            img.className = `camera-image ${index === 0 ? 'active' : ''}`;
            img.dataset.camera = camera.normalized_name;
            img.dataset.index = index;
            img.dataset.filename = imagePath;  // Store full path

            imageContainer.appendChild(img);
        });

        // Add navigation dots if multiple images
        if (camera.images.length > 1) {
            const nav = document.createElement('div');
            nav.className = 'image-nav';

            camera.images.forEach((imagePath, index) => {
                const dot = document.createElement('dot');
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

        // Reinitialize camera data structure
        cameras[camera.normalized_name] = {
            currentIndex: 0,
            images: document.querySelectorAll(`.camera-image[data-camera="${camera.normalized_name}"]`),
            dots: document.querySelectorAll(`.nav-dot[data-camera="${camera.normalized_name}"]`)
        };

        // Update timestamp for first image
        if (camera.images.length > 0) {
            updateImageTimestamp(camera.normalized_name, camera.images[0]);
        }

        console.log(`✓ Images refreshed for ${camera.name}`);
    } else {
        console.log(`- No new images for ${camera.name}`);
    }
}

// ============================================================================
// SCHEDULED CAMERA REFRESH
// ============================================================================

function startCameraAutoRefresh() {
    const pollIntervalMinutes = window.BlinkConfig.POLL_INTERVAL_MINUTES || 5;
    const pollIntervalMs = pollIntervalMinutes * 60 * 1000;

    console.log(`Camera auto-refresh enabled: every ${pollIntervalMinutes} minutes`);

    // Initial refresh after 30 seconds (give page time to fully load)
    setTimeout(() => {
        console.log('Running initial camera refresh...');
        refreshCameras();
    }, 30000);

    // Then refresh at poll interval
    setInterval(() => {
        console.log('Running scheduled camera refresh...');
        refreshCameras();
    }, pollIntervalMs);
}

// ============================================================================
// INITIALIZE AUTO-REFRESH
// ============================================================================

document.addEventListener('DOMContentLoaded', function() {
    console.log('Initializing camera auto-refresh...');
    startCameraAutoRefresh();
});

// ============================================================================
// MANUAL REFRESH FUNCTION (for testing)
// ============================================================================

window.manualRefreshCameras = refreshCameras;