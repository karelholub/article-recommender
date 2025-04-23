// Global state
let currentArticle = null;
let articles = [];

// Initialize the application
document.addEventListener('DOMContentLoaded', () => {
    loadArticles();
    loadStats();
    setupEventListeners();
});

// Load articles from the server
async function loadArticles() {
    try {
        // Show loading state
        const articleList = document.getElementById('article-list');
        articleList.innerHTML = `
            <div class="text-center p-3">
                <div class="spinner-border text-primary" role="status">
                    <span class="visually-hidden">Loading...</span>
                </div>
                <p class="mt-2">Loading articles...</p>
            </div>
        `;

        const response = await fetch('/api/articles');
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to load articles');
        }
        articles = await response.json();
        if (!Array.isArray(articles)) {
            throw new Error('Invalid response format');
        }
        displayArticles();
    } catch (error) {
        console.error('Error loading articles:', error);
        showError('Failed to load articles: ' + error.message);
        // Display empty state
        const articleList = document.getElementById('article-list');
        articleList.innerHTML = `
            <div class="alert alert-warning">
                <i class="fas fa-exclamation-triangle me-2"></i>
                No articles available. Please try again later.
            </div>
        `;
    }
}

// Load article statistics
async function loadStats() {
    try {
        const response = await fetch('/api/stats');
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to load statistics');
        }
        
        const stats = await response.json();
        displayStats(stats);
    } catch (error) {
        console.error('Error loading statistics:', error);
        showError('Failed to load statistics: ' + error.message);
    }
}

// Display articles in the sidebar
function displayArticles() {
    const articleList = document.getElementById('article-list');
    if (!articles || articles.length === 0) {
        articleList.innerHTML = `
            <div class="alert alert-info">
                <i class="fas fa-info-circle me-2"></i>
                No articles available.
            </div>
        `;
        return;
    }
    
    articleList.innerHTML = articles.map(article => `
        <a href="#" class="list-group-item list-group-item-action" data-id="${article.article_id}">
            <div class="d-flex w-100 justify-content-between">
                <h6 class="mb-1">${article.title}</h6>
            </div>
            ${article.metadata.scraped_at ? `
                <small class="text-muted">
                    <i class="fas fa-clock me-1"></i>
                    ${formatDate(article.metadata.scraped_at)}
                </small>
            ` : ''}
        </a>
    `).join('');
}

// Display a single article
function displayArticle(article) {
    if (!article) return;
    
    currentArticle = article;
    
    document.getElementById('article-title').textContent = article.title || 'No Title';
    document.getElementById('article-content').textContent = article.content || 'No content available';
    
    const articleUrl = article.metadata?.url;
    const urlElement = document.getElementById('article-url');
    if (articleUrl) {
        urlElement.href = articleUrl;
        urlElement.style.display = 'inline-block';
    } else {
        urlElement.style.display = 'none';
    }
    
    // Show the similar articles section button
    document.getElementById('show-similar').style.display = 'inline-block';
}

// Show similar articles
async function showSimilarArticles() {
    if (!currentArticle) {
        showError('Please select an article first');
        return;
    }
    
    try {
        // Show loading state
        const similarList = document.getElementById('similar-list');
        similarList.innerHTML = `
            <div class="text-center p-3">
                <div class="spinner-border text-primary" role="status">
                    <span class="visually-hidden">Loading...</span>
                </div>
                <p class="mt-2">Finding similar articles...</p>
            </div>
        `;
        document.getElementById('similar-articles').style.display = 'block';
        
        const response = await fetch(`/api/similar/${currentArticle.article_id}`);
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to load similar articles');
        }
        
        const similarArticles = await response.json();
        if (!Array.isArray(similarArticles)) {
            throw new Error('Invalid response format');
        }
        
        if (similarArticles.length === 0) {
            similarList.innerHTML = `
                <div class="alert alert-info">
                    <i class="fas fa-info-circle me-2"></i>
                    No similar articles found.
                </div>
            `;
        } else {
            similarList.innerHTML = similarArticles.map(article => `
                <div class="similar-article fade-in">
                    <h5>${article.title || 'No Title'}</h5>
                    <p class="mb-2">${article.content ? article.content.substring(0, 150) + '...' : 'No content available'}</p>
                    <div class="d-flex justify-content-between align-items-center">
                        <div class="similarity-indicators">
                            <div class="d-flex gap-3">
                                <div class="similarity-indicator" title="Semantic Similarity">
                                    <i class="fas fa-brain me-1"></i>
                                    <span>${(article.similarity_components.semantic * 100).toFixed(1)}%</span>
                                </div>
                                <div class="similarity-indicator" title="Content Freshness">
                                    <i class="fas fa-clock me-1"></i>
                                    <span>${(article.similarity_components.freshness * 100).toFixed(1)}%</span>
                                </div>
                                <div class="similarity-indicator" title="Topic Clustering">
                                    <i class="fas fa-layer-group me-1"></i>
                                    <span>${(article.similarity_components.topic * 100).toFixed(1)}%</span>
                                </div>
                            </div>
                            <small class="text-muted d-block mt-1">
                                Overall Score: ${(article.score * 100).toFixed(1)}%
                            </small>
                        </div>
                        ${article.metadata?.url ? `
                            <a href="${article.metadata.url}" target="_blank" class="btn btn-sm btn-outline-primary">
                                <i class="fas fa-external-link-alt me-1"></i>
                                Read More
                            </a>
                        ` : ''}
                    </div>
                </div>
            `).join('');
        }
    } catch (error) {
        console.error('Error loading similar articles:', error);
        showError('Failed to load similar articles: ' + error.message);
        const similarList = document.getElementById('similar-list');
        similarList.innerHTML = `
            <div class="alert alert-danger">
                <i class="fas fa-exclamation-circle me-2"></i>
                Failed to load similar articles. Please try again.
            </div>
        `;
    }
}

