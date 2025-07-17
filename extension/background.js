// Background script for LinkedIn Applied Jobs Collector
chrome.runtime.onInstalled.addListener(() => {
  console.log('LinkedIn Applied Jobs Collector installed');
  
  // Initialize storage
  chrome.storage.local.set({
    collectedLinks: [],
    isCollecting: false,
    lastUpdated: null
  });
});

// Handle messages from content script and popup
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  console.log('Background received message:', message);
  
  // Forward messages to popup if it's open
  if (message.action === 'updateProgress' || 
      message.action === 'collectionComplete' || 
      message.action === 'collectionError') {
    
    // Try to send to popup
    chrome.runtime.sendMessage(message).catch(() => {
      // Popup is not open, that's okay
    });
  }
});

// Handle extension icon click
chrome.action.onClicked.addListener((tab) => {
  // This will open the popup automatically due to manifest configuration
  console.log('Extension icon clicked');
}); 