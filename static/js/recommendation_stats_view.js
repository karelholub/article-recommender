(function initRecommendationStatsView(globalScope) {
    function render(stats, articleItems = []) {
        const statsContainer = document.getElementById('article-stats');
        if (!statsContainer) return;

        const totalArticles = Number(stats.total_articles || articleItems.length || 0);
        const freshness = stats.freshness_distribution || {};
        const today = Number(freshness.today || 0);
        const thisWeek = Number(freshness.this_week || 0);
        const thisMonth = Number(freshness.this_month || 0);
        const older = Number(freshness.older || 0);
        const fresh7d = today + thisWeek;
        const staleRatio = totalArticles ? older / totalArticles : 0;
        const freshRatio = totalArticles ? fresh7d / totalArticles : 0;
        const quality = stats.cluster_quality || {};

        const sourceCounts = {};
        const sectionCounts = {};
        let missingUrlCount = 0;
        let shortContentCount = 0;
        articleItems.forEach((item) => {
            const source = item.source || 'unknown';
            const section = item.section || item.metadata?.section || 'unknown';
            sourceCounts[source] = (sourceCounts[source] || 0) + 1;
            sectionCounts[section] = (sectionCounts[section] || 0) + 1;
            if (!item.metadata?.url) missingUrlCount += 1;
            if (!item.content || item.content.trim().length < 120) shortContentCount += 1;
        });
        const sourceRows = Object.entries(sourceCounts)
            .sort((a, b) => b[1] - a[1])
            .slice(0, 6);
        const sectionRows = Object.entries(sectionCounts)
            .sort((a, b) => b[1] - a[1])
            .slice(0, 6);
        const topSourceShare = sourceRows.length && totalArticles ? sourceRows[0][1] / totalArticles : 0;
        const unknownSectionShare = totalArticles ? Number(sectionCounts.unknown || 0) / totalArticles : 0;
        const shortContentShare = totalArticles ? shortContentCount / totalArticles : 0;
        const missingUrlShare = totalArticles ? missingUrlCount / totalArticles : 0;
        const unclusteredShare = totalArticles ? Number(quality.unclustered_count || 0) / totalArticles : 0;

        const actions = [];
        if (!totalArticles) {
            actions.push({
                level: 'danger',
                title: 'No indexed content',
                message: 'Ingestion is empty. Add or sync source connectors in Operations before testing recommendations.',
                target: '/operations'
            });
        }
        if (staleRatio > 0.45) {
            actions.push({
                level: 'warning',
                title: 'Catalog is stale',
                message: `${(staleRatio * 100).toFixed(1)}% of content is older than 30 days. Increase connector sync cadence and validate source freshness.`,
                target: '/operations'
            });
        }
        if (topSourceShare > 0.6) {
            actions.push({
                level: 'warning',
                title: 'Source concentration risk',
                message: `Top source contributes ${(topSourceShare * 100).toFixed(1)}% of inventory. Add more sources or reduce source weight bias.`,
                target: '/recommendations'
            });
        }
        if (unclusteredShare > 0.35) {
            actions.push({
                level: 'warning',
                title: 'Topic clustering quality is low',
                message: `${(unclusteredShare * 100).toFixed(1)}% of articles are unclustered. Run full embedding refresh and check extraction quality.`,
                target: '/embeddings'
            });
        }
        if (unknownSectionShare > 0.2 || missingUrlShare > 0.15 || shortContentShare > 0.25) {
            actions.push({
                level: 'info',
                title: 'Metadata quality needs cleanup',
                message: `Unknown sections ${(unknownSectionShare * 100).toFixed(1)}%, missing URLs ${(missingUrlShare * 100).toFixed(1)}%, short content ${(shortContentShare * 100).toFixed(1)}%. Improve scraper selectors and normalization.`,
                target: '/operations'
            });
        }
        if (!actions.length) {
            actions.push({
                level: 'success',
                title: 'Content inventory looks healthy',
                message: 'Freshness, source spread, and metadata quality are within normal operational thresholds.',
                target: ''
            });
        }

        const sourceTableRows = sourceRows.map(([name, count]) => `
            <tr>
                <td>${name}</td>
                <td>${count}</td>
                <td>${totalArticles ? `${((count / totalArticles) * 100).toFixed(1)}%` : '0.0%'}</td>
            </tr>
        `).join('');
        const sectionTableRows = sectionRows.map(([name, count]) => `
            <tr>
                <td>${name}</td>
                <td>${count}</td>
                <td>${totalArticles ? `${((count / totalArticles) * 100).toFixed(1)}%` : '0.0%'}</td>
            </tr>
        `).join('');
        const actionRows = actions.map((item) => `
            <div class="border rounded p-2 mb-2">
                <div class="d-flex justify-content-between align-items-center">
                    <strong>${item.title}</strong>
                    <span class="badge text-bg-${item.level}">${item.level}</span>
                </div>
                <div class="small text-muted mt-1">${item.message}</div>
                ${item.target ? `<div class="small mt-1">Suggested workspace: <a href="${item.target}">${item.target}</a></div>` : ''}
            </div>
        `).join('');

        statsContainer.innerHTML = `
            <div class="d-flex flex-wrap gap-2 mb-2">
                <span class="badge text-bg-light border">Total ${totalArticles}</span>
                <span class="badge ${freshRatio >= 0.45 ? 'text-bg-success' : 'text-bg-warning'}">Fresh 7d ${(freshRatio * 100).toFixed(1)}%</span>
                <span class="badge ${staleRatio <= 0.35 ? 'text-bg-success' : 'text-bg-warning'}">Older than 30d ${(staleRatio * 100).toFixed(1)}%</span>
                <span class="badge ${topSourceShare <= 0.5 ? 'text-bg-success' : 'text-bg-warning'}">Top source share ${(topSourceShare * 100).toFixed(1)}%</span>
                <span class="badge ${unclusteredShare <= 0.25 ? 'text-bg-success' : 'text-bg-warning'}">Unclustered ${(unclusteredShare * 100).toFixed(1)}%</span>
            </div>
            <div class="row g-2 mb-2 small">
                <div class="col-md-3"><strong>Today:</strong> ${today}</div>
                <div class="col-md-3"><strong>7 days:</strong> ${thisWeek}</div>
                <div class="col-md-3"><strong>30 days:</strong> ${thisMonth}</div>
                <div class="col-md-3"><strong>Older:</strong> ${older}</div>
            </div>
            <div class="row g-3">
                <div class="col-lg-6">
                    <h6 class="mb-2">Source mix (top 6)</h6>
                    <div class="table-responsive">
                        <table class="table table-sm mb-0">
                            <thead><tr><th>Source</th><th>Articles</th><th>Share</th></tr></thead>
                            <tbody>${sourceTableRows || '<tr><td colspan="3" class="text-muted">No source data.</td></tr>'}</tbody>
                        </table>
                    </div>
                </div>
                <div class="col-lg-6">
                    <h6 class="mb-2">Section coverage (top 6)</h6>
                    <div class="table-responsive">
                        <table class="table table-sm mb-0">
                            <thead><tr><th>Section</th><th>Articles</th><th>Share</th></tr></thead>
                            <tbody>${sectionTableRows || '<tr><td colspan="3" class="text-muted">No section data.</td></tr>'}</tbody>
                        </table>
                    </div>
                </div>
            </div>
            <details class="mt-2">
                <summary class="small">Data quality indicators</summary>
                <div class="small text-muted mt-1">
                    Missing URL: ${(missingUrlShare * 100).toFixed(1)}% (${missingUrlCount}) |
                    Short content (&lt;120 chars): ${(shortContentShare * 100).toFixed(1)}% (${shortContentCount}) |
                    Unknown section: ${(unknownSectionShare * 100).toFixed(1)}% (${sectionCounts.unknown || 0}) |
                    Cluster coverage: ${(Number(quality.coverage_ratio || 0) * 100).toFixed(1)}%
                </div>
            </details>
            <div class="mt-3">
                <h6 class="mb-2">Actionable recommendations</h6>
                ${actionRows}
            </div>
        `;
    }

    globalScope.RecommendationStatsView = { render };
})(window);
