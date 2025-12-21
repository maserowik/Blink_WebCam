// camera.js - Camera carousel and image management

// ============================================================================
// CAMERA CAROUSEL MANAGEMENT
// ============================================================================

const cameras = {};

// Initialize camera data structures
document.querySelectorAll('.camera-image').forEach(img => {
    const cam = img.dataset.camera;
    if (!cameras[cam]) {
        cameras[cam] = {
            currentIndex: 0,
            images: document.querySelectorAll(`.camera-image[data-camera="${cam}"]`),
            dots: document.querySelectorAll(`.nav-dot[data-camera="${cam}"]`)
        };
    }
});

// ============================================================================
// IMAGE SWITCHING
// ============================================================================

function switchImage(cameraName, index) {
    const cam = cameras[cameraName];
    if (!cam) return;

    cam.images.forEach(img => img.classList.remove('active'));
    cam.dots.forEach(dot => dot.classList.remove('active'));

    cam.images[index].classList.add('active');
    if (cam.dots[index]) cam.dots[index].classList.add('active');

    cam.currentIndex = index;

    const activeImage = cam.images[index];
    if (activeImage) {
        const filename = activeImage.dataset.filename || activeImage.src.split('/').pop();
        updateImageTimestamp(cameraName, filename);
    }
}

// ============================================================================
// AUTO-CYCLE IMAGES
// ============================================================================

setInterval(() => {
    Object.keys(cameras).forEach(cameraName => {
        const cam = cameras[cameraName];
        if (cam.images.length > 1) {
            const nextIndex = (cam.currentIndex + 1) % cam.images.length;
            switchImage(cameraName, nextIndex);
        }
    });
}, 3000);

// ============================================================================
// NAV DOT CLICK HANDLERS
// ============================================================================

document.querySelectorAll('.nav-dot').forEach(dot => {
    dot.addEventListener('click', e => {
        const cam = e.target.dataset.camera;
        const idx = parseInt(e.target.dataset.index);
        switchImage(cam, idx);
    });
});

// ============================================================================
// TIMESTAMP EXTRACTION & DISPLAY
// ============================================================================

function updateImageTimestamp(cameraName, filename) {
    const el = document.getElementById(`timestamp-${cameraName}`);
    if (!el) return;

    const match = filename.match(/_(\d{8})_(\d{6})/);
    if (match) {
        const dateStr = match[1];
        const timeStr = match[2];

        const year = dateStr.substring(0, 4);
        const month = dateStr.substring(4, 6);
        const day = dateStr.substring(6, 8);

        let hours = parseInt(timeStr.substring(0, 2));
        const minutes = timeStr.substring(2, 4);
        const seconds = timeStr.substring(4, 6);

        const ampm = hours >= 12 ? 'PM' : 'AM';
        hours = hours % 12;
        hours = hours ? hours : 12;

        const formattedTime = `${hours}:${minutes}:${seconds} ${ampm}`;
        const formattedDate = `${month}/${day}/${year}`;

        el.textContent = `${formattedDate} ${formattedTime}`;
    } else {
        el.textContent = 'Unknown time';
    }
}

// ============================================================================
// INITIALIZE TIMESTAMPS
// ============================================================================

document.addEventListener('DOMContentLoaded', function() {
    Object.keys(cameras).forEach(cameraName => {
        const cam = cameras[cameraName];
        if (cam.images.length > 0) {
            const firstImage = cam.images[0];
            const filename = firstImage.dataset.filename || firstImage.src.split('/').pop();
            updateImageTimestamp(cameraName, filename);
        }
    });
});

// ============================================================================
// STALE IMAGE DETECTION (FIXED - checks newest image, not active one)
// ============================================================================

function checkForStaleImages() {
    const pollInterval = window.BlinkConfig.POLL_INTERVAL_MINUTES || 5;
    const staleThreshold = pollInterval * 3; // 3x poll interval = stale
    
    document.querySelectorAll('.camera-card').forEach(card => {
        const cameraName = card.dataset.camera;
        
        // Get ALL images for this camera, not just the active one
        const allImages = card.querySelectorAll('.camera-image');
        if (allImages.length === 0) return;
        
        // Find the NEWEST image (they're sorted newest first in HTML)
        const newestImage = allImages[0];
        const filename = newestImage.dataset.filename || newestImage.src.split('/').pop();
        
        // Extract timestamp from filename
        const match = filename.match(/_(\d{8})_(\d{6})/);
        if (!match) return;
        
        const dateStr = match[1];
        const timeStr = match[2];
        
        const year = dateStr.substring(0, 4);
        const month = dateStr.substring(4, 6);
        const day = dateStr.substring(6, 8);
        
        let hours = parseInt(timeStr.substring(0, 2));
        const minutes = timeStr.substring(2, 4);
        const seconds = timeStr.substring(4, 6);
        
        const imageTime = new Date(year, month - 1, day, hours, minutes, seconds);
        
        const now = new Date();
        const ageMinutes = (now - imageTime) / (1000 * 60);
        
        // If image is older than 3x the poll interval, mark as stale
        if (ageMinutes > staleThreshold) {
            card.classList.add('stale-images');
            
            // Add warning badge if it doesn't exist
            if (!card.querySelector('.stale-badge')) {
                const badge = document.createElement('div');
                badge.className = 'stale-badge';
                badge.innerHTML = `
                    ⚠️ STALE
                    <div style="font-size: 0.8em; margin-top: 2px;">
                        Last photo: ${formatTimeAgo(ageMinutes)}
                    </div>
                `;
                card.querySelector('.camera-image-container').appendChild(badge);
            }
            
            // Update the badge time every check
            const existingBadge = card.querySelector('.stale-badge');
            if (existingBadge) {
                existingBadge.innerHTML = `
                    ⚠️ STALE
                    <div style="font-size: 0.8em; margin-top: 2px;">
                        Last photo: ${formatTimeAgo(ageMinutes)}
                    </div>
                `;
            }
        } else {
            card.classList.remove('stale-images');
            const staleBadge = card.querySelector('.stale-badge');
            if (staleBadge) staleBadge.remove();
        }
    });
}

function parseImageTimestamp(timestampText) {
    // Parse "MM/DD/YYYY HH:MM:SS AM/PM" format
    try {
        const match = timestampText.match(/(\d{1,2})\/(\d{1,2})\/(\d{4})\s+(\d{1,2}):(\d{2}):(\d{2})\s+(AM|PM)/);
        if (!match) return null;
        
        const [, month, day, year, hours, minutes, seconds, ampm] = match;
        let hour = parseInt(hours);
        
        if (ampm === 'PM' && hour !== 12) hour += 12;
        if (ampm === 'AM' && hour === 12) hour = 0;
        
        return new Date(year, month - 1, day, hour, minutes, seconds);
    } catch (e) {
        console.error('Error parsing timestamp:', e);
        return null;
    }
}

function formatTimeAgo(minutes) {
    if (minutes < 60) {
        return `${Math.floor(minutes)}m ago`;
    } else if (minutes < 1440) { // Less than 24 hours
        const hours = Math.floor(minutes / 60);
        return `${hours}h ago`;
    } else {
        const days = Math.floor(minutes / 1440);
        return `${days}d ago`;
    }
}

// ============================================================================
// AUTO-CHECK FOR STALE IMAGES
// ============================================================================

// Check on page load
document.addEventListener('DOMContentLoaded', function() {
    // Wait a bit for timestamps to be initialized
    setTimeout(() => {
        checkForStaleImages();
    }, 1000);
});

// Check every minute
setInterval(checkForStaleImages, 60000);