// camera.js - Camera carousel and image management
// COMPLETE REPLACEMENT FOR static/js/camera.js

// ============================================================================
// CAMERA CAROUSEL MANAGEMENT
// ============================================================================

const cameras = {};

// Initialize camera data structures - MORE ROBUST VERSION
function initializeCameras() {
    console.log('Initializing camera carousels...');
    
    // Clear existing cameras object
    Object.keys(cameras).forEach(key => delete cameras[key]);
    
    // Find all camera cards
    document.querySelectorAll('.camera-card').forEach(card => {
        const cameraName = card.dataset.camera;
        if (!cameraName) {
            console.warn('Camera card found without data-camera attribute');
            return;
        }
        
        const images = card.querySelectorAll(`.camera-image[data-camera="${cameraName}"]`);
        const dots = card.querySelectorAll(`.nav-dot[data-camera="${cameraName}"]`);
        
        if (images.length > 0) {
            cameras[cameraName] = {
                currentIndex: 0,
                images: images,
                dots: dots
            };
            console.log(`✓ Initialized carousel for ${cameraName}: ${images.length} images`);
        } else {
            console.warn(`No images found for camera: ${cameraName}`);
        }
    });
    
    console.log(`Total cameras initialized: ${Object.keys(cameras).length}`);
}

// Call initialization on load
document.addEventListener('DOMContentLoaded', function() {
    initializeCameras();
    
    // Initialize timestamps for all cameras
    Object.keys(cameras).forEach(cameraName => {
        const cam = cameras[cameraName];
        if (cam.images.length > 0) {
            const firstImage = cam.images[0];
            const filename = firstImage.dataset.filename || firstImage.src.split('/').pop().split('?')[0];
            updateImageTimestamp(cameraName, filename);
        }
    });
});

// ============================================================================
// IMAGE SWITCHING
// ============================================================================

function switchImage(cameraName, index) {
    const cam = cameras[cameraName];
    if (!cam) {
        console.error(`Camera not found: ${cameraName}`);
        return;
    }

    // Remove active class from all images and dots
    cam.images.forEach(img => img.classList.remove('active'));
    cam.dots.forEach(dot => dot.classList.remove('active'));

    // Add active class to selected image and dot
    if (cam.images[index]) {
        cam.images[index].classList.add('active');
    }
    if (cam.dots[index]) {
        cam.dots[index].classList.add('active');
    }

    cam.currentIndex = index;

    // Update timestamp
    const activeImage = cam.images[index];
    if (activeImage) {
        const filename = activeImage.dataset.filename || activeImage.src.split('/').pop().split('?')[0];
        updateImageTimestamp(cameraName, filename);
    }
}

// ============================================================================
// AUTO-CYCLE IMAGES
// ============================================================================

setInterval(() => {
    Object.keys(cameras).forEach(cameraName => {
        const cam = cameras[cameraName];
        if (cam && cam.images.length > 1) {
            const nextIndex = (cam.currentIndex + 1) % cam.images.length;
            switchImage(cameraName, nextIndex);
        }
    });
}, 3000);

// ============================================================================
// NAV DOT CLICK HANDLERS - DELEGATE TO CONTAINER
// ============================================================================

document.addEventListener('click', function(e) {
    if (e.target.classList.contains('nav-dot')) {
        const cameraName = e.target.dataset.camera;
        const index = parseInt(e.target.dataset.index);
        
        if (cameraName && !isNaN(index)) {
            switchImage(cameraName, index);
        }
    }
});

// ============================================================================
// TIMESTAMP EXTRACTION & DISPLAY
// ============================================================================

function updateImageTimestamp(cameraName, filename) {
    const el = document.getElementById(`timestamp-${cameraName}`);
    if (!el) return;

    // Extract from path if it contains date folder (e.g., "2025-01-23/camera_20250123_120000.jpg")
    let filenameOnly = filename;
    if (filename.includes('/')) {
        filenameOnly = filename.split('/').pop();
    }

    const match = filenameOnly.match(/_(\d{8})_(\d{6})/);
    if (match) {
        const dateStr = match[1]; // YYYYMMDD
        const timeStr = match[2]; // HHMMSS

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
// STALE IMAGE DETECTION
// ============================================================================

function checkForStaleImages() {
    const pollInterval = window.BlinkConfig.POLL_INTERVAL_MINUTES || 5;
    const staleThreshold = pollInterval * 3; // 3x poll interval = stale
    
    document.querySelectorAll('.camera-card').forEach(card => {
        const cameraName = card.dataset.camera;
        
        // Get ALL images for this camera
        const allImages = card.querySelectorAll('.camera-image');
        if (allImages.length === 0) return;
        
        // Find the NEWEST image (first one, they're sorted newest first)
        const newestImage = allImages[0];
        const filename = newestImage.dataset.filename || newestImage.src.split('/').pop().split('?')[0];
        
        // Extract from path if needed
        let filenameOnly = filename;
        if (filename.includes('/')) {
            filenameOnly = filename.split('/').pop();
        }
        
        // Extract timestamp from filename
        const match = filenameOnly.match(/_(\d{8})_(\d{6})/);
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
                    &#x26A0;&#xFE0F; STALE
                    <div style="font-size: 0.8em; margin-top: 2px;">
                        Last photo: ${formatTimeAgo(ageMinutes)}
                    </div>
                `;
                card.querySelector('.camera-image-container').appendChild(badge);
            }
            
            // Update the badge time
            const existingBadge = card.querySelector('.stale-badge');
            if (existingBadge) {
                existingBadge.innerHTML = `
                    &#x26A0;&#xFE0F; STALE
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

function formatTimeAgo(minutes) {
    if (minutes < 60) {
        return `${Math.floor(minutes)}m ago`;
    } else if (minutes < 1440) {
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
    setTimeout(() => {
        checkForStaleImages();
    }, 1000);
});

// Check every minute
setInterval(checkForStaleImages, 60000);

// ============================================================================
// EXPOSE FOR USE BY OTHER MODULES
// ============================================================================

window.cameras = cameras;
window.initializeCameras = initializeCameras;
window.switchImage = switchImage;
window.updateImageTimestamp = updateImageTimestamp;
window.checkForStaleImages = checkForStaleImages;