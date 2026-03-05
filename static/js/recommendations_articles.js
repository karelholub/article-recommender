(function initRecommendationsArticlesModule(globalScope) {
    function formatDate(dateString) {
        if (!dateString) return 'No date';
        try {
            const date = new Date(dateString);
            return date.toLocaleDateString('en-US', {
                year: 'numeric',
                month: 'short',
                day: 'numeric',
            });
        } catch (_error) {
            return 'Invalid date';
        }
    }

    function getArticleTimestamp(article) {
        return article?.metadata?.scraped_at || article?.metadata?.published_at || article?.published_at || null;
    }

    function compareArticles(left, right, mode) {
        if (mode === 'title_asc') {
            return String(left.title || '').localeCompare(String(right.title || ''), undefined, { sensitivity: 'base' });
        }
        if (mode === 'title_desc') {
            return String(right.title || '').localeCompare(String(left.title || ''), undefined, { sensitivity: 'base' });
        }
        const leftTs = new Date(getArticleTimestamp(left) || 0).getTime();
        const rightTs = new Date(getArticleTimestamp(right) || 0).getTime();
        if (mode === 'oldest') return leftTs - rightTs;
        return rightTs - leftTs;
    }

    function displayArticles(ctx) {
        const {
            articles,
            currentArticle,
            articleSearchTerm,
            articleSourceFilter,
            articleSortMode,
            articlePageSize,
            articleCurrentPage,
            setArticleCurrentPage,
        } = ctx;
        const articleList = document.getElementById('article-list');
        const summary = document.getElementById('article-list-summary');
        const pageInfo = document.getElementById('article-page-info');
        const prevButton = document.getElementById('article-page-prev');
        const nextButton = document.getElementById('article-page-next');
        if (!articles || articles.length === 0) {
            articleList.innerHTML = `
                <div class="alert alert-info">
                    <i class="fas fa-info-circle me-2"></i>
                    No articles available.
                </div>
            `;
            if (summary) summary.textContent = '0 articles';
            if (pageInfo) pageInfo.textContent = 'Page 0 of 0';
            if (prevButton) prevButton.disabled = true;
            if (nextButton) nextButton.disabled = true;
            return;
        }

        const filtered = articles
            .filter((article) => {
                const source = article.source || 'unknown';
                if (articleSourceFilter !== 'all' && source !== articleSourceFilter) {
                    return false;
                }
                if (!articleSearchTerm) return true;
                const haystack = [
                    article.article_id || '',
                    article.title || '',
                    article.content || '',
                    article.source || '',
                    article.section || '',
                    article.metadata?.section || '',
                ].join(' ').toLowerCase();
                return haystack.includes(articleSearchTerm);
            })
            .sort((left, right) => compareArticles(left, right, articleSortMode));

        const totalPages = Math.max(1, Math.ceil(filtered.length / articlePageSize));
        const boundedPage = Math.min(Math.max(articleCurrentPage, 1), totalPages);
        setArticleCurrentPage(boundedPage);
        const startIndex = (boundedPage - 1) * articlePageSize;
        const paged = filtered.slice(startIndex, startIndex + articlePageSize);
        const endIndex = startIndex + paged.length;

        if (!paged.length) {
            articleList.innerHTML = '<div class="text-muted">No matching articles for current filters.</div>';
        } else {
            articleList.innerHTML = `
                <div class="table-responsive">
                    <table class="table table-sm align-middle">
                        <thead>
                            <tr>
                                <th>Article</th>
                                <th>Source</th>
                                <th>Section</th>
                                <th>Published</th>
                                <th class="text-end">Action</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${paged.map(article => {
                                const isSelected = currentArticle && currentArticle.article_id === article.article_id;
                                const published = getArticleTimestamp(article);
                                const snippet = (article.content || '').trim();
                                const section = article.section || article.metadata?.section || '-';
                                return `
                                    <tr class="${isSelected ? 'table-primary' : ''}">
                                        <td>
                                            <div class="fw-semibold">${article.title || 'No title'}</div>
                                            <div class="small text-muted">${article.article_id || 'n/a'}</div>
                                            <div class="small text-muted">${snippet ? `${snippet.substring(0, 95)}${snippet.length > 95 ? '...' : ''}` : 'No preview content'}</div>
                                        </td>
                                        <td><span class="badge text-bg-light border">${article.source || 'unknown'}</span></td>
                                        <td>${section}</td>
                                        <td class="small text-muted">${published ? formatDate(published) : 'n/a'}</td>
                                        <td class="text-end">
                                            <button class="btn btn-sm ${isSelected ? 'btn-primary' : 'btn-outline-primary'} select-article-btn" data-id="${article.article_id}">
                                                ${isSelected ? 'Selected' : 'Select'}
                                            </button>
                                        </td>
                                    </tr>
                                `;
                            }).join('')}
                        </tbody>
                    </table>
                </div>
            `;
        }
        if (summary) {
            summary.textContent = filtered.length
                ? `Showing ${startIndex + 1}-${endIndex} of ${filtered.length} matching articles (${articles.length} total)`
                : `0 matching articles (${articles.length} total)`;
        }
        if (pageInfo) pageInfo.textContent = `Page ${boundedPage} of ${totalPages}`;
        if (prevButton) prevButton.disabled = boundedPage <= 1;
        if (nextButton) nextButton.disabled = boundedPage >= totalPages;
    }

    function displayArticle(article, ctx) {
        if (!article) return;
        ctx.setCurrentArticle(article);
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

        document.getElementById('show-similar').style.display = 'inline-block';
        const whyNotInput = document.getElementById('why-not-article-id');
        if (whyNotInput && !whyNotInput.value) {
            whyNotInput.value = article.article_id || '';
        }
        const whyThisInput = document.getElementById('why-this-article-id');
        if (whyThisInput && !whyThisInput.value) {
            whyThisInput.value = article.article_id || '';
        }
    }

    function refreshArticleSourceFilterOptions(ctx) {
        const sourceSelect = document.getElementById('article-source-select');
        if (!sourceSelect) return;
        const sources = Array.from(new Set((ctx.articles || []).map(item => item.source || 'unknown')))
            .sort((a, b) => a.localeCompare(b));
        sourceSelect.innerHTML = '<option value="all">All sources</option>' + sources.map(src => `<option value="${src}">${src}</option>`).join('');
        if (ctx.articleSourceFilter !== 'all' && !sources.includes(ctx.articleSourceFilter)) {
            ctx.setArticleSourceFilter('all');
        }
        sourceSelect.value = ctx.articleSourceFilter;
    }

    function selectArticleById(articleId, ctx) {
        const article = (ctx.articles || []).find(a => a.article_id === articleId);
        if (!article) return;
        displayArticle(article, ctx);
        displayArticles(ctx);
    }

    globalScope.RecommendationsArticlesModule = {
        displayArticles,
        displayArticle,
        refreshArticleSourceFilterOptions,
        selectArticleById,
    };
})(window);
