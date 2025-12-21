// snooze.js - Snooze modal and management functionality

// ============================================================================
// SNOOZE MODAL STATE
// ============================================================================

let currentSnoozeCamera = null;
let currentSnoozeCameraDisplay = null;
let selectedSnoozeDuration = null;
let currentSnoozeStatus = null;
let selectedSnoozeAllDuration = null;

// ============================================================================
// SINGLE CAMERA SNOOZE MODAL
// ============================================================================

async function openSnoozeModal(cameraName, cameraDisplay) {
    currentSnoozeCamera = cameraName;
    currentSnoozeCameraDisplay = cameraDisplay;
    selectedSnoozeDuration = null;

    document.getElementById('snooze-camera-display').textContent = `Camera: ${cameraDisplay}`;
    document.getElementById('snooze-custom-input').value = '';

    // Clear all selections
    document.querySelectorAll('#snooze-options .snooze-option').forEach(opt => {
        opt.classList.remove('selected');
    });

    // Check current snooze status
    try {
        const response = await fetch(`/api/snooze/status/${cameraName}`);
        const status = await response.json();
        currentSnoozeStatus = status;

        if (status.is_snoozed) {
            document.getElementById('snooze-expiry-time').textContent = status.snooze_until_full;
            document.getElementById('snooze-status-display').style.display = 'block';
            document.getElementById('snooze-cancel-btn').style.display = 'block';
        } else {
            document.getElementById('snooze-status-display').style.display = 'none';
            document.getElementById('snooze-cancel-btn').style.display = 'none';
        }
    } catch (error) {
        console.error('Error fetching snooze status:', error);
        document.getElementById('snooze-status-display').style.display = 'none';
        document.getElementById('snooze-cancel-btn').style.display = 'none';
    }

    document.getElementById('snooze-modal').classList.add('show');
}

function closeSnoozeModal() {
    document.getElementById('snooze-modal').classList.remove('show');
    currentSnoozeCamera = null;
    currentSnoozeCameraDisplay = null;
    selectedSnoozeDuration = null;
    currentSnoozeStatus = null;
}

async function applySnooze() {
    if (!currentSnoozeCamera) return;

    let duration = selectedSnoozeDuration;
    if (!duration) {
        const customValue = parseInt(document.getElementById('snooze-custom-input').value);
        if (customValue && customValue > 0) {
            duration = customValue;
        }
    }

    if (!duration) {
        alert('Please select a snooze duration');
        return;
    }

    try {
        const response = await fetch('/api/snooze/set', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                camera_name: currentSnoozeCamera,
                duration_minutes: duration
            })
        });

        const result = await response.json();

        if (result.success) {
            console.log(`Snoozed ${currentSnoozeCamera} for ${duration} minutes`);
            closeSnoozeModal();
            setTimeout(() => location.reload(), 500);
        } else {
            alert('Failed to apply snooze: ' + (result.error || 'Unknown error'));
        }
    } catch (error) {
        console.error('Error applying snooze:', error);
        alert('Error communicating with server');
    }
}

async function cancelSnooze() {
    if (!currentSnoozeCamera) return;

    if (!confirm(`Remove snooze for ${currentSnoozeCameraDisplay}?`)) {
        return;
    }

    try {
        const response = await fetch('/api/snooze/unset', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                camera_name: currentSnoozeCamera
            })
        });

        const result = await response.json();

        if (result.success) {
            console.log(`Removed snooze for ${currentSnoozeCamera}`);
            closeSnoozeModal();
            location.reload();
        } else {
            alert('Failed to remove snooze: ' + (result.error || 'Unknown error'));
        }
    } catch (error) {
        console.error('Error removing snooze:', error);
        alert('Error communicating with server');
    }
}

// ============================================================================
// SNOOZE ALL MODAL
// ============================================================================

