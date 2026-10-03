// Frontend analytics SDK: page view tracking and custom event tracking
const Analytics = {
    track(eventType, eventData = null) {
        // Fire and forget - don't block UI
        Api.post('/api/analytics/track', {
            event_type: eventType,
            event_data: eventData,
            page_url: window.location.pathname + window.location.search,
        }).catch(() => {});
    },

    // Track page view automatically
    trackPageView() {
        this.track('page_view', {
            page: window.location.pathname,
            search: window.location.search,
        });
    },

    // Track button click
    trackClick(element, action) {
        this.track('click', {
            element: element,
            action: action,
        });
    },
};

// Auto track page views on load (for non-login pages)
if (Auth.isLoggedIn()) {
    Analytics.trackPageView();
}
