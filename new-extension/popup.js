/**
 * LinkedIn Applied Jobs Collector - Popup Script
 * 
 * Handles the popup UI and communication with content script.
 */

class PopupManager {
  constructor() {
    this.isCollecting = false;
    this.init();
  }

  init() {
    this.bindEvents();
    this.updateStatus();
    this.setupMessageListeners();
    this.displayVersion();
  }
  
  async displayVersion() {
    try {
      const manifestData = chrome.runtime.getManifest();
      const versionElement = document.querySelector('.footer[style]');
      if (versionElement && manifestData.version) {
        versionElement.textContent = `Версия: ${manifestData.version}`;
      }
    } catch (error) {
      console.error('Error displaying version:', error);
    }
  }

  bindEvents() {
    document.getElementById('startBtn').addEventListener('click', () => this.startCollection());
    document.getElementById('stopBtn').addEventListener('click', () => this.stopCollection());
    document.getElementById('downloadBtn').addEventListener('click', () => this.downloadLinks());
    document.getElementById('openPageBtn').addEventListener('click', () => this.openAppliedJobsPage());
  }
  
  setupMessageListeners() {
    chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
      console.log('Popup received message:', message);
      
      if (message.action === 'updateProgress') {
        this.updateProgressUI(message.currentPage, message.totalPages, message.collectedLinks);
      } else if (message.action === 'collectionComplete') {
        this.handleCollectionComplete(message.collectedLinks);
      } else if (message.action === 'collectionError') {
        this.handleCollectionError(message.error);
      } else if (message.action === 'updateStatus') {
        this.showInfo(message.status);
      }
    });
  }

  async updateStatus() {
    const status = document.getElementById('status');
    const startBtn = document.getElementById('startBtn');
    const progress = document.getElementById('progress');
    
    try {
      // Check if we're on the right page
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
      
      if (!tab || !tab.url) {
        status.textContent = '⚠️ Не удалось определить текущую страницу';
        status.className = 'status warning';
        startBtn.disabled = true;
        return;
      }
      
      if (tab.url.includes('linkedin.com/my-items/saved-jobs') && tab.url.includes('cardType=APPLIED')) {
        status.textContent = '✅ На странице Applied Jobs. Готов к сбору.';
        status.className = 'status success';
        startBtn.disabled = false;
      } else if (tab.url.includes('linkedin.com')) {
        status.textContent = '⚠️ Вы на LinkedIn, но не на странице Applied Jobs';
        status.className = 'status warning';
        startBtn.disabled = true;
      } else {
        status.textContent = '⚠️ Откройте страницу "Мои вакансии" в LinkedIn';
        status.className = 'status warning';
        startBtn.disabled = true;
      }

      // Check if we have collected data
      const result = await chrome.storage.local.get(['collectedLinks', 'isCollecting']);
      if (result.collectedLinks && result.collectedLinks.length > 0) {
        document.getElementById('downloadBtn').classList.remove('hidden');
        this.showInfo(`В хранилище ${result.collectedLinks.length} ссылок`);
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
      if (!tab || !tab.id) {
        throw new Error('Не удалось найти активную вкладку');
      }
      
      await chrome.tabs.sendMessage(tab.id, { action: 'startCollection' });
      
      // Store collection state
      await chrome.storage.local.set({ isCollecting: true });
      
    } catch (error) {
      console.error('Error starting collection:', error);
      this.showError('Ошибка при запуске сбора: ' + error.message);
      this.isCollecting = false;
      this.hideProgress();
    }
  }

  async stopCollection() {
    try {
      // Send message to content script to stop collection
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
      if (tab && tab.id) {
        await chrome.tabs.sendMessage(tab.id, { action: 'stopCollection' });
      }
      
      // Clear collection state
      await chrome.storage.local.set({ isCollecting: false });
      
      this.isCollecting = false;
      this.hideProgress();
      this.showInfo('Сбор остановлен');
      
    } catch (error) {
      console.error('Error stopping collection:', error);
      this.showError('Ошибка при остановке сбора: ' + error.message);
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
      // Открываем страницу напрямую, без сообщений
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

  updateProgressUI(currentPage, totalPages, collectedLinks) {
    const progressFill = document.getElementById('progress-fill');
    const currentPageSpan = document.getElementById('current-page');
    const collectedLinksSpan = document.getElementById('collected-links');
    
    if (totalPages > 0) {
      const percentage = Math.min((currentPage / totalPages) * 100, 100);
      progressFill.style.width = `${percentage}%`;
    }
    
    currentPageSpan.textContent = `Страница: ${currentPage}`;
    collectedLinksSpan.textContent = `Собрано: ${collectedLinks} ссылок`;
  }
  
  handleCollectionComplete(collectedLinks) {
    this.isCollecting = false;
    this.hideProgress();
    this.showSuccess(`Сбор завершен! Собрано ${collectedLinks} ссылок`);
    document.getElementById('downloadBtn').classList.remove('hidden');
  }
  
  handleCollectionError(error) {
    this.isCollecting = false;
    this.hideProgress();
    this.showError('Ошибка при сборе: ' + error);
  }
}

// Initialize popup when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
  window.popupManager = new PopupManager();
});