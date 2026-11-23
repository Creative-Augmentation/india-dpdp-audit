// Synthetic display theme.
analytics.track('rack_preview');
document.addEventListener('visitorConsentCollected', () => {
    if (window.Shopify.customerPrivacy.analyticsProcessingAllowed()) {
        analytics.track('rack_choice');
    }
});
