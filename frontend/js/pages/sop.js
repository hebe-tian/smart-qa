// SOP management page: list, view/edit, index to KB, template config
const SOPPage = {
    async load() {
        this.loadList();
        this.loadSopTemplate();
    },

    // ------------------------------------------------------------------
    // SOP list
    // ------------------------------------------------------------------

    async loadList() {
        const result = await Api.sopList();
        const tbody = document.getElementById('sopTableBody');
        if (!result || result.error) {
            Toast.error(result?.message || '加载 SOP 列表失败');
            tbody.innerHTML = `<tr><td colspan="5" style="text-align:center;color:var(--text-muted);">加载失败</td></tr>`;
            return;
        }
        this.renderTable(result.sops || []);
    },

    renderTable(sops) {
        const tbody = document.getElementById('sopTableBody');
        if (sops.length === 0) {
            tbody.innerHTML = `
                <tr><td colspan="5" style="text-align: center; padding: var(--space-12); color: var(--text-muted);">
                    暂无 SOP，在问答页解答后点击「生成 SOP」即可创建
                </td></tr>
            `;
            return;
        }

        tbody.innerHTML = sops.map(s => {
            const time = s.created_at ? new Date(s.created_at).toLocaleString('zh-CN') : '-';
            const indexBadge = s.indexed
                ? `<span class="badge badge-success">已索引</span>`
                : `<span class="badge badge-muted">未索引</span>`;
            const sessionCell = s.kb_session_id
                ? `<button class="btn btn-ghost btn-sm" onclick="Router.navigate('qa', {session: ${s.kb_session_id}})">会话 #${s.kb_session_id}</button>`
                : '<span style="color:var(--text-muted);">—</span>';
            return `
                <tr>
                    <td class="font-semibold">${this._escape(s.title)}</td>
                    <td>${sessionCell}</td>
                    <td>${time}</td>
                    <td>${indexBadge}</td>
                    <td>
                        <button class="btn btn-ghost btn-sm" onclick="SOPPage.viewSOP(${s.id})">查看</button>
                        <button class="btn btn-ghost btn-sm" onclick="SOPPage.editSOP(${s.id})">编辑</button>
                        <button class="btn btn-ghost btn-sm" onclick="SOPPage.indexSOP(${s.id})">${s.indexed ? '重建' : '构建知识库'}</button>
                        <button class="btn btn-ghost btn-sm" onclick="SOPPage.deleteSOP(${s.id})">删除</button>
                    </td>
                </tr>
            `;
        }).join('');
    },

    // ------------------------------------------------------------------
    // View / edit
    // ------------------------------------------------------------------

    async viewSOP(sopId) {
        const result = await Api.sopGet(sopId);
        if (!result || result.error) {
            Toast.error(result?.message || '加载 SOP 失败');
            return;
        }
        Modal.show({
            title: 'SOP 详情',
            size: 'large',
            body: `
                <div class="sop-view">
                    <div class="sop-view-title">${this._escape(result.title)}</div>
                    <div class="sop-view-content sop-text">${this._escape(result.content)}</div>
                </div>
            `,
            footer: `
                <button class="btn btn-secondary" onclick="Modal.close()">关闭</button>
                <button class="btn btn-primary" onclick="SOPPage.editSOP(${sopId})">编辑</button>
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
                    <input type="text" class="form-input" id="sopTitle" value="${this._escape(result.title)}">
                </div>
                <div class="form-group">
                    <label class="form-label">内容（纯文本）</label>
                    <textarea class="form-textarea" id="sopContent" rows="16" style="font-family: monospace;">${this._escape(result.content)}</textarea>
                </div>
            `,
            footer: `
                <button class="btn btn-secondary" onclick="Modal.close()">取消</button>
                <button class="btn btn-primary" onclick="SOPPage.saveSOP(${sopId})">保存</button>
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
        this.viewSOP(sopId);
        this.loadList();
    },

    async deleteSOP(sopId) {
        Modal.confirm('确定删除此 SOP？已索引的知识库向量也会一并移除。', async () => {
            const result = await Api.sopDelete(sopId);
            if (!result || result.error) {
                Toast.error(result?.message || '删除失败');
                return;
            }
            Toast.success('SOP 已删除');
            this.loadList();
        });
    },

    // ------------------------------------------------------------------
    // Index to knowledge base
    // ------------------------------------------------------------------

    async indexSOP(sopId) {
        Toast.info('正在构建知识库索引...');
        const result = await Api.sopIndex(sopId);
        if (!result || result.error) {
            Toast.error(result?.message || '构建知识库失败');
            return;
        }
        Toast.success(`已纳入知识库（${result.stored} 条向量）`);
        this.loadList();
    },

    // ------------------------------------------------------------------
    // Template config
    // ------------------------------------------------------------------

    async loadSopTemplate() {
        const result = await Api.sopGetTemplate();
        if (result && !result.error && result.template !== undefined) {
            document.getElementById('sopTemplateInput').value = result.template;
        } else if (result && result.error) {
            Toast.error(result.message || '加载 SOP 模板失败');
        }
    },

    async saveSopTemplate() {
        const content = document.getElementById('sopTemplateInput').value.trim();
        if (!content) {
            Toast.warning('模板内容不能为空');
            return;
        }
        const result = await Api.sopUpdateTemplate(content);
        if (!result || result.error) {
            Toast.error(result?.message || '保存失败');
            return;
        }
        Toast.success('SOP 模板已保存');
    },

    async resetSopTemplate() {
        Modal.confirm('确定将 SOP 模板恢复为默认格式？', async () => {
            const result = await Api.sopResetTemplate();
            if (!result || result.error) {
                Toast.error(result?.message || '恢复失败');
                return;
            }
            document.getElementById('sopTemplateInput').value = result.template;
            Toast.success('已恢复为默认模板');
        });
    },

    // ------------------------------------------------------------------
    // Helpers
    // ------------------------------------------------------------------

    _escape(text) {
        const div = document.createElement('div');
        div.textContent = text == null ? '' : String(text);
        return div.innerHTML;
    },
};