async function openSnoozeAllModal() {
    selectedSnoozeAllDuration = null;
    document.getElementById('snooze-all-custom-input').value = '';
    
    document.querySelectorAll('#snooze-all-options .snooze-option').forEach(opt => {
        opt.classList.remove('selected');
    });
    
    document.getElementById('snooze-all-modal').classList.add('show');
}

function closeSnoozeAllModal() {
    document.getElementById('snooze-all-modal').classList.remove('show');
    selectedSnoozeAllDuration = null;
}

async function applySnoozeAll() {
    let duration = selectedSnoozeAllDuration;
    if (!duration) {
        const customValue = parseInt(document.getElementById('snooze-all-custom-input').value);
        if (customValue && customValue > 0) {
            duration = customValue;
        }
    }

    if (!duration) {
        alert('Please select a snooze duration');
        return;
    }

    try {
        const response = await fetch('/api/snooze/all/set', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                duration_minutes: duration
            })
        });

        const result = await response.json();

        if (result.success) {
            console.log(`Snoozed all ${result.count} cameras for ${duration} minutes`);
            closeSnoozeAllModal();
            setTimeout(() => location.reload(), 500);
        } else {
            alert('Failed to snooze all cameras: ' + (result.error || 'Unknown error'));
        }
    } catch (error) {
        console.error('Error snoozing all cameras:', error);
        alert('Error communicating with server');
    }
}

// ============================================================================
// SNOOZE ALL TOGGLE
// ============================================================================

let isTogglingSnoozeAll = false;

async function toggleSnoozeAll() {
    if (isTogglingSnoozeAll) return;

    const toggle = document.getElementById('snooze-all-toggle');
    const isSnoozed = toggle.classList.contains('snoozed');

    if (isSnoozed) {
        if (!confirm('Remove snooze from all cameras?')) {
            return;
        }

        isTogglingSnoozeAll = true;
        toggle.classList.add('loading');

        try {
            const response = await fetch('/api/snooze/all/unset', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'}
            });

            const result = await response.json();

            if (result.success) {
                console.log('Unsnoozed all cameras');
                location.reload();
            } else {
                alert('Failed to unsnooze all cameras: ' + (result.error || 'Unknown error'));
            }
        } catch (error) {
            console.error('Error unsnoozing all cameras:', error);
            alert('Error communicating with server');
        } finally {
            toggle.classList.remove('loading');
            isTogglingSnoozeAll = false;
        }
    } else {
        openSnoozeAllModal();
    }
}

async function loadSnoozeAllStatus() {
    try {
        const response = await fetch('/api/snooze/all/status');
        const data = await response.json();

        if (data.success) {
            const toggle = document.getElementById('snooze-all-toggle');

            if (data.all_snoozed) {
                toggle.classList.add('snoozed');
            } else {
                toggle.classList.remove('snoozed');
            }
        }
    } catch (error) {
        console.error('Error loading snooze all status:', error);
    }
}

// ============================================================================
// SNOOZE OPTION SELECTION
// ============================================================================

document.addEventListener('DOMContentLoaded', function() {
    // Single camera snooze options
    document.querySelectorAll('#snooze-options .snooze-option').forEach(option => {
        option.addEventListener('click', function() {
            document.querySelectorAll('#snooze-options .snooze-option').forEach(opt => {
                opt.classList.remove('selected');
            });
            this.classList.add('selected');
            selectedSnoozeDuration = parseInt(this.dataset.minutes);
            document.getElementById('snooze-custom-input').value = '';
        });
    });

    // Snooze all options
    document.querySelectorAll('#snooze-all-options .snooze-option').forEach(option => {
        option.addEventListener('click', function() {
            document.querySelectorAll('#snooze-all-options .snooze-option').forEach(opt => {
                opt.classList.remove('selected');
            });
            this.classList.add('selected');
            selectedSnoozeAllDuration = parseInt(this.dataset.minutes);
            document.getElementById('snooze-all-custom-input').value = '';
        });
    });

    // Custom input handling
    document.getElementById('snooze-custom-input').addEventListener('input', function() {
        document.querySelectorAll('#snooze-options .snooze-option').forEach(opt => {
            opt.classList.remove('selected');
        });
        selectedSnoozeDuration = null;
    });

    document.getElementById('snooze-all-custom-input').addEventListener('input', function() {
        document.querySelectorAll('#snooze-all-options .snooze-option').forEach(opt => {
            opt.classList.remove('selected');
        });
        selectedSnoozeAllDuration = null;
    });
});

