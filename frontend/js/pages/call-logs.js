// Call logs page: list with filters, expandable detail view
const CallLogsPage = {
    currentPage: 1,

    async load() {
        const taskType = document.getElementById('filterType').value;
        const status = document.getElementById('filterStatus').value;

        const params = new URLSearchParams({
            page: this.currentPage,
            per_page: CONFIG.PAGE_SIZE,
        });
        if (taskType) params.append('task_type', taskType);
        if (status) params.append('status', status);

        const result = await Api.get(`/api/call-logs?${params}`);
        if (!result || result.error) {
            Toast.error(result?.message || '加载失败');
            return;
        }

        this.renderTable(result.call_logs || []);
        this.renderPagination(result);
    },

    renderTable(logs) {
        const tbody = document.getElementById('callLogTableBody');
        if (logs.length === 0) {
            tbody.innerHTML = `
                <tr><td colspan="7" style="text-align: center; padding: var(--space-12); color: var(--text-muted);">
                    暂无调用记录
                </td></tr>
            `;
            return;
        }

        tbody.innerHTML = logs.map(log => {
            const statusInfo = CALL_STATUS_MAP[log.status] || CALL_STATUS_MAP['failed'];
            const typeLabel = TASK_TYPE_MAP[log.task_type] || log.task_type;
            const date = new Date(log.created_at).toLocaleString('zh-CN');
            const tokens = log.total_tokens || '-';
            const duration = log.duration_ms ? log.duration_ms + 'ms' : '-';
            return `
                <tr class="table-row-expandable" onclick="CallLogsPage.toggleDetail(${log.id})">
                    <td style="font-size: 12px;">${date}</td>
                    <td>${typeLabel}</td>
                    <td>${log.model_name || '-'}</td>
                    <td><span class="badge ${statusInfo.class}">${statusInfo.label}</span></td>
                    <td>${tokens}</td>
                    <td>${duration}</td>
                    <td><button class="btn btn-ghost btn-sm">详情</button></td>
                </tr>
                <tr id="detail-${log.id}" style="display: none;">
                    <td colspan="7">
                        <div class="call-log-detail" id="detailContent-${log.id}">
                            <span class="spinner"></span> 加载中...
                        </div>
                    </td>
                </tr>
            `;
        }).join('');
    },

    async toggleDetail(logId) {
        const detailRow = document.getElementById(`detail-${logId}`);
        if (!detailRow) return;

        if (detailRow.style.display === 'none') {
            detailRow.style.display = '';
            if (!detailRow.dataset.loaded) {
                const result = await Api.get(`/api/call-logs/${logId}`);
                const contentEl = document.getElementById(`detailContent-${logId}`);
                if (result && !result.error) {
                    contentEl.innerHTML = this.renderDetail(result);
                    detailRow.dataset.loaded = '1';
                } else {
                    contentEl.innerHTML = '<span style="color: var(--danger);">加载失败</span>';
                }
            }
        } else {
            detailRow.style.display = 'none';
        }
    },

    renderDetail(log) {
        let promptMessages = '无';
        try {
            const msgs = JSON.parse(log.prompt_messages_json || '[]');
            promptMessages = msgs.map(m => `[${m.role}] ${m.content}`).join('\n\n');
        } catch (e) {}

        return `
            <div class="call-log-section">
                <div class="call-log-section-title">Prompt消息</div>
                <div class="call-log-content">${promptMessages}</div>
            </div>
            <div class="call-log-section">
                <div class="call-log-section-title">AI响应</div>
                <div class="call-log-content">${log.response_content || '无'}</div>
            </div>
            <div class="call-log-section">
                <div class="call-log-section-title">Token消耗</div>
                <div class="flex gap-6">
                    <span>Prompt: <strong>${log.prompt_tokens || 0}</strong></span>
                    <span>Completion: <strong>${log.completion_tokens || 0}</strong></span>
                    <span>Total: <strong>${log.total_tokens || 0}</strong></span>
                    <span>Duration: <strong>${log.duration_ms || 0}ms</strong></span>
                </div>
            </div>
            ${log.error_message ? `
            <div class="call-log-section">
                <div class="call-log-section-title">错误信息</div>
                <div class="call-log-content" style="color: var(--danger);">${log.error_message}</div>
            </div>
            ` : ''}
        `;
    },

    renderPagination(data) {
        const el = document.getElementById('pagination');
        if (data.pages <= 1) {
            el.innerHTML = '';
            return;
        }

        let html = '';
        if (data.current_page > 1) {
            html += `<button onclick="CallLogsPage.goToPage(${data.current_page - 1})">上一页</button>`;
        }
        for (let i = 1; i <= data.pages; i++) {
            html += `<button class="${i === data.current_page ? 'active' : ''}" onclick="CallLogsPage.goToPage(${i})">${i}</button>`;
        }
        if (data.current_page < data.pages) {
            html += `<button onclick="CallLogsPage.goToPage(${data.current_page + 1})">下一页</button>`;
        }
        el.innerHTML = html;
    },

    goToPage(page) {
        this.currentPage = page;
        this.load();
    },
};
