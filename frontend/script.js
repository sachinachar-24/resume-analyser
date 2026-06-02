// Shared utility functions for both HR and User portals

// Close modal
function closeModal(modalId) {
    document.getElementById(modalId).style.display = 'none';
}

// Close modal when clicking outside
window.onclick = function(event) {
    if (event.target.classList.contains('modal')) {
        event.target.style.display = 'none';
    }
}

// Display error toast
function displayError(message) {
    showToast(message, 'error');
}

// Display success toast
function showSuccess(message) {
    showToast(message, 'success');
}

// Generic toast notification
function showToast(message, type = 'info') {
    // Remove existing toasts
    const existingToast = document.querySelector('.toast');
    if (existingToast) {
        existingToast.remove();
    }

    // Create new toast
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    document.body.appendChild(toast);

    // Auto remove after 4 seconds
    setTimeout(() => {
        toast.style.animation = 'slideOutRight 0.3s ease';
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}

// Format score as percentage
function formatScore(score) {
    return `${(score * 100).toFixed(1)}% Match`;
}

// Format date
function formatDate(dateString) {
    if (!dateString) return 'N/A';
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', { 
        year: 'numeric', 
        month: 'short', 
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    });
}

// Escape HTML to prevent XSS
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function getAuthHeaders() {
    const token = localStorage.getItem('access_token');
    return token ? { 'Authorization': `Bearer ${token}` } : {};
}

async function authFetch(url, options = {}) {
    options.headers = {
        ...(options.headers || {}),
        ...getAuthHeaders(),
    };

    const response = await fetch(url, options);
    if (response.status === 401) {
        const nextPage = window.location.pathname.split('/').pop();
        window.location.href = `auth.html?next=${encodeURIComponent(nextPage)}`;
        return response;
    }
    return response;
}

function logout() {
    localStorage.removeItem('access_token');
    window.location.href = 'auth.html';
}

// Open PDF in modal viewer
async function openPDF(resumeId) {
    const token = localStorage.getItem('access_token');
    if (!token) {
        displayError('You must be logged in to view PDFs');
        window.location.href = 'auth.html';
        return;
    }

    const url = `http://localhost:8080/api/resumes/${resumeId}/pdf`;
    let response;
    try {
        response = await fetch(url, {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });
    } catch (err) {
        displayError('Failed to fetch resume PDF');
        console.error(err);
        return;
    }

    if (response.status === 401) {
        displayError('Missing authorization header or invalid session');
        window.location.href = 'auth.html';
        return;
    }

    if (!response.ok) {
        const message = await response.text().catch(() => response.statusText);
        displayError(`Could not load PDF: ${message}`);
        return;
    }

    const blob = await response.blob();
    const blobUrl = URL.createObjectURL(blob);

    // Create modal if it doesn't exist
    let modal = document.getElementById('pdfViewerModal');
    if (!modal) {
        modal = document.createElement('div');
        modal.id = 'pdfViewerModal';
        modal.className = 'modal';
        modal.innerHTML = `
            <div class="modal-content modal-pdf-viewer">
                <div class="pdf-viewer-header">
                    <h2>Resume PDF Viewer</h2>
                    <div>
                        <button id="openPdfNewTabBtn" class="btn-secondary-small">
                            🔗 Open in New Tab
                        </button>
                        <span class="close" onclick="closeModal('pdfViewerModal')">&times;</span>
                    </div>
                </div>
                <div class="pdf-viewer-container">
                    <iframe id="pdfIframe" type="application/pdf"></iframe>
                </div>
            </div>
        `;
        document.body.appendChild(modal);
    }

    const iframe = modal.querySelector('#pdfIframe');
    iframe.src = blobUrl;

    const openTabBtn = modal.querySelector('#openPdfNewTabBtn');
    openTabBtn.onclick = () => window.open(blobUrl, '_blank');

    modal.style.display = 'block';
}

