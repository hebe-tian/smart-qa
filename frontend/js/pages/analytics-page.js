// Analytics page: summary stats, token trend, call stats, event feed
const AnalyticsPage = {
    async load() {
        await this.loadSummary();
        await this.loadEvents();
    },

    async refresh() {
        Toast.info('正在刷新...');
        await this.load();
        Toast.success('已刷新');
    },

    async loadSummary() {
        const result = await Api.get('/api/analytics/summary');
        if (!result || result.error) {
            Toast.error(result?.message || '加载失败');
            return;
        }

        this.renderStats(result.summary);
        this.renderTokenTrend(result.token_trend || []);
        this.renderCallStats(result.summary);
    },

    renderStats(summary) {
        const grid = document.getElementById('statsGrid');
        const stats = [
            { label: '用例总数', value: summary.total_cases || 0, type: 'primary' },
            { label: '生成次数', value: summary.total_generates || 0, type: 'info' },
            { label: 'AI调用次数', value: summary.total_ai_calls || 0, type: 'success' },
            { label: '总Token消耗', value: summary.total_tokens || 0, type: 'warning' },
            { label: '成功率', value: (summary.success_rate || 0) + '%', type: 'success' },
            { label: '失败次数', value: summary.failed_calls || 0, type: 'primary' },
        ];

        grid.innerHTML = stats.map(s => `
            <div class="stat-card ${s.type}">
                <div class="stat-label">${s.label}</div>
                <div class="stat-value">${s.value}</div>
            </div>
        `).join('');
    },

    renderTokenTrend(trend) {
        const container = document.getElementById('tokenTrend');
        if (!trend || trend.length === 0) {
            container.innerHTML = '<div class="empty-state"><div class="empty-state-text">暂无数据</div></div>';
            return;
        }

        const maxTokens = Math.max(...trend.map(t => t.tokens), 1);
        container.innerHTML = trend.map(t => {
            const percent = (t.tokens / maxTokens * 100).toFixed(1);
            return `
                <div class="bar-chart-item">
                    <div class="bar-chart-label">${t.date}</div>
                    <div class="bar-chart-track">
                        <div class="bar-chart-fill" style="width: ${percent}%">${t.tokens}</div>
                    </div>
                </div>
            `;
        }).join('');
    },

    renderCallStats(summary) {
        const container = document.getElementById('callStats');
        const success = summary.success_calls || 0;
        const failed = summary.failed_calls || 0;
        const total = success + failed || 1;

        container.innerHTML = `
            <div class="bar-chart-item">
                <div class="bar-chart-label">成功</div>
                <div class="bar-chart-track">
                    <div class="bar-chart-fill" style="width: ${(success / total * 100).toFixed(1)}%; background: var(--success);">${success}</div>
                </div>
            </div>
            <div class="bar-chart-item">
                <div class="bar-chart-label">失败</div>
                <div class="bar-chart-track">
                    <div class="bar-chart-fill" style="width: ${(failed / total * 100).toFixed(1)}%; background: var(--danger);">${failed}</div>
                </div>
            </div>
        `;
    },

    async loadEvents() {
        const result = await Api.get('/api/analytics/events?per_page=10');
        if (!result || result.error) return;

        const container = document.getElementById('eventFeed');
        const events = result.events || [];
        if (events.length === 0) {
            container.innerHTML = '<div class="empty-state"><div class="empty-state-text">暂无事件</div></div>';
            return;
        }

        container.innerHTML = events.map(e => {
            const date = new Date(e.created_at).toLocaleString('zh-CN');
            let dataStr = '';
            try { dataStr = JSON.stringify(JSON.parse(e.event_data_json || '{}')); } catch (err) {}
            return `
                <div class="event-feed-item">
                    <span class="event-feed-time">${date}</span>
                    <span class="event-feed-type">${e.event_type}</span>
                    <span class="event-feed-data">${dataStr}</span>
                </div>
            `;
        }).join('');
    },
};