// ============================================================================
// AUTO-REFRESH SNOOZE STATUS
// ============================================================================

async function refreshSnoozeBadges() {
    const cards = document.querySelectorAll('.camera-card');

    for (const card of cards) {
        const cam = card.dataset.camera;
        const badge = document.getElementById(`snooze-badge-${cam}`);
        const btn = document.getElementById(`snooze-btn-${cam}`);

        try {
            const res = await fetch(`/api/snooze/status/${cam}`);
            const status = await res.json();

            if (status.is_snoozed) {
                if (badge) {
                    badge.dataset.expiry = status.snooze_until;
                } else {
                    const newBadge = document.createElement('div');
                    newBadge.className = 'snooze-badge';
                    newBadge.id = `snooze-badge-${cam}`;
                    newBadge.dataset.expiry = status.snooze_until;
                    newBadge.innerHTML = `
                        &#x1F515; Until ${status.snooze_until_full}<br>
                        <span id="snooze-countdown-${cam}" style="font-size: 0.9em;">${status.minutes_remaining}m left</span>
                    `;
                    card.querySelector('.camera-image-container').prepend(newBadge);
                }

                if (btn) btn.classList.add("active");
                card.classList.add("snoozed");
            } else {
                if (badge) badge.remove();
                if (btn) btn.classList.remove("active");
                card.classList.remove("snoozed");
            }

        } catch (e) {
            console.error("Error refreshing snooze status:", e);
        }
    }

    await loadSnoozeAllStatus();
}

// ============================================================================
// SNOOZE COUNTDOWN UPDATES
// ============================================================================

function updateSnoozeCountdowns() {
    document.querySelectorAll('.snooze-badge[data-expiry]').forEach(badge => {
        const cameraName = badge.id.replace('snooze-badge-', '');
        const countdownSpan = document.getElementById(`snooze-countdown-${cameraName}`);
        const expiryISO = badge.dataset.expiry;

        if (!countdownSpan || !expiryISO) return;

        const expiry = new Date(expiryISO);
        const now = new Date();
        const diffMs = expiry - now;

        if (diffMs <= 0) {
            location.reload();
            return;
        }

        const totalSeconds = Math.floor(diffMs / 1000);
        const hours = Math.floor(totalSeconds / 3600);
        const minutes = Math.floor((totalSeconds % 3600) / 60);
        const seconds = totalSeconds % 60;

        if (hours > 0) {
            countdownSpan.textContent = `${hours}h ${minutes}m ${seconds}s left`;
        } else if (minutes > 0) {
            countdownSpan.textContent = `${minutes}m ${seconds}s left`;
        } else {
            countdownSpan.textContent = `${seconds}s left`;
        }
    });
}

// ============================================================================
// CLEANUP & POLLING
// ============================================================================

async function cleanupExpiredSnoozes() {
    try {
        await fetch('/api/snooze/cleanup', { method: 'POST' });
        console.log('Expired snoozes cleaned up');
    } catch (error) {
        console.error('Error cleaning up snoozes:', error);
    }
}

// Initialize
document.addEventListener('DOMContentLoaded', function() {
    cleanupExpiredSnoozes();
    loadSnoozeAllStatus();
    setInterval(loadSnoozeAllStatus, 10000);
    setInterval(refreshSnoozeBadges, 20000);
    setInterval(updateSnoozeCountdowns, 1000);
    updateSnoozeCountdowns();
});