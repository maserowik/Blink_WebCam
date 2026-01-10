// nws-alerts.js - Enhanced NWS Alert Widget
// Displays National Weather Service alerts with severity colors and auto-scroll
// COMPLETE FILE - Replace entire static/js/nws-alerts.js with this

// ============================================================================
// ENHANCED NWS ALERT WIDGET CLASS
// ============================================================================

class EnhancedNWSAlertWidget {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
        if (!this.container) {
            console.error('NWS Alert container not found:', containerId);
            return;
        }

        this.alerts = [];
        this.currentIndex = 0;
        this.scrollInterval = null;
        this.isScrolling = false;
        this.nextCheckTimeout = null;
        
        // Severity colors
        this.severityColors = {
            'Extreme': '#8B0000',
            'Severe': '#DC143C',
            'Moderate': '#FF8C00',
            'Minor': '#FFD700',
            'Unknown': '#4299e1'
        };
    }

    // ========================================================================
    // CHECK FOR ALERTS
    // ========================================================================

    async checkAlerts() {
        try {
            const response = await fetch('/api/nws/alerts');
            const data = await response.json();

            if (!data.success) {
                console.error('NWS API error:', data.error);
                this.scheduleNextCheck(new Date(Date.now() + 300000)); // 5 min fallback
                return;
            }

            // Update alerts
            const hasAlerts = data.alerts && data.alerts.length > 0;

            if (hasAlerts) {
                this.alerts = data.alerts;
                this.show();
            } else {
                this.alerts = [];
                this.hide();
            }

            // Schedule next check based on server response
            if (data.next_check) {
                const nextCheck = new Date(data.next_check);
                this.scheduleNextCheck(nextCheck);
            }

        } catch (error) {
            console.error('Error checking NWS alerts:', error);
            // Retry in 5 minutes on error
            this.scheduleNextCheck(new Date(Date.now() + 300000));
        }
    }

    // ========================================================================
    // SCHEDULE NEXT CHECK
    // ========================================================================

    scheduleNextCheck(nextCheckTime) {
        // Clear existing timeout
        if (this.nextCheckTimeout) {
            clearTimeout(this.nextCheckTimeout);
        }

        const now = new Date();
        const msUntilCheck = nextCheckTime - now;

        // Ensure we don't schedule negative time
        const delay = Math.max(0, msUntilCheck);

        this.nextCheckTimeout = setTimeout(() => {
            this.checkAlerts();
        }, delay);

        console.log(`Next NWS check scheduled for: ${nextCheckTime.toLocaleTimeString()}`);
    }

    // ========================================================================
    // SHOW WIDGET
    // ========================================================================

    show() {
        if (this.alerts.length === 0) {
            this.hide();
            return;
        }

        // Reset to first alert
        this.currentIndex = 0;

        // Display first alert
        this.displayCurrentAlert();

        // Show widget with fade-in animation
        this.container.style.display = 'block';
        this.container.classList.remove('fade-out');
        this.container.classList.add('fade-in');

        // Start auto-scroll if multiple alerts
        if (this.alerts.length > 1) {
            this.startAutoScroll();
        } else {
            this.stopAutoScroll();
        }
    }

    // ========================================================================
    // HIDE WIDGET
    // ========================================================================

    hide() {
        // Stop scrolling
        this.stopAutoScroll();

        // Fade out animation
        this.container.classList.remove('fade-in');
        this.container.classList.add('fade-out');

        // After animation, hide completely
        setTimeout(() => {
            this.container.style.display = 'none';
            this.container.classList.remove('fade-out');
        }, 300);
    }

    // ========================================================================
    // DISPLAY CURRENT ALERT
    // ========================================================================

    displayCurrentAlert() {
        if (this.alerts.length === 0) return;

        const alert = this.alerts[this.currentIndex];
        
        // Format alert text - truncate if too long for widget
        const alertText = typeof alert === 'string' ? alert : alert.description;
        const maxLength = 180;  // Shorter to fit widget
        const displayText = alertText.length > maxLength ? 
            alertText.substring(0, maxLength) + '...' : alertText;
        
        // Build HTML - no background color here (applied to widget itself)
        let html = `
            <div class="nws-alert-content">
                <div class="nws-alert-text">
        `;
        
        // Add severity badge only if severity info exists
        if (alert.event || alert.severity) {
            html += `
                    <div class="nws-alert-severity">
                        &#x26A0;&#xFE0F; ${alert.event || 'Weather Alert'}
                    </div>
            `;
        }
        
        html += `
                    <div>
                        <span class="nws-alert-prefix">NWS Alert:</span>
                        <span class="nws-alert-description"> ${this.escapeHtml(displayText)}</span>
                    </div>
                </div>
            </div>
        `;

        this.container.innerHTML = html;
    }

    // ========================================================================
    // AUTO-SCROLL (for multiple alerts)
    // ========================================================================

    startAutoScroll() {
        // Clear any existing interval
        this.stopAutoScroll();

        // Scroll every 8 seconds (longer for readability)
        this.scrollInterval = setInterval(() => {
            this.showNextAlert();
        }, 8000);

        this.isScrolling = true;
        console.log('NWS alert auto-scroll started');
    }

    stopAutoScroll() {
        if (this.scrollInterval) {
            clearInterval(this.scrollInterval);
            this.scrollInterval = null;
        }
        this.isScrolling = false;
    }

    showNextAlert() {
        const content = this.container.querySelector('.nws-alert-content');
        if (!content) return;

        // Fade out current alert
        content.classList.remove('fade-in');
        content.classList.add('fade-out');

        // After fade out, switch to next alert
        setTimeout(() => {
            // Move to next alert (loop back to 0 if at end)
            this.currentIndex = (this.currentIndex + 1) % this.alerts.length;

            // Update content
            this.displayCurrentAlert();

            // Fade in new alert
            const newContent = this.container.querySelector('.nws-alert-content');
            if (newContent) {
                newContent.classList.remove('fade-out');
                newContent.classList.add('fade-in');
            }
        }, 300);
    }

    // ========================================================================
    // UTILITY FUNCTIONS
    // ========================================================================

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}


// ============================================================================
// INITIALIZE ON PAGE LOAD
// ============================================================================

let nwsWidget = null;

document.addEventListener('DOMContentLoaded', function() {
    console.log('Initializing Enhanced NWS Alert Widget...');

    // Create widget instance
    nwsWidget = new EnhancedNWSAlertWidget('nws-alert-widget');

    // Initial check
    if (nwsWidget) {
        nwsWidget.checkAlerts();
    }
});


// ============================================================================
// EXPOSE FOR MANUAL TESTING
// ============================================================================

window.refreshNWSAlerts = function() {
    if (nwsWidget) {
        nwsWidget.checkAlerts();
    } else {
        console.error('NWS widget not initialized');
    }
};