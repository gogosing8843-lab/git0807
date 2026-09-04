document.addEventListener('DOMContentLoaded', () => {
    let articlesData = [];
    let currentSourceFilter = 'all';
    let currentKeywordFilter = 'all';
    let searchQuery = '';

    const btnCrawl = document.getElementById('btn-crawl');
    const searchInput = document.getElementById('search-input');
    const newsGrid = document.getElementById('news-grid');
    const loadingSpinner = document.getElementById('loading-spinner');
    const emptyState = document.getElementById('empty-state');
    const showingCount = document.getElementById('showing-count');
    const paperContent = document.getElementById('paper-content');
    const paperDate = document.getElementById('paper-date');

    // Stat elements
    const statTotal = document.getElementById('stat-total');
    const statBusan = document.getElementById('stat-busan');
    const statKookje = document.getElementById('stat-kookje');
    const statTime = document.getElementById('stat-time');

    // Fetch initial news data
    fetchNewsData();

    // Crawl Button Listener
    btnCrawl.addEventListener('click', async () => {
        btnCrawl.disabled = true;
        btnCrawl.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> 크롤링 중...';
        loadingSpinner.classList.remove('hidden');
        newsGrid.classList.add('hidden');
        emptyState.classList.add('hidden');

        try {
            const res = await fetch('/api/crawl', { method: 'POST' });
            const data = await res.json();
            if (data.success) {
                articlesData = data.articles;
                updateStats(data);
                renderNews();
            } else {
                alert('뉴스 수집 중 오류가 발생했습니다: ' + (data.error || ''));
            }
        } catch (err) {
            console.error(err);
            alert('서버 연결 실패');
        } finally {
            btnCrawl.disabled = false;
            btnCrawl.innerHTML = '<i class="fa-solid fa-rotate-right icon-spin-hover"></i> 뉴스 수집 실행';
            loadingSpinner.classList.add('hidden');
            newsGrid.classList.remove('hidden');
        }
    });

    // Search Input Listener
    searchInput.addEventListener('input', (e) => {
        searchQuery = e.target.value.trim().toLowerCase();
        renderNews();
    });

    // Source Filter Buttons
    document.querySelectorAll('.filter-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            currentSourceFilter = btn.dataset.source;
            renderNews();
        });
    });

    // Keyword Tag Chips
    document.querySelectorAll('.tag-chip').forEach(chip => {
        chip.addEventListener('click', () => {
            document.querySelectorAll('.tag-chip').forEach(c => c.classList.remove('active'));
            chip.classList.add('active');
            currentKeywordFilter = chip.dataset.keyword;
            renderNews();
        });
    });

    // Fetch News Data Function
    async function fetchNewsData() {
        try {
            const res = await fetch('/api/news');
            const data = await res.json();
            articlesData = data.articles || [];
            updateStats(data);
            renderNews();
        } catch (err) {
            console.error("Fetch news failed", err);
        }
    }

    // Update Dashboard Stats
    function updateStats(data) {
        const total = data.articles ? data.articles.length : 0;
        const busanCount = data.articles ? data.articles.filter(a => a.source === '부산일보').length : 0;
        const kookjeCount = data.articles ? data.articles.filter(a => a.source === '국제신문').length : 0;

        statTotal.textContent = total;
        statBusan.textContent = busanCount;
        statKookje.textContent = kookjeCount;
        statTime.textContent = data.last_updated || new Date().toLocaleTimeString('ko-KR');
        paperDate.textContent = `날짜: ${new Date().toLocaleDateString('ko-KR')}`;
    }

    // Render Filtered News Cards & HWPX Preview
    function renderNews() {
        const filtered = articlesData.filter(item => {
            // Source Filter
            if (currentSourceFilter !== 'all' && item.source !== currentSourceFilter) {
                return false;
            }
            // Keyword Filter
            if (currentKeywordFilter !== 'all' && !item.title.includes(currentKeywordFilter) && item.keyword !== currentKeywordFilter) {
                return false;
            }
            // Search Query
            if (searchQuery) {
                const matchTitle = item.title.toLowerCase().includes(searchQuery);
                const matchSummary = item.summary.toLowerCase().includes(searchQuery);
                if (!matchTitle && !matchSummary) return false;
            }
            return true;
        });

        showingCount.textContent = filtered.length;

        if (filtered.length === 0) {
            newsGrid.classList.add('hidden');
            emptyState.classList.remove('hidden');
            paperContent.innerHTML = '<p style="color:#6b7280;">수집된 기사가 없습니다.</p>';
            return;
        }

        emptyState.classList.add('hidden');
        newsGrid.classList.remove('hidden');

        // Build News Card HTML
        newsGrid.innerHTML = filtered.map((item, idx) => {
            const sourceClass = item.source === '부산일보' ? 'busan' : 'kookje';
            const badgeClass = item.source === '부산일보' ? 'badge-busan' : 'badge-kookje';

            return `
                <div class="news-card glass-card ${sourceClass}">
                    <div class="card-top">
                        <span class="source-badge ${badgeClass}">${item.source}</span>
                        <span class="kw-badge">#${item.keyword || '부산시'}</span>
                    </div>
                    <a href="${item.url}" target="_blank" class="news-title">
                        ${escapeHtml(item.title)}
                    </a>
                    <div class="news-summary-box">
                        ${escapeHtml(item.summary)}
                    </div>
                    <div class="card-footer">
                        <a href="${item.url}" target="_blank" class="link-btn">
                            기사 원문 보기 <i class="fa-solid fa-arrow-up-right-from-square"></i>
                        </a>
                    </div>
                </div>
            `;
        }).join('');

        // Build HWPX Document Preview HTML
        paperContent.innerHTML = filtered.map((item, idx) => `
            <div class="paper-item">
                <div class="paper-item-title">
                    ${idx + 1}. (${item.keyword || '부산시'}) [${item.source}] ${escapeHtml(item.title)}
                </div>
                <div class="paper-item-summary">
                    주요 내용: ${escapeHtml(item.summary)}
                </div>
            </div>
        `).join('');
    }

    function escapeHtml(text) {
        if (!text) return '';
        return text
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }
});
