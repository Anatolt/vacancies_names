/**
 * LinkedIn Applied Jobs Collector - Content Script
 * 
 * This script extracts job links from LinkedIn Applied Jobs page
 * with pagination support.
 */

class AppliedJobsCollector {
  constructor() {
    this.isCollecting = false;
    this.collectedLinks = new Set();
    this.currentPage = 0;
    this.maxPages = 50; // Safety limit
    this.shouldStop = false;
    this.totalPages = 0;
    
    this.init();
  }

  init() {
    console.log('LinkedIn Applied Jobs Collector initialized');
    this.bindMessages();
    this.loadExistingData();
  }

  bindMessages() {
    chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
      console.log('Content script received message:', message);
      
      if (message.action === 'startCollection') {
        this.startCollection();
        sendResponse({ status: 'started' });
      } else if (message.action === 'stopCollection') {
        this.stopCollection();
        sendResponse({ status: 'stopped' });
      } else if (message.action === 'checkPage') {
        const isCorrectPage = this.isAppliedJobsPage();
        sendResponse({ 
          isCorrectPage: isCorrectPage,
          url: window.location.href
        });
      }
      
      return true; // Keep the message channel open for async responses
    });
  }

  async loadExistingData() {
    try {
      const result = await chrome.storage.local.get(['collectedLinks']);
      if (result.collectedLinks) {
        this.collectedLinks = new Set(result.collectedLinks);
        console.log(`Loaded ${this.collectedLinks.size} existing links`);
      }
    } catch (error) {
      console.error('Error loading existing data:', error);
    }
  }

  async startCollection() {
    if (this.isCollecting) {
      console.log('Collection already in progress');
      this.notifyStatus('Collection already in progress');
      return;
    }

    console.log('Starting Applied Jobs collection...');
    this.notifyStatus('Starting collection...');
    
    this.isCollecting = true;
    this.shouldStop = false;
    this.currentPage = 0;
    
    await chrome.storage.local.set({ isCollecting: true });

    try {
      // Check if we're on the right page
      if (!this.isAppliedJobsPage()) {
        throw new Error('Not on Applied Jobs page. Please navigate to LinkedIn Applied Jobs.');
      }

      // Start collection process
      await this.collectAllJobLinks();
      
    } catch (error) {
      console.error('Collection error:', error);
      this.notifyError(error.message);
    } finally {
      this.isCollecting = false;
      await chrome.storage.local.set({ isCollecting: false });
    }
  }

  stopCollection() {
    console.log('Stopping collection...');
    this.notifyStatus('Stopping collection...');
    this.shouldStop = true;
    this.isCollecting = false;
  }

  isAppliedJobsPage() {
    const url = window.location.href;
    return url.includes('linkedin.com/my-items/saved-jobs') && url.includes('cardType=APPLIED');
  }

  async collectAllJobLinks() {
    console.log('Starting to collect all job links...');
    this.notifyStatus('Collecting job links...');
    
    // Try to get total count estimate
    const totalEstimate = this.getTotalJobsCount();
    if (totalEstimate > 0) {
      console.log(`Estimated total applied jobs: ${totalEstimate}`);
      this.notifyStatus(`Found approximately ${totalEstimate} applied jobs`);
    }
    
    while (this.currentPage < this.maxPages && !this.shouldStop) {
      this.currentPage++;
      console.log(`Processing page ${this.currentPage}...`);
      this.notifyStatus(`Processing page ${this.currentPage}...`);
      
      // Wait for page to load
      await this.wait(2000);
      
      // Extract job links from current page
      const pageLinks = this.extractJobLinksFromPage();
      
      if (pageLinks.length === 0) {
        console.log('No job links found on current page');
        this.notifyStatus('No job links found on current page');
        break;
      }
      
      // Add new unique links
      let newLinksCount = 0;
      for (const link of pageLinks) {
        if (!this.collectedLinks.has(link)) {
          this.collectedLinks.add(link);
          newLinksCount++;
        }
      }
      
      console.log(`Found ${newLinksCount} new job links on page ${this.currentPage}`);
      console.log(`Total unique jobs collected: ${this.collectedLinks.size}`);
      
      // Save progress
      await this.saveProgress();
      
      // Update progress in popup
      this.updateProgress();
      
      // Check if there are more jobs to load
      if (!this.checkForMoreJobs()) {
        console.log('No more jobs to load - pagination complete');
        this.notifyStatus('Pagination complete');
        break;
      }
      
      // Load more jobs
      if (!await this.loadMoreJobs()) {
        console.log('Failed to load more jobs - stopping pagination');
        this.notifyStatus('Failed to load more jobs');
        break;
      }
      
      // Safety check: if we haven't found new links
      if (newLinksCount === 0) {
        console.log('No new links found - might have reached the end');
        this.notifyStatus('No new links found - might have reached the end');
        break;
      }
    }
    
    // Collection complete
    console.log(`Collection completed! Total links: ${this.collectedLinks.size}`);
    this.notifyComplete();
  }

  extractJobLinksFromPage() {
    try {
      // Try multiple selectors to find job links
      const selectors = [
        'a[href*="jobs/view/"][trk*="flagship3_job_home_appliedjobs"]',
        'a[href*="jobs/view/"]',
        'a[trk*="flagship3_job_home_appliedjobs"]'
      ];
      
      let allLinks = [];
      
      for (const selector of selectors) {
        const links = Array.from(document.querySelectorAll(selector));
        const hrefs = links
          .map(link => link.href)
          .filter(href => href && href.includes('jobs/view/'));
        
        console.log(`Selector "${selector}": found ${links.length} elements, ${hrefs.length} job links`);
        
        if (hrefs.length > 0) {
          allLinks = allLinks.concat(hrefs);
          break; // Use the first selector that finds links
        }
      }
      
      // Clean and deduplicate URLs
      const cleanLinks = [];
      const seenJobIds = new Set();
      
      for (const link of allLinks) {
        // Extract job ID from URL
        const match = link.match(/\/jobs\/view\/(\d+)\//);
        if (match) {
          const jobId = match[1];
          if (!seenJobIds.has(jobId)) {
            // Create clean URL without tracking parameters
            const cleanUrl = `https://www.linkedin.com/jobs/view/${jobId}/`;
            cleanLinks.push(cleanUrl);
            seenJobIds.add(jobId);
          }
        }
      }
      
      return cleanLinks;
      
    } catch (error) {
      console.error('Error extracting job links:', error);
      return [];
    }
  }

  getTotalJobsCount() {
    try {
      // Look for total count in various places
      const countSelectors = [
        '.workflow-results-container h1',  // "My Jobs" heading area
        '.search-results-container__text',
        '.jobs-search-results-list__text',
        '[data-test-id*="count"]'
      ];
      
      for (const selector of countSelectors) {
        const element = document.querySelector(selector);
        if (element) {
          const text = element.innerText;
          // Look for numbers in the text
          const numbers = text.match(/\d+/g);
          if (numbers && numbers.length > 0) {
            return parseInt(numbers[0]);
          }
        }
      }
      
      // Fallback: count job cards on page
      const jobCards = document.querySelectorAll('a[href*="jobs/view/"][trk="flagship3_job_home_appliedjobs"]');
      return jobCards.length;
      
    } catch (error) {
      console.error('Error getting total jobs count:', error);
      return 0;
    }
  }

  checkForMoreJobs() {
    try {
      // Scroll to bottom to make sure pagination is visible
      window.scrollTo(0, document.body.scrollHeight);
      
      // Look for "Next" button in pagination
      const nextButtonSelectors = [
        'button[aria-label="Next"]',
        'button[aria-label*="Next"]',
        '.artdeco-pagination__button--next',
        'button[data-test-pagination-page-btn="next"]'
      ];
      
      for (const selector of nextButtonSelectors) {
        const element = document.querySelector(selector);
        if (element && element.offsetParent !== null && !element.disabled) {
          console.log(`Found Next button: ${selector}`);
          return true;
        }
      }
      
      // Look for numbered pagination buttons
      const paginationInfo = this.getPaginationInfo();
      console.log(`Pagination info: Current page ${paginationInfo.currentPage}, Total pages ${paginationInfo.totalPages}`);
      
      // Update total pages
      this.totalPages = paginationInfo.totalPages;
      
      return paginationInfo.hasNext;
      
    } catch (error) {
      console.error('Error checking for more jobs:', error);
      return false;
    }
  }

  getPaginationInfo() {
    // Look for pagination container
    const paginationSelectors = [
      '.artdeco-pagination',
      '[role="navigation"]',
      '.pagination'
    ];
    
    let paginationContainer = null;
    for (const selector of paginationSelectors) {
      paginationContainer = document.querySelector(selector);
      if (paginationContainer) break;
    }
    
    if (!paginationContainer) {
      return { hasNext: false, currentPage: 1, totalPages: 1 };
    }
    
    // Find current page
    const currentPageElement = paginationContainer.querySelector('[aria-current="page"], .active, .selected');
    const currentPage = currentPageElement ? parseInt(currentPageElement.textContent) || 1 : 1;
    
    // Find all page number buttons
    const pageButtons = Array.from(paginationContainer.querySelectorAll('button, a'))
      .filter(btn => /^\d+$/.test(btn.textContent.trim()));
    
    const pageNumbers = pageButtons.map(btn => parseInt(btn.textContent)).filter(num => !isNaN(num));
    const maxPage = Math.max(...pageNumbers, currentPage);
    
    // Check if there's a next page button or a higher page number
    const hasNextButton = !!paginationContainer.querySelector('button[aria-label*="Next"], .artdeco-pagination__button--next');
    const hasHigherPage = pageNumbers.some(num => num > currentPage);
    
    return {
      hasNext: hasNextButton || hasHigherPage,
      currentPage: currentPage,
      totalPages: maxPage,
      availablePages: pageNumbers
    };
  }

  async loadMoreJobs() {
    try {
      // Scroll to bottom to make sure pagination is visible
      window.scrollTo(0, document.body.scrollHeight);
      await this.wait(1000);
      
      // First, try to click "Next" button
      const nextButtonSelectors = [
        'button[aria-label="Next"]',
        'button[aria-label*="Next"]',
        '.artdeco-pagination__button--next',
        'button[data-test-pagination-page-btn="next"]'
      ];
      
      for (const selector of nextButtonSelectors) {
        const element = document.querySelector(selector);
        if (element && element.offsetParent !== null && !element.disabled) {
          console.log(`Clicking Next button: ${selector}`);
          element.click();
          await this.wait(3000); // Wait for page to load
          return true;
        }
      }
      
      // If no Next button, try to find the next page number
      const paginationInfo = this.getPaginationInfo();
      const nextPage = paginationInfo.currentPage + 1;
      
      if (paginationInfo.availablePages.includes(nextPage)) {
        const nextPageButton = Array.from(document.querySelectorAll('button, a'))
          .find(btn => btn.textContent.trim() === nextPage.toString());
        
        if (nextPageButton) {
          console.log(`Clicking page ${nextPage} button`);
          nextPageButton.click();
          await this.wait(3000);
          return true;
        }
      }
      
      return false;
      
    } catch (error) {
      console.error('Error loading more jobs:', error);
      return false;
    }
  }

  async saveProgress() {
    try {
      const linksArray = Array.from(this.collectedLinks);
      await chrome.storage.local.set({ 
        collectedLinks: linksArray,
        lastUpdated: new Date().toISOString()
      });
    } catch (error) {
      console.error('Error saving progress:', error);
    }
  }

  updateProgress() {
    try {
      const paginationInfo = this.getPaginationInfo();
      chrome.runtime.sendMessage({
        action: 'updateProgress',
        currentPage: this.currentPage,
        totalPages: paginationInfo.totalPages || this.totalPages,
        collectedLinks: this.collectedLinks.size
      });
    } catch (error) {
      console.error('Error updating progress:', error);
    }
  }

  notifyComplete() {
    try {
      chrome.runtime.sendMessage({
        action: 'collectionComplete',
        collectedLinks: this.collectedLinks.size
      });
    } catch (error) {
      console.error('Error notifying completion:', error);
    }
  }

  notifyError(error) {
    try {
      chrome.runtime.sendMessage({
        action: 'collectionError',
        error: error
      });
    } catch (err) {
      console.error('Error notifying error:', err);
    }
  }

  notifyStatus(status) {
    try {
      chrome.runtime.sendMessage({
        action: 'updateStatus',
        status: status
      });
    } catch (error) {
      console.error('Error notifying status:', error);
    }
  }

  wait(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
  }
}

// Initialize collector when page loads
const collector = new AppliedJobsCollector();