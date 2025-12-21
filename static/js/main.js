// main.js - Core application functionality

// ============================================================================
// THEME MANAGEMENT
// ============================================================================

// Load saved theme immediately (before page renders)
(function() {
    const savedTheme = localStorage.getItem('theme') || 'light';
    document.body.setAttribute('data-theme', savedTheme);
})();

// Toggle theme
function toggleTheme() {
    const body = document.body;
    const currentTheme = body.getAttribute('data-theme');
    const newTheme = currentTheme === 'light' ? 'dark' : 'light';
    body.setAttribute('data-theme', newTheme);
    document.getElementById('theme-icon').innerHTML = newTheme === 'light' ? '&#x2600;&#xFE0F;' : '&#x1F319;';
    localStorage.setItem('theme', newTheme);
}

// Update theme icon after DOM loads
document.addEventListener('DOMContentLoaded', function() {
    const savedTheme = localStorage.getItem('theme') || 'light';
    const themeIcon = document.getElementById('theme-icon');
    if (themeIcon) {
        themeIcon.innerHTML = savedTheme === 'light' ? '&#x2600;&#xFE0F;' : '&#x1F319;';
    }
});

// ============================================================================
// ARM/DISARM TOGGLE
// ============================================================================

let isTogglingArm = false;

// Load saved arm state immediately
(function() {
    const savedArmState = localStorage.getItem('armState');
    if (savedArmState === 'armed') {
        document.addEventListener('DOMContentLoaded', function() {
            const toggle = document.getElementById('arm-toggle');
            const icon = document.getElementById('arm-icon');
            if (toggle && icon) {
                toggle.classList.add('armed');
                icon.innerHTML = '&#x1F6E1;&#xFE0F;';
            }
        });
    }
})();

async function loadArmStatus() {
    try {
        const response = await fetch('/api/arm/status');
        const data = await response.json();

        if (data.success) {
            const toggle = document.getElementById('arm-toggle');
            const icon = document.getElementById('arm-icon');

            if (data.armed) {
                toggle.classList.add('armed');
                icon.innerHTML = '&#x1F6E1;&#xFE0F;';
                localStorage.setItem('armState', 'armed');
            } else {
                toggle.classList.remove('armed');
                icon.innerHTML = '&#x1F513;';
                localStorage.setItem('armState', 'disarmed');
            }
        }
    } catch (error) {
        console.error('Error loading arm status:', error);
    }
}

async function toggleArm() {
    if (isTogglingArm) return;

    const toggle = document.getElementById('arm-toggle');
    const icon = document.getElementById('arm-icon');
    const isArmed = toggle.classList.contains('armed');

    isTogglingArm = true;
    toggle.classList.add('loading');

    try {
        const response = await fetch('/api/arm/set', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({arm: !isArmed})
        });

        const result = await response.json();

        if (result.success) {
            if (result.armed) {
                toggle.classList.add('armed');
                icon.innerHTML = '&#x1F6E1;&#xFE0F;';
                localStorage.setItem('armState', 'armed');
                console.log('System ARMED');
            } else {
                toggle.classList.remove('armed');
                icon.innerHTML = '&#x1F513;';
                localStorage.setItem('armState', 'disarmed');
                console.log('System DISARMED');
            }
        } else {
            alert('Failed to change arm state: ' + (result.error || 'Unknown error'));
        }
    } catch (error) {
        console.error('Error toggling arm state:', error);
        alert('Error communicating with server');
    } finally {
        toggle.classList.remove('loading');
        isTogglingArm = false;
    }
}

// ============================================================================
// CURRENT TIME DISPLAY
// ============================================================================

function updateTime() {
    const now = new Date();
    document.getElementById('current-time').textContent = now.toLocaleString('en-US', {
        weekday: 'long',
        year: 'numeric',
        month: 'long',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
    });
}

updateTime();
setInterval(updateTime, 1000);

// ============================================================================
// BATTERY & TEMPERATURE ALERTS
// ============================================================================

function parseTemperature(tempStr) {
    if (!tempStr || tempStr === 'N/A') return null;
    const cleaned = tempStr.replace(/[^\d.-]/g, '');
    return parseFloat(cleaned);
}

function parseBattery(batteryStr) {
    if (!batteryStr || batteryStr === 'N/A') return null;
    batteryStr = batteryStr.toLowerCase().trim();
    if (batteryStr === 'low') return 10;
    if (batteryStr === 'ok' || batteryStr === 'okay') return 100;
    const match = batteryStr.match(/(\d+)/);
    return match ? parseInt(match[1]) : null;
}

function checkBatteryLevels() {
    document.querySelectorAll('[data-battery]').forEach(statDiv => {
        const batteryStr = statDiv.getAttribute('data-battery');
        const battery = parseBattery(batteryStr);

        if (battery !== null && battery <= window.BlinkConfig.BATTERY_LOW_THRESHOLD) {
            statDiv.classList.add('critical');
            const valueDiv = statDiv.querySelector('.stat-value');
            if (valueDiv) {
                const currentText = valueDiv.textContent.trim();
                if (!currentText.includes('\u26A0')) {
                    valueDiv.innerHTML = '&#x26A0;&#xFE0F; ' + currentText;
                }
            }
        }
    });
}

function checkTemperatureLevels() {
    document.querySelectorAll('[data-temperature]').forEach(statDiv => {
        const tempStr = statDiv.getAttribute('data-temperature');
        const temp = parseTemperature(tempStr);

        if (temp !== null) {
            const valueDiv = statDiv.querySelector('.stat-value');
            if (temp >= window.BlinkConfig.TEMP_HOT_THRESHOLD) {
                statDiv.classList.add('alert');
                if (valueDiv) {
                    const currentText = valueDiv.textContent.trim();
                    if (!currentText.includes('\uD83D\uDD25')) {
                        valueDiv.innerHTML = '&#x1F525; ' + currentText;
                    }
                }
            } else if (temp <= window.BlinkConfig.TEMP_COLD_THRESHOLD) {
                statDiv.classList.add('alert');
                if (valueDiv) {
                    const currentText = valueDiv.textContent.trim();
                    if (!currentText.includes('\u2744')) {
                        valueDiv.innerHTML = '&#x2744;&#xFE0F; ' + currentText;
                    }
                }
            }
        }
    });
}

// ============================================================================
// PAGE INITIALIZATION
// ============================================================================

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    checkBatteryLevels();
    checkTemperatureLevels();
    loadArmStatus();
});

// Poll arm status every 10 seconds
setInterval(loadArmStatus, 10000);

// NOTE: Camera auto-refresh is handled by camera-refresh.js
// Weather refreshes at :00 and :30 via weather.js
// Radar auto-refreshes via radar.js
// Full page reload is NO LONGER NEEDED