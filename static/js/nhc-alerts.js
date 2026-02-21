// nhc-alerts.js - NHC Hurricane Alert Widget

class NHCAlertWidget {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
        if (!this.container) {
            console.error('NHC Alert container not found:', containerId);
            return;
        }

        this.hurricanes = [];
        this.currentIndex = 0;
        this.scrollInterval = null;
        this.nextCheckTimeout = null;
    }

    async checkAlerts() {
        try {
            const response = await fetch('/api/nhc/alerts');
            const data = await response.json();

            if (!data.success) {
                console.error('NHC API error:', data.error);
                this.scheduleNextCheck(new Date(Date.now() + 300000));
                return;
            }

            const hasHurricanes = data.hurricanes && data.hurricanes.length > 0;

            if (hasHurricanes) {
                this.hurricanes = data.hurricanes;
                this.show();
            } else {
                this.hurricanes = [];
                this.hide();
            }

            if (data.next_check) {
                this.scheduleNextCheck(new Date(data.next_check));
            }

        } catch (error) {
            console.error('Error checking NHC alerts:', error);
            this.scheduleNextCheck(new Date(Date.now() + 300000));
        }
    }

    scheduleNextCheck(nextCheckTime) {
        if (this.nextCheckTimeout) clearTimeout(this.nextCheckTimeout);
        const delay = Math.max(0, nextCheckTime - new Date());
        this.nextCheckTimeout = setTimeout(() => this.checkAlerts(), delay);
        console.log(`Next NHC check scheduled for: ${nextCheckTime.toLocaleTimeString()}`);
    }

    show() {
        if (this.hurricanes.length === 0) { this.hide(); return; }

        this.currentIndex = 0;
        this.displayCurrent();

        this.container.style.display = 'block';
        this.container.classList.remove('fade-out');
        this.container.classList.add('fade-in');

        if (this.hurricanes.length > 1) {
            this.startAutoScroll();
        } else {
            this.stopAutoScroll();
        }
    }

    hide() {
        this.stopAutoScroll();
        this.container.classList.remove('fade-in');
        this.container.classList.add('fade-out');
        setTimeout(() => {
            this.container.style.display = 'none';
            this.container.classList.remove('fade-out');
        }, 300);
    }

    displayCurrent() {
        if (this.hurricanes.length === 0) return;

        const name = this.hurricanes[this.currentIndex];
        const countText = this.hurricanes.length > 1
            ? ` (${this.currentIndex + 1} of ${this.hurricanes.length})`
            : '';

        this.container.innerHTML = `
            <div class="nws-alert-content">
                <div class="nws-alert-text">
                    <div class="nws-alert-severity">&#x1F300; Active Atlantic Hurricane${countText}</div>
                    <div>
                        <span class="nws-alert-prefix">NHC Alert:</span>
                        <span class="nws-alert-description"> Hurricane ${this.escapeHtml(name)} is active in the Atlantic basin</span>
                    </div>
                </div>
            </div>
        `;
    }

    startAutoScroll() {
        this.stopAutoScroll();
        this.scrollInterval = setInterval(() => this.showNext(), 8000);
    }

    stopAutoScroll() {
        if (this.scrollInterval) {
            clearInterval(this.scrollInterval);
            this.scrollInterval = null;
        }
    }

    showNext() {
        const content = this.container.querySelector('.nws-alert-content');
        if (!content) return;

        content.classList.remove('fade-in');
        content.classList.add('fade-out');

        setTimeout(() => {
            this.currentIndex = (this.currentIndex + 1) % this.hurricanes.length;
            this.displayCurrent();
            const newContent = this.container.querySelector('.nws-alert-content');
            if (newContent) {
                newContent.classList.remove('fade-out');
                newContent.classList.add('fade-in');
            }
        }, 300);
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}

let nhcWidget = null;

document.addEventListener('DOMContentLoaded', function() {
    console.log('Initializing NHC Alert Widget...');
    nhcWidget = new NHCAlertWidget('nhc-alert-widget');
    if (nhcWidget) nhcWidget.checkAlerts();
});

window.refreshNHCAlerts = function() {
    if (nhcWidget) nhcWidget.checkAlerts();
    else console.error('NHC widget not initialized');
};
