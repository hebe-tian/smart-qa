// Q&A page: session-based multi-turn Q&A with feedback
const QA = {
    isQuerying: false,
    currentSessionId: null,
    sessionSopMap: {},  // session_id -> sop_id (page-lifetime cache)
    _pollToken: 0,      // invalidates any in-flight pending-answer poll

    init() {
        this.loadStatus();
        this.loadSessions();

        // Priority: URL ?session= param > last session persisted in localStorage
        const sessionId = Router.getParam('session');
        if (sessionId) {
            this.selectSession(parseInt(sessionId));
        } else {
            const storedId = this.getStoredSessionId();
            if (storedId) {
                this.selectSession(storedId);
            }
        }
    },

    // ------------------------------------------------------------------
    // Session persistence (survives full page navigation)
    // ------------------------------------------------------------------

    getStoredSessionId() {
        const raw = localStorage.getItem(CONFIG.QA_SESSION_KEY);
        if (!raw) return null;
        const id = parseInt(raw, 10);
        return isNaN(id) ? null : id;
    },

    saveCurrentSessionId(sessionId) {
        if (sessionId == null) {
            localStorage.removeItem(CONFIG.QA_SESSION_KEY);
        } else {
            localStorage.setItem(CONFIG.QA_SESSION_KEY, String(sessionId));
        }
    },

    // ------------------------------------------------------------------
    // RAG Status
    // ------------------------------------------------------------------

    async loadStatus() {
        const result = await Api.get('/api/rag/status');
        const dot = document.getElementById('kbStatusDot');
        const text = document.getElementById('kbStatusText');
        const meta = document.getElementById('kbStatusMeta');
        const welcomeDesc = document.getElementById('kbWelcomeDesc');
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
            welcomeDesc.textContent = '请先在 AI配置 页面设置 Embedding 模型，再重建知识库索引。';
            return;
        }

        if (!result.is_ready) {
            dot.className = 'kb-status-indicator warning';
            text.textContent = '知识库未构建';
            meta.textContent = '点击"重建索引"开始';
            rebuildBtn.disabled = false;
            welcomeDesc.textContent = '知识库尚未构建，点击右上角"重建索引"按钮生成向量索引后即可提问。';
            return;
        }

        dot.className = 'kb-status-indicator ready';
        text.textContent = '知识库就绪';
        const lastBuilt = result.last_built_at
            ? new Date(result.last_built_at).toLocaleString('zh-CN')
            : '';

        let breakdownText = '';
        if (result.by_project_type) {
            const pt = result.by_project_type;
            const prod = pt['production'] || {total: 0};
            const test = pt['test'] || {total: 0};
            const parts = [];
            parts.push(`线上 ${prod.total} 条`);
            if (test.total > 0) parts.push(`测试 ${test.total} 条`);
            breakdownText = ` · ${parts.join(' / ')}`;
        }

        meta.textContent = `${result.chunk_count} 条已索引${breakdownText}${lastBuilt ? ' · ' + lastBuilt : ''}`;
        rebuildBtn.disabled = false;
        welcomeDesc.textContent = '基于需求文档、业务代码和历史问答，用自然语言提问。AI 会自主判断是否需要追问，给出解答后你可以反馈准确度。';
    },

    // ------------------------------------------------------------------
    // Session management
    // ------------------------------------------------------------------

    async loadSessions() {
        const result = await Api.get('/api/kbqa/sessions');
        const container = document.getElementById('kbSessionList');

        if (!result || result.error) {
            container.innerHTML = '<div class="kb-session-empty">加载失败</div>';
            return;
        }

        const sessions = result.sessions || [];
        if (sessions.length === 0) {
            container.innerHTML = '<div class="kb-session-empty">暂无问答会话<br><span style="font-size:11px;color:var(--text-muted)">点击上方按钮开始</span></div>';
            return;
        }

        container.innerHTML = sessions.map(s => this.renderSessionCard(s)).join('');

        // Highlight current session
        if (this.currentSessionId) {
            const card = container.querySelector(`[data-session-id="${this.currentSessionId}"]`);
            if (card) card.classList.add('active');
        }
    },

    renderSessionCard(session) {
        const isActive = session.id === this.currentSessionId;
        const statusLabel = this._getSessionStatus(session);
        const timeStr = this._formatTime(session.updated_at || session.created_at);
        const sopBadge = session.sop_id
            ? `<span class="kb-session-sop-badge user-only" title="查看 SOP" onclick="event.stopPropagation(); QA.viewSOP(${session.sop_id})">SOP</span>`
            : '';

        return `
            <div class="kb-session-card ${isActive ? 'active' : ''}" data-session-id="${session.id}"
                 onclick="QA.selectSession(${session.id})">
                <div class="kb-session-card-title">${this.escapeHtml(session.title)}</div>
                <div class="kb-session-card-meta">
                    <span class="kb-session-card-status ${session.status}">${statusLabel}</span>
                    ${sopBadge}
                    <span class="kb-session-card-time">${timeStr}</span>
                </div>
                <button class="kb-session-card-delete user-only" onclick="QA.deleteSession(event, ${session.id})">×</button>
            </div>
        `;
    },

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

    async newSession() {
        const result = await Api.post('/api/kbqa/sessions', {});
        if (!result || result.error) {
            Toast.error(result?.message || '创建会话失败');
            return;
        }
        this._pollToken++;  // cancel any pending poll
        this.currentSessionId = result.id;
        this.saveCurrentSessionId(result.id);
        await this.loadSessions();
        this.clearMessages();
        this.showWelcome();
        document.getElementById('kbInput').focus();
    },

    async selectSession(sessionId) {
        if (this.isQuerying) return;
        this._pollToken++;  // cancel any pending poll
        this.currentSessionId = sessionId;
        this.saveCurrentSessionId(sessionId);

        // Update active state in list
        document.querySelectorAll('.kb-session-card').forEach(c => {
            c.classList.toggle('active', parseInt(c.dataset.sessionId) === sessionId);
        });

        // Load session detail
        const result = await Api.get(`/api/kbqa/sessions/${sessionId}`);
        if (!result || result.error) {
            Toast.error(result?.message || '加载会话失败');
            return;
        }

        this.sessionSopMap[sessionId] = result.sop_id || null;
        this.clearMessages();
        const messages = result.messages || [];
        if (messages.length === 0) {
            this.showWelcome();
        } else {
            this.hideWelcome();
            messages.forEach(msg => {
                if (msg.role === 'user') {
                    this.renderUserMessage(msg.content);
                } else {
                    this.renderAIMessage(msg.content, msg.message_type, msg.sources, msg.round, sessionId, msg.id);
                }
            });
            this.scrollToBottom();
        }

        // If the last message is from the user, the previous AI turn may still
        // be generating (e.g. the page was navigated away mid-response). Poll
        // until the assistant reply lands, then re-render.
        const last = messages[messages.length - 1];
        if (last && last.role === 'user') {
            this.pollForPendingAnswer(sessionId);
        }

        document.getElementById('kbInput').focus();
    },

    // Poll until the in-flight AI reply for a session lands (used when the page
    // was navigated away while the assistant was still generating).
    async pollForPendingAnswer(sessionId) {
        const token = ++this._pollToken;
        this.showTyping();
        const MAX_ATTEMPTS = 30;   // 30 * 2s = 60s
        const INTERVAL = 2000;

        for (let attempt = 0; attempt < MAX_ATTEMPTS; attempt++) {
            await new Promise(res => setTimeout(res, INTERVAL));

            // Superseded by a new poll, session switch, or an outgoing send —
            // the cancelling flow already cleans up the typing placeholder.
            if (token !== this._pollToken || this.currentSessionId !== sessionId || this.isQuerying) {
                return;
            }

            const result = await Api.get(`/api/kbqa/sessions/${sessionId}`);
            if (!result || result.error) continue;

            const msgs = result.messages || [];
            const last = msgs[msgs.length - 1];
            if (last && last.role === 'assistant') {
                this.hideTyping();
                this.sessionSopMap[sessionId] = result.sop_id || null;
                this.clearMessages();
                msgs.forEach(msg => {
                    if (msg.role === 'user') {
                        this.renderUserMessage(msg.content);
                    } else {
                        this.renderAIMessage(msg.content, msg.message_type, msg.sources, msg.round, sessionId, msg.id);
                    }
                });
                this.scrollToBottom();
                this.loadSessions();
                return;
            }
        }

        // Timed out without a reply; leave the user message and hide placeholder
        this.hideTyping();
    },

    async deleteSession(event, sessionId) {
        event.stopPropagation();
        Modal.confirm('确定删除此问答会话？', async () => {
            const result = await Api.delete(`/api/kbqa/sessions/${sessionId}`);
            if (!result || result.error) {
                Toast.error(result?.message || '删除失败');
                return;
            }
            if (this.currentSessionId === sessionId) {
                this._pollToken++;  // cancel any pending poll
                this.currentSessionId = null;
                this.saveCurrentSessionId(null);
                this.clearMessages();
                this.showWelcome();
            }
            this.loadSessions();
            Toast.success('会话已删除');
        });
    },

    // ------------------------------------------------------------------
    // Messaging
    // ------------------------------------------------------------------

    handleKeydown(event) {
        if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault();
            this.send();
        }
    },

    autoResize(textarea) {
        textarea.style.height = 'auto';
        textarea.style.height = Math.min(textarea.scrollHeight, 120) + 'px';
    },

    quickAsk(question) {
        const input = document.getElementById('kbInput');
        input.value = question;
        this.autoResize(input);
        this.send();
    },

    async send(forceAnswer = false) {
        if (this.isQuerying) return;
        this._pollToken++;   // cancel any pending poll
        this.hideTyping();   // clear poll's typing placeholder if present

        const input = document.getElementById('kbInput');
        const question = input.value.trim();
        if (!question) return;

        // Auto-create session if none selected
        if (!this.currentSessionId) {
            const session = await Api.post('/api/kbqa/sessions', {});
            if (!session || session.error) {
                Toast.error(session?.message || '创建会话失败');
                return;
            }
            this.currentSessionId = session.id;
            this.saveCurrentSessionId(session.id);
            await this.loadSessions();
        }

        this.hideWelcome();
        this.renderUserMessage(question);

        input.value = '';
        this.autoResize(input);

        this.isQuerying = true;
        document.getElementById('sendBtn').disabled = true;
        document.getElementById('forceAnswerBtn').disabled = true;
        this.showTyping();

        try {
            const result = await Api.post(
                `/api/kbqa/sessions/${this.currentSessionId}/messages`,
                { content: question, force_answer: forceAnswer }
            );
            this.hideTyping();

            if (!result || result.error) {
                this.renderAIMessage(result?.message || '查询失败，请稍后重试', 'answer', []);
            } else {
                this.renderAIMessage(
                    result.content || '(空回答)',
                    result.message_type || 'answer',
                    result.sources || [],
                    result.round,
                    this.currentSessionId,
                    result.message_id
                );
            }

            // Refresh session list to update title/status
            this.loadSessions();
        } catch (e) {
            this.hideTyping();
            this.renderAIMessage('网络错误，请稍后重试', 'answer', []);
        } finally {
            this.isQuerying = false;
            document.getElementById('sendBtn').disabled = false;
            document.getElementById('forceAnswerBtn').disabled = false;
            input.focus();
        }
    },

    // ------------------------------------------------------------------
    // Feedback
    // ------------------------------------------------------------------

    async submitFeedback(sessionId, feedback, btnEl) {
        const comment = null;

        const result = await Api.post(
            `/api/kbqa/sessions/${sessionId}/feedback`,
            { feedback, comment }
        );

        if (!result || result.error) {
            Toast.error(result?.message || '反馈失败');
            return;
        }

        // Update feedback buttons UI
        const feedbackArea = btnEl.closest('.kb-feedback');
        feedbackArea.querySelectorAll('.kb-feedback-btn').forEach(b => {
            b.classList.remove('selected', 'positive', 'negative');
        });
        btnEl.classList.add('selected', feedback);

        if (feedback === 'positive') {
            const msg = result.indexed
                ? '已标记为准确，问答已纳入知识库索引'
                : '已标记为准确';
            Toast.success(msg);
            const badge = feedbackArea.querySelector('.kb-feedback-indexed');
            if (badge && result.indexed) badge.style.display = 'inline-flex';
        } else {
            const msg = result.indexed
                ? '已标记为不准确，作为错误参考记入知识库'
                : '已标记为不准确';
            Toast.show(msg, 'warning');
            if (result.indexed) {
                const badge = feedbackArea.querySelector('.kb-feedback-negative-badge');
                if (badge) badge.style.display = 'inline-flex';
            }
        }

        // Refresh session list to update status
        this.loadSessions();
    },

    // ------------------------------------------------------------------
    // SOP generation & viewing
    // ------------------------------------------------------------------

    async generateSOP(sessionId, messageId, btnEl) {
        Modal.confirm('是否将本次解答生成 SOP（标准操作程序）？', async () => {
            btnEl.disabled = true;
            btnEl.innerHTML = '<span>生成中...</span>';
            Toast.info('正在生成 SOP，请稍候...');

            const result = await Api.sopGenerate(sessionId, messageId);

            if (!result || result.error) {
                btnEl.disabled = false;
                btnEl.innerHTML = '<span>生成 SOP</span>';
                Toast.error(result?.message || 'SOP 生成失败');
                return;
            }

            const sop = result.sop;
            this.sessionSopMap[sessionId] = sop.id;
            btnEl.outerHTML = `<button class="kb-feedback-btn kb-sop-btn" onclick="QA.viewSOP(${sop.id})">查看 SOP</button>`;
            Toast.success('SOP 已生成');
            this.loadSessions();
            this.showSOPModal(sop);
        });
    },

    async viewSOP(sopId) {
        const result = await Api.sopGet(sopId);
        if (!result || result.error) {
            Toast.error(result?.message || '加载 SOP 失败');
            return;
        }
        this.showSOPModal(result);
    },

    showSOPModal(sop) {
        Modal.show({
            title: 'SOP 详情',
            size: 'large',
            body: `
                <div class="sop-view">
                    <div class="sop-view-title">${this.escapeHtml(sop.title)}</div>
                    <div class="sop-view-content sop-text">${this.escapeHtml(sop.content)}</div>
                </div>
            `,
            footer: `
                <button class="btn btn-secondary" onclick="Modal.close()">关闭</button>
                <button class="btn btn-primary" onclick="QA.editSOP(${sop.id})">编辑</button>
            `,
        });
    },

    async editSOP(sopId) {
        const result = await Api.sopGet(sopId);
        if (!result || result.error) {
            Toast.error(result?.message || '加载 SOP 失败');
            return;
        }

        Modal.show({
            title: '编辑 SOP',
            size: 'large',
            body: `
                <div class="form-group">
                    <label class="form-label">标题</label>
                    <input type="text" class="form-input" id="sopTitle" value="${this.escapeHtml(result.title)}">
                </div>
                <div class="form-group">
                    <label class="form-label">内容（纯文本）</label>
                    <textarea class="form-input" id="sopContent" rows="16" style="font-family: monospace;">${this.escapeHtml(result.content)}</textarea>
                </div>
            `,
            footer: `
                <button class="btn btn-secondary" onclick="Modal.close()">取消</button>
                <button class="btn btn-primary" onclick="QA.saveSOP(${sopId})">保存</button>
            `,
        });
    },

    async saveSOP(sopId) {
        const title = document.getElementById('sopTitle').value.trim();
        const content = document.getElementById('sopContent').value.trim();
        if (!title || !content) {
            Toast.warning('标题和内容不能为空');
            return;
        }

        const result = await Api.sopUpdate(sopId, { title, content });
        if (!result || result.error) {
            Toast.error(result?.message || '保存失败');
            return;
        }

        Toast.success('SOP 已保存');
        Modal.close();
        this.showSOPModal(result);
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
    // Message rendering
    // ------------------------------------------------------------------

    clearMessages() {
        const container = document.getElementById('chatMessages');
        container.innerHTML = '';
    },

    showWelcome() {
        const container = document.getElementById('chatMessages');
        container.innerHTML = `
            <div class="kb-welcome" id="kbWelcome">
                <div class="kb-welcome-icon">[?]</div>
                <div class="kb-welcome-title">智能问答</div>
                <div class="kb-welcome-desc" id="kbWelcomeDesc">
                    基于需求文档、业务代码和历史问答，用自然语言提问。AI 会自主判断是否需要追问，给出解答后你可以反馈准确度。
                </div>
                <div class="kb-suggestions" id="kbSuggestions">
                    <div class="kb-suggestion-item" onclick="QA.quickAsk('登录功能有哪些测试用例？')">登录功能有哪些测试用例？</div>
                    <div class="kb-suggestion-item" onclick="QA.quickAsk('边界测试用例一般覆盖哪些场景？')">边界测试用例一般覆盖哪些场景？</div>
                    <div class="kb-suggestion-item" onclick="QA.quickAsk('异常测试怎么设计？')">异常测试怎么设计？</div>
                </div>
            </div>
        `;
    },

    hideWelcome() {
        const welcome = document.getElementById('kbWelcome');
        if (welcome) welcome.style.display = 'none';
    },

    renderUserMessage(text) {
        const container = document.getElementById('chatMessages');
        const div = document.createElement('div');
        div.className = 'chat-message user';
        div.innerHTML = `
            <div class="chat-bubble">${this.escapeHtml(text)}</div>
            <div class="chat-avatar">ME</div>
        `;
        container.appendChild(div);
        this.scrollToBottom();
    },

    renderAIMessage(content, type, sources, round, sessionId, messageId = null) {
        const container = document.getElementById('chatMessages');
        const div = document.createElement('div');
        const isClarification = type === 'clarification';
        div.className = `chat-message assistant ${isClarification ? 'clarification' : 'answer'}`;

        let sourcesHtml = '';
        if (sources && sources.length > 0) {
            sourcesHtml = `
                <div class="kb-sources">
                    <div class="kb-sources-header" onclick="this.parentElement.classList.toggle('collapsed')">
                        <span>引用来源 (${sources.length})</span>
                        <span class="kb-sources-toggle">[+]</span>
                    </div>
                    <div class="kb-sources-list">
                        ${sources.map((s, i) => this.renderSourceCard(s, i)).join('')}
                    </div>
                </div>
            `;
        }

        // Feedback buttons only for answer type (hidden for read-only guests)
        let feedbackHtml = '';
        if (!isClarification && sessionId && !Auth.isGuest()) {
            // SOP generate/view button (only for answer messages that have a session)
            let sopButtonHtml = '';
            if (sessionId) {
                const existingSopId = this.sessionSopMap[sessionId];
                sopButtonHtml = existingSopId
                    ? `<button class="kb-feedback-btn kb-sop-btn" onclick="QA.viewSOP(${existingSopId})">查看 SOP</button>`
                    : `<button class="kb-feedback-btn kb-sop-btn" onclick="QA.generateSOP(${sessionId}, ${messageId || 'null'}, this)">生成 SOP</button>`;
            }

            feedbackHtml = `
                <div class="kb-feedback" data-session-id="${sessionId}">
                    <span class="kb-feedback-label">回答准确吗？</span>
                    <button class="kb-feedback-btn positive" onclick="QA.submitFeedback(${sessionId}, 'positive', this)">
                        <span>✓ 准确</span>
                    </button>
                    <button class="kb-feedback-btn negative" onclick="QA.submitFeedback(${sessionId}, 'negative', this)">
                        <span>✗ 不准确</span>
                    </button>
                    <span class="kb-feedback-indexed" style="display:none">
                        <span class="badge badge-success">已纳入知识库</span>
                    </span>
                    <span class="kb-feedback-negative-badge" style="display:none">
                        <span class="badge badge-warning">已记为错误参考</span>
                    </span>
                    ${sopButtonHtml}
                </div>
            `;
        }

        // Round badge for clarification
        let roundBadge = '';
        if (isClarification && round) {
            roundBadge = `<span class="kb-round-badge">追问 ${round}</span>`;
        }

        div.innerHTML = `
            <div class="chat-avatar">AI</div>
            <div class="chat-bubble ${isClarification ? 'clarification-bubble' : ''}">
                ${roundBadge}
                <div class="kb-answer">${this.formatAnswer(content)}</div>
                ${sourcesHtml}
                ${feedbackHtml}
            </div>
        `;
        container.appendChild(div);
        this.scrollToBottom();
    },

    renderSourceCard(source, index) {
        const typeLabel = CHUNK_TYPE_MAP[source.chunk_type] || source.chunk_type;
        const score = Math.round((source.score || 0) * 100);
        const meta = source.metadata || {};
        let metaParts = [];
        if (meta.priority) metaParts.push(`${PRIORITY_MAP[meta.priority]?.label || meta.priority}`);
        if (meta.case_type) metaParts.push(`${CASE_TYPE_MAP[meta.case_type] || meta.case_type}`);
        if (meta.session_title) metaParts.push(meta.session_title);
        if (meta.file_name) metaParts.push(meta.file_name);

        return `
            <div class="kb-source-card">
                <div class="kb-source-header">
                    <span class="badge badge-info">${typeLabel}</span>
                    <span class="kb-source-score">相似度 ${score}%</span>
                </div>
                <div class="kb-source-text">${this.escapeHtml(source.text)}</div>
                ${metaParts.length ? `<div class="kb-source-meta">${metaParts.join(' · ')}</div>` : ''}
            </div>
        `;
    },

    // ------------------------------------------------------------------
    // Typing indicator
    // ------------------------------------------------------------------

    showTyping() {
        const container = document.getElementById('chatMessages');
        const div = document.createElement('div');
        div.className = 'chat-message assistant';
        div.id = 'typingIndicator';
        div.innerHTML = `
            <div class="chat-avatar">AI</div>
            <div class="chat-bubble">
                <div class="typing-indicator">
                    <span></span><span></span><span></span>
                </div>
            </div>
        `;
        container.appendChild(div);
        this.scrollToBottom();
    },

    hideTyping() {
        const el = document.getElementById('typingIndicator');
        if (el) el.remove();
    },

    // ------------------------------------------------------------------
    // Helpers
    // ------------------------------------------------------------------

    scrollToBottom() {
        const container = document.getElementById('chatMessages');
        container.scrollTop = container.scrollHeight;
    },

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    },

    formatAnswer(text) {
        let html = this.escapeHtml(text);
        html = html.replace(/```(\w*)\n?([\s\S]*?)```/g, (m, lang, code) => {
            return `<pre class="kb-code-block"><code>${code.trim()}</code></pre>`;
        });
        html = html.replace(/`([^`]+)`/g, '<code class="kb-code-inline">$1</code>');
        html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
        html = html.replace(/\n/g, '<br>');
        return html;
    },
};
