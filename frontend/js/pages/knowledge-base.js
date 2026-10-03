// Knowledge base management page: stats overview, code library, Q&A history
const KnowledgeBase = {
    currentTab: 'code',

    init() {
        this.loadStatus();
        this.loadQaHistory();
        // Initialize code source management
        if (typeof CodeSource !== 'undefined' && CodeSource.init) {
            CodeSource.init();
        }
    },

    // ------------------------------------------------------------------
    // Tab switching
    // ------------------------------------------------------------------

    switchTab(tab) {
        if (this.currentTab === tab) return;
        this.currentTab = tab;

        document.querySelectorAll('.kb-tab-item').forEach(el => {
            el.classList.toggle('active', el.dataset.tab === tab);
        });
        document.getElementById('kbTabCode').classList.toggle('active', tab === 'code');
        document.getElementById('kbTabQa').classList.toggle('active', tab === 'qa');

        if (tab === 'qa') {
            this.loadQaHistory();
        }
    },

    // ------------------------------------------------------------------
    // Status & Stats
    // ------------------------------------------------------------------

    async loadStatus() {
        const result = await Api.get('/api/rag/status');
        const dot = document.getElementById('kbStatusDot');
        const text = document.getElementById('kbStatusText');
        const meta = document.getElementById('kbStatusMeta');
        const rebuildBtn = document.getElementById('rebuildBtn');

        if (!result || result.error) {
            dot.className = 'kb-status-indicator error';
            text.textContent = '状态获取失败';
            meta.textContent = result?.message || '';
            rebuildBtn.disabled = true;
            return;
        }

        if (!result.embedding_configured) {
            dot.className = 'kb-status-indicator warning';
            text.textContent = '未配置 Embedding 模型';
            meta.textContent = '请在 AI配置 页面设置';
            rebuildBtn.disabled = true;
            this.renderStats(result);
            return;
        }

        if (!result.is_ready) {
            dot.className = 'kb-status-indicator warning';
            text.textContent = '知识库未构建';
            meta.textContent = '点击"重建索引"开始';
            rebuildBtn.disabled = false;
            this.renderStats(result);
            return;
        }

        dot.className = 'kb-status-indicator ready';
        text.textContent = '知识库就绪';
        const lastBuilt = result.last_built_at
            ? new Date(result.last_built_at).toLocaleString('zh-CN')
            : '';
        meta.textContent = `共 ${result.chunk_count} 条索引${lastBuilt ? ' · ' + lastBuilt : ''}`;
        rebuildBtn.disabled = false;

        this.renderStats(result);

        // Also load code document count for stats
        this.loadCodeStats();
    },

    renderStats(result) {
        const breakdown = result.by_project_type || {};
        // Aggregate across all project types
        let reqCount = 0, qaCount = 0, qaNegCount = 0, codeCount = 0;
        for (const ptKey of Object.keys(breakdown)) {
            const pt = breakdown[ptKey];
            reqCount += (pt.requirement || 0) + (pt.module || 0) + (pt.test_case || 0);
            qaCount += pt.qa || 0;
            qaNegCount += pt.qa_negative || 0;
            codeCount += pt.code || 0;
        }

        // Requirement docs stat
        document.getElementById('kbStatReq').textContent = reqCount;
        let reqSubParts = [];
        for (const ptKey of Object.keys(breakdown)) {
            const pt = breakdown[ptKey];
            const ptReq = (pt.requirement || 0) + (pt.module || 0) + (pt.test_case || 0);
            if (ptReq > 0) reqSubParts.push(`${ptKey === 'production' ? '线上' : ptKey} ${ptReq}`);
        }
        document.getElementById('kbStatReqSub').textContent = reqSubParts.length
            ? reqSubParts.join(' / ')
            : '需求 / 模块 / 测试用例';

        // Q&A stat
        const qaTotal = qaCount + qaNegCount;
        document.getElementById('kbStatQa').textContent = qaTotal;
        document.getElementById('kbStatQaSub').textContent = qaTotal > 0
            ? `准确 ${qaCount} / 错误参考 ${qaNegCount}`
            : '已采纳问答 / 错误参考';

        // Code stat (will be updated by loadCodeStats)
        document.getElementById('kbStatCode').textContent = codeCount;
    },

    async loadCodeStats() {
        const result = await Api.get('/api/code/documents');
        if (!result || result.error) return;

        const docs = result.documents || [];
        const indexedDocs = docs.filter(d => d.indexed);
        const totalChunks = docs.reduce((sum, d) => sum + (d.chunk_count || 0), 0);
        const codeCount = parseInt(document.getElementById('kbStatCode').textContent) || 0;

        document.getElementById('kbStatCode').textContent = totalChunks || codeCount;
        document.getElementById('kbStatCodeSub').textContent = `${docs.length} 个文档 / ${indexedDocs.length} 个已索引`;
    },

    // ------------------------------------------------------------------
    // Q&A History
    // ------------------------------------------------------------------

    async loadQaHistory() {
        const result = await Api.get('/api/kbqa/sessions');
        const container = document.getElementById('kbQaHistoryList');

        if (!result || result.error) {
            container.innerHTML = '<div class="kb-code-doc-empty">加载失败</div>';
            return;
        }

        const sessions = result.sessions || [];
        if (sessions.length === 0) {
            container.innerHTML = '<div class="kb-code-doc-empty">暂无问答历史<br><span style="font-size:11px;color:var(--text-muted)">前往「问答」页面开始提问</span></div>';
            return;
        }

        // Header row
        let html = `
            <div class="kb-qa-history-row kb-qa-history-row-header">
                <div>标题</div>
                <div>状态</div>
                <div>反馈</div>
                <div>消息数</div>
                <div>时间</div>
                <div>操作</div>
            </div>
        `;

        html += sessions.map(s => this.renderQaHistoryRow(s)).join('');
        container.innerHTML = html;
    },

    renderQaHistoryRow(session) {
        const statusLabel = this._getSessionStatus(session);
        const timeStr = this._formatTime(session.updated_at || session.created_at);

        let feedbackBadge;
        if (session.status === 'feedback_given') {
            if (session.feedback === 'positive') {
                feedbackBadge = '<span class="badge badge-success">准确</span>';
            } else {
                feedbackBadge = '<span class="badge badge-warning">不准确</span>';
            }
        } else {
            feedbackBadge = '<span class="badge badge-muted">未反馈</span>';
        }

        const msgCount = session.message_count || '-';

        return `
            <div class="kb-qa-history-row">
                <div class="kb-qa-history-title">${this.escapeHtml(session.title)}</div>
                <div><span class="kb-session-card-status ${session.status}">${statusLabel}</span></div>
                <div>${feedbackBadge}</div>
                <div>${msgCount}</div>
                <div class="kb-qa-history-time">${timeStr}</div>
                <div class="kb-code-doc-actions">
                    <button onclick="KnowledgeBase.viewSession(${session.id})">查看</button>
                    <button class="delete" onclick="KnowledgeBase.deleteSession(${session.id})">删除</button>
                </div>
            </div>
        `;
    },

    viewSession(sessionId) {
        Router.navigate('qa', { session: sessionId });
    },

    async deleteSession(sessionId) {
        Modal.confirm('确定删除此问答会话？', async () => {
            const result = await Api.delete(`/api/kbqa/sessions/${sessionId}`);
            if (!result || result.error) {
                Toast.error(result?.message || '删除失败');
                return;
            }
            Toast.success('会话已删除');
            this.loadQaHistory();
        });
    },

    // ------------------------------------------------------------------
    // Rebuild
    // ------------------------------------------------------------------

    async rebuild() {
        Modal.confirm('确定重建知识库索引？此操作会清除现有需求/模块/用例索引并重新生成向量。代码和历史问答索引不受影响。', async () => {
            const dot = document.getElementById('kbStatusDot');
            const text = document.getElementById('kbStatusText');
            const meta = document.getElementById('kbStatusMeta');
            const rebuildBtn = document.getElementById('rebuildBtn');

            dot.className = 'kb-status-indicator building';
            text.textContent = '正在构建索引...';
            meta.textContent = '这可能需要几分钟';
            rebuildBtn.disabled = true;

            const result = await Api.post('/api/rag/rebuild');

            if (!result || result.error) {
                Toast.error(result?.message || '重建失败');
                dot.className = 'kb-status-indicator error';
                text.textContent = '构建失败';
                rebuildBtn.disabled = false;
                return;
            }

            Toast.success(`知识库构建完成：${result.chunk_count} 条已索引`);
            this.loadStatus();
        });
    },

    // ------------------------------------------------------------------
    // Helpers
    // ------------------------------------------------------------------

    _getSessionStatus(session) {
        if (session.status === 'feedback_given') {
            return session.feedback === 'positive' ? '已采纳' : '已反馈';
        }
        if (session.status === 'answered') return '已回答';
        return '追问中';
    },

    _formatTime(isoStr) {
        if (!isoStr) return '';
        const d = new Date(isoStr);
        const now = new Date();
        const diff = (now - d) / 1000;
        if (diff < 60) return '刚刚';
        if (diff < 3600) return `${Math.floor(diff / 60)}分钟前`;
        if (diff < 86400) return `${Math.floor(diff / 3600)}小时前`;
        return d.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' });
    },

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    },
};