// Display article statistics
function displayStats(stats) {
    const statsContainer = document.getElementById('article-stats');
    
    // Create freshness distribution chart
    const freshnessData = {
        labels: ['Today', 'This Week', 'This Month', 'Older'],
        datasets: [{
            data: [
                stats.freshness_distribution.today,
                stats.freshness_distribution.this_week,
                stats.freshness_distribution.this_month,
                stats.freshness_distribution.older
            ],
            backgroundColor: [
                '#28a745',  // Today - green
                '#17a2b8',  // This week - cyan
                '#ffc107',  // This month - yellow
                '#6c757d'   // Older - gray
            ]
        }]
    };
    
    // Create cluster distribution chart
    const clusterData = {
        labels: Object.keys(stats.cluster_distribution).map(cluster => `Cluster ${cluster}`),
        datasets: [{
            data: Object.values(stats.cluster_distribution),
            backgroundColor: [
                '#007bff',  // Blue
                '#6610f2',  // Purple
                '#6f42c1',  // Indigo
                '#e83e8c',  // Pink
                '#fd7e14'   // Orange
            ]
        }]
    };
    
    // Create HTML for statistics
    statsContainer.innerHTML = `
        <div class="row">
            <div class="col-md-6">
                <h5 class="mb-3">Content Freshness</h5>
                <canvas id="freshnessChart"></canvas>
            </div>
            <div class="col-md-6">
                <h5 class="mb-3">Topic Clusters</h5>
                <canvas id="clusterChart"></canvas>
            </div>
        </div>
        <div class="mt-4">
            <h5>Topic Overview</h5>
            <div class="row">
                ${Object.entries(stats.cluster_topics).map(([cluster, topics]) => `
                    <div class="col-md-6 mb-3">
                        <div class="card">
                            <div class="card-body">
                                <h6 class="card-title">Cluster ${cluster}</h6>
                                <p class="card-text">
                                    ${topics.map(title => `
                                        <small class="d-block text-muted mb-1">
                                            <i class="fas fa-angle-right me-1"></i>
                                            ${title}
                                        </small>
                                    `).join('')}
                                </p>
                            </div>
                        </div>
                    </div>
                `).join('')}
            </div>
        </div>
    `;
    
    // Create charts
    new Chart(document.getElementById('freshnessChart'), {
        type: 'pie',
        data: freshnessData,
        options: {
            responsive: true,
            plugins: {
                legend: {
                    position: 'bottom'
                }
            }
        }
    });
    
    new Chart(document.getElementById('clusterChart'), {
        type: 'pie',
        data: clusterData,
        options: {
            responsive: true,
            plugins: {
                legend: {
                    position: 'bottom'
                }
            }
        }
    });
}

// Setup event listeners
function setupEventListeners() {
    // Article list click handler
    document.getElementById('article-list').addEventListener('click', (e) => {
        e.preventDefault();
        const articleItem = e.target.closest('.list-group-item');
        if (articleItem) {
            const articleId = articleItem.dataset.id;
            const article = articles.find(a => a.article_id === articleId);
            if (article) {
                // Remove selected class from all items
                document.querySelectorAll('.list-group-item').forEach(item => {
                    item.classList.remove('active');
                });
                // Add selected class to clicked item
                articleItem.classList.add('active');
                displayArticle(article);
            }
        }
    });
    
    // Show similar articles button
    document.getElementById('show-similar').addEventListener('click', showSimilarArticles);
}

// Utility functions
function formatDate(dateString) {
    if (!dateString) return 'No date';
    try {
        const date = new Date(dateString);
        return date.toLocaleDateString('en-US', {
            year: 'numeric',
            month: 'short',
            day: 'numeric'
        });
    } catch (e) {
        return 'Invalid date';
    }
}

function showError(message) {
    // Create toast notification
    const toast = document.createElement('div');
    toast.className = 'toast show position-fixed bottom-0 end-0 m-3';
    toast.style.zIndex = '1050';
    toast.innerHTML = `
        <div class="toast-header bg-danger text-white">
            <i class="fas fa-exclamation-circle me-2"></i>
            <strong class="me-auto">Error</strong>
            <button type="button" class="btn-close btn-close-white" data-bs-dismiss="toast"></button>
        </div>
        <div class="toast-body">
            ${message}
        </div>
    `;
    
    document.body.appendChild(toast);
    
    // Remove toast after 5 seconds
    setTimeout(() => {
        toast.remove();
    }, 5000);
} 