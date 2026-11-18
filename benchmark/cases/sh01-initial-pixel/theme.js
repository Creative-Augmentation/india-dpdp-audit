// Illustrative, non-executable pseudocode for the staged synthetic theme.
recordOptionalPageView(); // Queues analytics immediately on initialization.
onVisitorConsentCollected((privacy) => {
  if (!privacy.analyticsAllowed) stopOptionalPageViews();
});
