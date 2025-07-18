/**
 * LinkedIn Applied Jobs Collector - Background Script
 * 
 * Handles background tasks and communication between popup and content script.
 */

// Initialize extension when installed
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
      message.action === 'collectionError' ||
      message.action === 'updateStatus') {
    
    // Try to send to popup
    chrome.runtime.sendMessage(message).catch(() => {
      // Popup is not open, that's okay
    });
  }
  
  // Handle specific actions
  if (message.action === 'openAppliedJobsPage') {
    chrome.tabs.create({
      url: 'https://www.linkedin.com/my-items/saved-jobs/?cardType=APPLIED'
    });
  }
});

// Add context menu for quick access
chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: 'openAppliedJobs',
    title: 'Open LinkedIn Applied Jobs',
    contexts: ['action']
  });
  
  chrome.contextMenus.create({
    id: 'startCollection',
    title: 'Start Collection',
    contexts: ['action']
  });
});

// Handle context menu clicks
chrome.contextMenus.onClicked.addListener((info, tab) => {
  if (info.menuItemId === 'openAppliedJobs') {
    chrome.tabs.create({
      url: 'https://www.linkedin.com/my-items/saved-jobs/?cardType=APPLIED'
    });
  } else if (info.menuItemId === 'startCollection') {
    // Check if we're on the right page first
    chrome.tabs.query({active: true, currentWindow: true}, (tabs) => {
      if (tabs.length > 0) {
        chrome.tabs.sendMessage(tabs[0].id, {action: 'checkPage'}, (response) => {
          if (response && response.isCorrectPage) {
            chrome.tabs.sendMessage(tabs[0].id, {action: 'startCollection'});
          } else {
            // Not on the right page, open it first
            chrome.tabs.create({
              url: 'https://www.linkedin.com/my-items/saved-jobs/?cardType=APPLIED'
            });
          }
        });
      }
    });
  }
});