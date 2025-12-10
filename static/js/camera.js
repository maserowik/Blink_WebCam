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