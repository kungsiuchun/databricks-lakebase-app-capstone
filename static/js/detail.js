// Stock Watcher - Ticker Detail Page JavaScript

// Get ticker symbol from URL query parameter
const urlParams = new URLSearchParams(window.location.search);
const tickerSymbol = urlParams.get('symbol') || '';

// State
let isInWatchlist = false;

// Initialize page
document.addEventListener('DOMContentLoaded', () => {
    if (!tickerSymbol) {
        showError('No ticker symbol provided', 'Please search for a ticker');
        return;
    }
    
    loadTickerData(tickerSymbol);
    
    // Set up event listeners
    document.getElementById('search-btn').addEventListener('click', handleSearch);
    document.getElementById('ticker-search').addEventListener('keypress', (e) => {
        if (e.key === 'Enter') handleSearch();
    });
    document.getElementById('add-to-watchlist').addEventListener('click', handleAddToWatchlist);
});

// Load ticker data from API
async function loadTickerData(symbol) {
    try {
        showLoading();
        
        // Fetch company details and metrics in parallel
        const [detailsRes, metricsRes] = await Promise.all([
            fetch(`/ticker/${symbol}/details`),
            fetch(`/ticker/${symbol}/metrics`)
        ]);
        
        if (!detailsRes.ok) {
            throw new Error('Ticker not found');
        }
        
        const details = await detailsRes.json();
        const metrics = metricsRes.ok ? await metricsRes.json() : null;
        
        // Check if ticker is in watchlist
        await checkWatchlistStatus(symbol);
        
        // Render data
        renderCompanyHeader(details, metrics);
        renderCompanyInfo(details);
        renderDescription(details);
        
        showContent();
        
        // Initialize chart after content is visible
        if (window.ChartController) {
            setTimeout(() => {
                new ChartController(symbol);
            }, 100);
        }
    } catch (error) {
        console.error('Error loading ticker data:', error);
        showError('Failed to load ticker data', error.message);
    }
}

// Check if ticker is in user's watchlist
async function checkWatchlistStatus(symbol) {
    try {
        const res = await fetch('/watchlist');
        if (res.ok) {
            const watchlist = await res.json();
            isInWatchlist = watchlist.some(item => item.symbol === symbol);
            updateWatchlistButton();
        }
    } catch (error) {
        console.error('Error checking watchlist:', error);
    }
}

// Render company header (logo, name, price)
function renderCompanyHeader(details, metrics) {
    // Company name and ticker
    document.getElementById('company-name').textContent = details.name || 'Unknown Company';
    document.getElementById('ticker-symbol').textContent = details.symbol;
    document.getElementById('exchange').textContent = details.primary_exchange || '-';
    
    // Company logo or initials
    const logo = document.getElementById('company-logo');
    const initialsEl = document.getElementById('company-initials');
    
    if (details.logo_url) {
        // Show logo
        logo.src = details.logo_url;
        logo.style.display = 'block';
        initialsEl.style.display = 'none';
    } else {
        // Show initials
        const initials = generateInitials(details.symbol || details.name || '??');
        initialsEl.textContent = initials;
        logo.style.display = 'none';
        initialsEl.style.display = 'flex';
    }
    
    // Price data
    if (metrics) {
        const price = parseFloat(metrics.last_price) || 0;
        const change = parseFloat(metrics.price_change) || 0;
        const changePct = parseFloat(metrics.price_change_pct) || 0;
        
        document.getElementById('current-price').textContent = `$${price.toFixed(2)}`;
        
        const priceChangeEl = document.getElementById('price-change');
        const sign = change >= 0 ? '+' : '';
        priceChangeEl.textContent = `${sign}$${change.toFixed(2)} (${sign}${changePct.toFixed(2)}%)`;
        priceChangeEl.className = change >= 0 ? 'price-change positive' : 'price-change negative';
    }
}

// Render company info grid
function renderCompanyInfo(details) {
    // Market Cap
    const marketCap = details.market_cap;
    document.getElementById('market-cap').textContent = marketCap 
        ? formatMarketCap(marketCap)
        : '-';
    
    // Employees
    const employees = details.total_employees;
    document.getElementById('employees').textContent = employees 
        ? employees.toLocaleString()
        : '-';
    
    // Industry (SIC description)
    document.getElementById('industry').textContent = details.sic_description || '-';
    
    // IPO Date (format as "MMM DD, YYYY")
    const ipoDate = details.list_date;
    document.getElementById('ipo-date').textContent = ipoDate 
        ? formatDate(ipoDate)
        : '-';
    
    // Security Type
    const typeMap = {
        'CS': 'Common Stock',
        'ETF': 'ETF',
        'ADR': 'ADR',
        'ADRC': 'ADR Common',
        'PFD': 'Preferred Stock'
    };
    document.getElementById('security-type').textContent = typeMap[details.type] || details.type || '-';
    
    // Homepage
    const homepageLink = document.getElementById('homepage-link');
    if (details.homepage_url) {
        homepageLink.href = details.homepage_url;
        homepageLink.style.display = 'inline';
    } else {
        homepageLink.style.display = 'none';
    }
}

// Render company description
function renderDescription(details) {
    const description = details.description || 'No description available for this company.';
    document.getElementById('company-description').textContent = description;
}