// File upload progress simulation
function simulateProgress(elementId, duration = 2000) {
    const element = document.getElementById(elementId);
    if (!element) return;

    let progress = 0;
    const interval = 50;
    const increment = (interval / duration) * 100;

    const timer = setInterval(() => {
        progress += increment;
        if (progress >= 100) {
            progress = 100;
            clearInterval(timer);
        }
        element.style.width = `${progress}%`;
    }, interval);

    return timer;
}

// Confirmation dialog helper
function confirmAction(message) {
    return confirm(message);
}

// Debounce function for search/filter inputs
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// Validate file type
function validatePDF(file) {
    if (!file) return false;
    return file.type === 'application/pdf';
}

// Validate file size (in MB)
function validateFileSize(file, maxSizeMB = 10) {
    if (!file) return false;
    const maxSize = maxSizeMB * 1024 * 1024;
    return file.size <= maxSize;
}

// Format file size
function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
}

// Copy text to clipboard
async function copyToClipboard(text) {
    try {
        await navigator.clipboard.writeText(text);
        showSuccess('Copied to clipboard!');
    } catch (err) {
        displayError('Failed to copy to clipboard');
        console.error(err);
    }
}

// Download text as file
function downloadTextFile(filename, text) {
    const element = document.createElement('a');
    element.setAttribute('href', 'data:text/plain;charset=utf-8,' + encodeURIComponent(text));
    element.setAttribute('download', filename);
    element.style.display = 'none';
    document.body.appendChild(element);
    element.click();
    document.body.removeChild(element);
}

// Loading spinner overlay
function showLoadingOverlay(message = 'Loading...') {
    const overlay = document.createElement('div');
    overlay.id = 'loadingOverlay';
    overlay.style.cssText = `
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: rgba(0, 0, 0, 0.7);
        display: flex;
        flex-direction: column;
        justify-content: center;
        align-items: center;
        z-index: 9999;
    `;
    
    overlay.innerHTML = `
        <div style="color: white; font-size: 1.5rem; margin-bottom: 20px;">${message}</div>
        <div style="border: 4px solid #f3f3f3; border-top: 4px solid #007bff; border-radius: 50%; width: 50px; height: 50px; animation: spin 1s linear infinite;"></div>
    `;
    
    // Add spin animation
    const style = document.createElement('style');
    style.textContent = '@keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }';
    document.head.appendChild(style);
    
    document.body.appendChild(overlay);
}

function hideLoadingOverlay() {
    const overlay = document.getElementById('loadingOverlay');
    if (overlay) {
        overlay.remove();
    }
}

// Keyboard shortcuts
document.addEventListener('keydown', (e) => {
    // ESC key closes modals
    if (e.key === 'Escape') {
        const modals = document.querySelectorAll('.modal');
        modals.forEach(modal => {
            if (modal.style.display === 'block') {
                modal.style.display = 'none';
            }
        });
    }
});

// Auto-resize textarea
function autoResizeTextarea(textarea) {
    textarea.style.height = 'auto';
    textarea.style.height = textarea.scrollHeight + 'px';
}

// Add event listeners for all textareas
document.addEventListener('DOMContentLoaded', () => {
    const textareas = document.querySelectorAll('textarea');
    textareas.forEach(textarea => {
        textarea.addEventListener('input', () => autoResizeTextarea(textarea));
    });
});

// Smooth scroll to element
function scrollToElement(elementId) {
    const element = document.getElementById(elementId);
    if (element) {
        element.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
}

// Check if API is reachable
async function checkAPIHealth() {
    try {
        const response = await fetch('http://localhost:8080/', {
            method: 'GET',
            timeout: 5000
        });
        return response.ok;
    } catch (error) {
        console.error('API health check failed:', error);
        return false;
    }
}

// Initialize API health check on page load
window.addEventListener('DOMContentLoaded', async () => {
    const isHealthy = await checkAPIHealth();
    if (!isHealthy) {
        displayError('Warning: Backend API may not be running. Please start the server.');
    }
});

console.log('Resume Analyzer - Shared utilities loaded');
