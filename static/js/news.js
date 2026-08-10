/**
 * News Feed - Modern Card Layout
 * Displays recent news articles with images, sentiment, and publisher info
 */

// Load news when page loads
document.addEventListener('DOMContentLoaded', () => {
    const urlParams = new URLSearchParams(window.location.search);
    const symbol = urlParams.get('symbol');
    
    if (symbol) {
        loadNews(symbol);
    }
});

async function loadNews(symbol) {
    const newsLoading = document.getElementById('news-loading');
    const newsError = document.getElementById('news-error');
    const newsEmpty = document.getElementById('news-empty');
    const newsList = document.getElementById('news-list');
    
    // Show loading state
    newsLoading.style.display = 'block';
    newsError.style.display = 'none';
    newsEmpty.style.display = 'none';
    newsList.style.display = 'none';
    
    try {
        const response = await fetch(`/ticker/${symbol}/news?limit=20`);
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        
        const articles = await response.json();
        
        // Hide loading
        newsLoading.style.display = 'none';
        
        if (!articles || articles.length === 0) {
            newsEmpty.style.display = 'block';
            return;
        }
        
        // Render news cards
        newsList.innerHTML = articles.map(article => renderNewsCard(article)).join('');
        newsList.style.display = 'grid';
        
    } catch (error) {
        console.error('Failed to load news:', error);
        newsLoading.style.display = 'none';
        newsError.style.display = 'block';
    }
}

function renderNewsCard(article) {
    const sentiment = article.sentiment || 'neutral';
    const sentimentColor = {
        'positive': '#10b981',
        'negative': '#ef4444',
        'neutral': '#6b7280'
    }[sentiment.toLowerCase()] || '#6b7280';
    
    const sentimentEmoji = {
        'positive': '📈',
        'negative': '📉',
        'neutral': '➖'
    }[sentiment.toLowerCase()] || '➖';
    
    // Format published date
    const publishedDate = article.published_utc 
        ? new Date(article.published_utc).toLocaleDateString('en-US', {
            month: 'short',
            day: 'numeric',
            year: 'numeric'
        })
        : 'Unknown date';
    
    // Publisher info
    const publisherName = article.publisher_name || article.publisher?.name || 'Unknown';
    const publisherLogo = article.publisher?.logo_url || '';
    
    // Fallback image if none provided
    const imageUrl = article.image_url || 'https://via.placeholder.com/400x200?text=No+Image';
    
    return `
        <article class="news-card">
            <div class="news-card-image">
                <img src="${imageUrl}" 
                     alt="${escapeHtml(article.title)}"
                     onerror="this.src='https://via.placeholder.com/400x200?text=No+Image'">
                ${sentiment && sentiment !== 'neutral' ? `
                <div class="news-card-sentiment" style="background-color: ${sentimentColor}">
                    ${sentimentEmoji} ${sentiment.charAt(0).toUpperCase() + sentiment.slice(1)}
                </div>
                ` : ''}
            </div>
            
            <div class="news-card-content">
                <div class="news-card-header">
                    <div class="news-card-publisher">
                        ${publisherLogo ? `
                        <img src="${publisherLogo}" 
                             alt="${escapeHtml(publisherName)}"
                             onerror="this.style.display='none'">
                        ` : ''}
                        <span>${escapeHtml(publisherName)}</span>
                    </div>
                    <time class="news-card-date">${publishedDate}</time>
                </div>
                
                <h3 class="news-card-title">
                    <a href="${article.article_url}" target="_blank" rel="noopener noreferrer">
                        ${escapeHtml(article.title)}
                    </a>
                </h3>
                
                ${article.description ? `
                <p class="news-card-description">
                    ${escapeHtml(article.description)}
                </p>
                ` : ''}
                
                ${article.author ? `
                <div class="news-card-meta">
                    <span class="news-card-author">By ${escapeHtml(article.author)}</span>
                </div>
                ` : ''}
            </div>
        </article>
    `;
}

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
