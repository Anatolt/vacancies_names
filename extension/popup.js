// Popup script for LinkedIn Applied Jobs Collector
class PopupManager {
  constructor() {
    this.isCollecting = false;
    this.init();
  }

  init() {
    this.bindEvents();
    this.updateStatus();
  }

  bindEvents() {
    document.getElementById('startBtn').addEventListener('click', () => this.startCollection());
    document.getElementById('stopBtn').addEventListener('click', () => this.stopCollection());
    document.getElementById('downloadBtn').addEventListener('click', () => this.downloadLinks());
    document.getElementById('openPageBtn').addEventListener('click', () => this.openAppliedJobsPage());
  }

  async updateStatus() {
    const status = document.getElementById('status');
    const startBtn = document.getElementById('startBtn');
    const progress = document.getElementById('progress');
    
    try {
      // Check if we're on the right page
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
      
      if (tab.url && tab.url.includes('linkedin.com/my-items/saved-jobs')) {
        status.textContent = '✅ На странице Applied Jobs. Готов к сбору.';
        status.className = 'status success';
        startBtn.disabled = false;
      } else {
        status.textContent = '⚠️ Откройте страницу "Мои вакансии" в LinkedIn';
        status.className = 'status warning';
        startBtn.disabled = true;
      }

      // Check if we have collected data
      const result = await chrome.storage.local.get(['collectedLinks', 'isCollecting']);
      if (result.collectedLinks && result.collectedLinks.length > 0) {
        document.getElementById('downloadBtn').classList.remove('hidden');
      }
      
      if (result.isCollecting) {
        this.isCollecting = true;
        this.showProgress();
      }
      
    } catch (error) {
      console.error('Error updating status:', error);
      status.textContent = '❌ Ошибка при проверке статуса';
      status.className = 'status error';
    }
  }

  async startCollection() {
    if (this.isCollecting) return;

    try {
      this.isCollecting = true;
      this.showProgress();
      
      // Send message to content script to start collection
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
      await chrome.tabs.sendMessage(tab.id, { action: 'startCollection' });
      
      // Store collection state
      await chrome.storage.local.set({ isCollecting: true });
      
      this.updateStatus();
      
    } catch (error) {
      console.error('Error starting collection:', error);
      this.showError('Ошибка при запуске сбора: ' + error.message);
    }
  }

  async stopCollection() {
    try {
      this.isCollecting = false;
      this.hideProgress();
      
      // Send message to content script to stop collection
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
      await chrome.tabs.sendMessage(tab.id, { action: 'stopCollection' });
      
      // Clear collection state
      await chrome.storage.local.set({ isCollecting: false });
      
      this.updateStatus();
      
    } catch (error) {
      console.error('Error stopping collection:', error);
    }
  }

  async downloadLinks() {
    try {
      const result = await chrome.storage.local.get(['collectedLinks']);
      if (!result.collectedLinks || result.collectedLinks.length === 0) {
        this.showError('Нет собранных ссылок для скачивания');
        return;
      }

      // Create file content
      const content = result.collectedLinks.join('\n');
      const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
      const filename = `applied_jobs_links_${timestamp}.txt`;

      // Download file
      const blob = new Blob([content], { type: 'text/plain' });
      const url = URL.createObjectURL(blob);
      
      await chrome.downloads.download({
        url: url,
        filename: filename,
        saveAs: true
      });

      this.showSuccess(`Скачано ${result.collectedLinks.length} ссылок в файл ${filename}`);
      
    } catch (error) {
      console.error('Error downloading links:', error);
      this.showError('Ошибка при скачивании: ' + error.message);
    }
  }

  async openAppliedJobsPage() {
    try {
      await chrome.tabs.create({
        url: 'https://www.linkedin.com/my-items/saved-jobs/?cardType=APPLIED'
      });
    } catch (error) {
      console.error('Error opening page:', error);
      this.showError('Ошибка при открытии страницы');
    }
  }

  showProgress() {
    document.getElementById('progress').classList.remove('hidden');
    document.getElementById('startBtn').classList.add('hidden');
    document.getElementById('stopBtn').classList.remove('hidden');
  }

  hideProgress() {
    document.getElementById('progress').classList.add('hidden');
    document.getElementById('startBtn').classList.remove('hidden');
    document.getElementById('stopBtn').classList.add('hidden');
  }

  showSuccess(message) {
    const status = document.getElementById('status');
    status.textContent = message;
    status.className = 'status success';
  }

  showError(message) {
    const status = document.getElementById('status');
    status.textContent = message;
    status.className = 'status error';
  }

  showInfo(message) {
    const status = document.getElementById('status');
    status.textContent = message;
    status.className = 'status info';
  }

  updateProgress(currentPage, totalPages, collectedLinks) {
    const progressFill = document.getElementById('progress-fill');
    const currentPageSpan = document.getElementById('current-page');
    const collectedLinksSpan = document.getElementById('collected-links');
    
    if (totalPages > 0) {
      const percentage = (currentPage / totalPages) * 100;
      progressFill.style.width = `${percentage}%`;
    }
    
    currentPageSpan.textContent = `Страница: ${currentPage}`;
    collectedLinksSpan.textContent = `Собрано: ${collectedLinks} ссылок`;
  }
}

// Listen for messages from content script
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === 'updateProgress') {
    const popup = window.popupManager;
    if (popup) {
      popup.updateProgress(message.currentPage, message.totalPages, message.collectedLinks);
    }
  } else if (message.action === 'collectionComplete') {
    const popup = window.popupManager;
    if (popup) {
      popup.isCollecting = false;
      popup.hideProgress();
      popup.showSuccess(`Сбор завершен! Собрано ${message.collectedLinks} ссылок`);
      document.getElementById('downloadBtn').classList.remove('hidden');
    }
  } else if (message.action === 'collectionError') {
    const popup = window.popupManager;
    if (popup) {
      popup.isCollecting = false;
      popup.hideProgress();
      popup.showError('Ошибка при сборе: ' + message.error);
    }
  }
});

// Initialize popup when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
  window.popupManager = new PopupManager();
}); 