// Format market cap for display
function formatMarketCap(value) {
    if (value >= 1e12) {
        return `$${(value / 1e12).toFixed(2)}T`;
    } else if (value >= 1e9) {
        return `$${(value / 1e9).toFixed(2)}B`;
    } else if (value >= 1e6) {
        return `$${(value / 1e6).toFixed(2)}M`;
    }
    return `$${value.toLocaleString()}`;
}

// Handle search
function handleSearch() {
    const searchInput = document.getElementById('ticker-search');
    const symbol = searchInput.value.trim().toUpperCase();
    
    if (symbol) {
        window.location.href = `/ticker?symbol=${symbol}`;
    }
}

// Handle add to watchlist
async function handleAddToWatchlist() {
    try {
        const btn = document.getElementById('add-to-watchlist');
        btn.disabled = true;
        
        if (isInWatchlist) {
            // Remove from watchlist
            const res = await fetch(`/watchlist/${tickerSymbol}`, {
                method: 'DELETE'
            });
            
            if (res.ok) {
                isInWatchlist = false;
                updateWatchlistButton();
                showToast('Removed from watchlist', 'success');
            } else {
                throw new Error('Failed to remove from watchlist');
            }
        } else {
            // Add to watchlist
            const res = await fetch('/watchlist', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ symbol: tickerSymbol })
            });
            
            if (res.ok) {
                isInWatchlist = true;
                updateWatchlistButton();
                showToast('Added to watchlist', 'success');
            } else {
                const error = await res.json();
                throw new Error(error.error || 'Failed to add to watchlist');
            }
        }
    } catch (error) {
        console.error('Error updating watchlist:', error);
        showToast(error.message, 'error');
    } finally {
        document.getElementById('add-to-watchlist').disabled = false;
    }
}

// Update watchlist button state
function updateWatchlistButton() {
    const btn = document.getElementById('add-to-watchlist');
    const starIcon = btn.querySelector('.star-icon');
    
    if (isInWatchlist) {
        btn.classList.add('added');
        starIcon.textContent = '★';
        btn.innerHTML = '<span class="star-icon">★</span> Remove from Watchlist';
    } else {
        btn.classList.remove('added');
        starIcon.textContent = '☆';
        btn.innerHTML = '<span class="star-icon">☆</span> Add to Watchlist';
    }
}

// Show toast notification
function showToast(message, type = 'info') {
    // Create toast element
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    toast.style.cssText = `
        position: fixed;
        bottom: 2rem;
        right: 2rem;
        padding: 1rem 1.5rem;
        background: ${type === 'success' ? '#10b981' : '#ef4444'};
        color: white;
        border-radius: 8px;
        font-weight: 500;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        z-index: 9999;
        animation: slideIn 0.3s ease;
    `;
    
    document.body.appendChild(toast);
    
    // Remove after 3 seconds
    setTimeout(() => {
        toast.style.animation = 'slideOut 0.3s ease';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// Show loading state
function showLoading() {
    document.getElementById('loading').classList.remove('hidden');
    document.getElementById('error-state').classList.add('hidden');
    document.getElementById('content').classList.add('hidden');
}

// Show error state
function showError(title, message) {
    document.getElementById('error-title').textContent = title;
    document.getElementById('error-message').textContent = message;
    
    document.getElementById('loading').classList.add('hidden');
    document.getElementById('error-state').classList.remove('hidden');
    document.getElementById('content').classList.add('hidden');
}


// Generate company initials from symbol or name
function generateInitials(text) {
    // Take first 2 characters of symbol (e.g., "AAPL" -> "AP")
    // or first letter of first 2 words (e.g., "Apple Inc." -> "AI")
    const cleaned = text.trim().toUpperCase();
    
    // If it's a symbol (all caps, no spaces), take first 2 chars
    if (!cleaned.includes(' ') && cleaned.length >= 2) {
        return cleaned.substring(0, 2);
    }
    
    // If it's a name with spaces, take first letter of first 2 words
    const words = cleaned.split(' ').filter(w => w.length > 0);
    if (words.length >= 2) {
        return words[0][0] + words[1][0];
    }
    
    // Fallback: first 2 characters
    return cleaned.substring(0, 2) || '??';
}

// Format date as "MMM DD, YYYY" (remove time and timezone)
function formatDate(dateString) {
    try {
        const date = new Date(dateString);
        const options = { year: 'numeric', month: 'short', day: '2-digit' };
        return date.toLocaleDateString('en-US', options);
    } catch (error) {
        return dateString; // Return original if parsing fails
    }
}

// Show content
function showContent() {
    document.getElementById('loading').classList.add('hidden');
    document.getElementById('error-state').classList.add('hidden');
    document.getElementById('content').classList.remove('hidden');
}

// Add CSS animations
const style = document.createElement('style');
style.textContent = `
    @keyframes slideIn {
        from {
            transform: translateX(100%);
            opacity: 0;
        }
        to {
            transform: translateX(0);
            opacity: 1;
        }
    }
    
    @keyframes slideOut {
        from {
            transform: translateX(0);
            opacity: 1;
        }
        to {
            transform: translateX(100%);
            opacity: 0;
        }
    }
`;
document.head.appendChild(style);
