// Code source management: zip upload, list, delete, index
const CodeSource = {
    _initialized: false,

    init() {
        if (this._initialized) return;
        this._initialized = true;
        this.loadDocuments();
    },

    // ------------------------------------------------------------------
    // ZIP upload
    // ------------------------------------------------------------------

    async uploadZip() {
        const titleInput = document.getElementById('kbCodeTitle');
        const descInput = document.getElementById('kbCodeDesc');

        const title = titleInput.value.trim();
        const description = descInput.value.trim();

        if (!title) {
            Toast.error('请输入文档标题');
            return;
        }

        // Create hidden file picker
        const input = document.createElement('input');
        input.type = 'file';
        input.accept = '.zip';
        input.style.display = 'none';
        input.onchange = async (e) => {
            const file = e.target.files[0];
            input.remove();
            if (!file) return;

            // Front-end size guard
            if (file.size > 50 * 1024 * 1024) {
                Toast.error('文件过大，最大支持 50MB');
                return;
            }

            Toast.show('正在上传并提取代码文件...', 'info');

            const formData = new FormData();
            formData.append('file', file);
            formData.append('title', title);
            formData.append('description', description);

            const result = await Api.upload('/api/code/upload-zip', formData);

            if (!result || result.error) {
                Toast.error(result?.message || '上传失败');
                return;
            }

            Toast.success(`导入完成：${result.created} 个文件，跳过 ${result.skipped} 个非代码文件`);
            titleInput.value = '';
            descInput.value = '';
            this.loadDocuments();
        };
        document.body.appendChild(input);
        input.click();
    },

    // ------------------------------------------------------------------
    // Document list
    // ------------------------------------------------------------------

    async loadDocuments() {
        const result = await Api.get('/api/code/documents');
        const container = document.getElementById('kbCodeDocList');

        if (!result || result.error) {
            container.innerHTML = '<div class="kb-code-doc-empty">加载失败</div>';
            return;
        }

        const docs = result.documents || [];
        if (docs.length === 0) {
            container.innerHTML = '<div class="kb-code-doc-empty">暂无代码文档，请上传 zip 代码包</div>';
            return;
        }

        // Header row
        let html = `
            <div class="kb-code-doc-row kb-code-doc-row-header">
                <div>标题</div>
                <div>语言</div>
                <div>来源</div>
                <div>分块</div>
                <div>状态</div>
                <div>操作</div>
            </div>
        `;

        // Render documents
        html += docs.map(d => this.renderDocRow(d)).join('');
        container.innerHTML = html;
    },

    renderDocRow(doc) {
        const sourceMap = { github: 'GitHub', upload: '上传', local: '本地' };
        const sourceLabel = `<span class="badge badge-info">${sourceMap[doc.source_type] || doc.source_type}</span>`;

        const statusBadge = doc.indexed
            ? `<span class="badge badge-success">已索引</span>`
            : `<span class="badge badge-warning">未索引</span>`;

        const sizeText = doc.content_length
            ? `${(doc.content_length / 1024).toFixed(1)}KB`
            : '-';

        const nameDisplay = doc.file_name;
        const titleBlock = `<div class="kb-code-doc-title">
                ${this.escapeHtml(doc.title)}
                ${doc.description ? `<div style="font-size:11px;color:var(--text-muted);font-weight:400;margin-top:2px">${this.escapeHtml(doc.description)}</div>` : ''}
                <div style="font-size:11px;color:var(--text-muted)">${this.escapeHtml(nameDisplay)} · ${sizeText}</div>
            </div>`;

        return `
            <div class="kb-code-doc-row" data-doc-id="${doc.id}">
                ${titleBlock}
                <div><span class="badge badge-muted">${this.escapeHtml(doc.language)}</span></div>
                <div>${sourceLabel}</div>
                <div>${doc.chunk_count || 0}</div>
                <div>${statusBadge}</div>
                <div class="kb-code-doc-actions">
                    <button onclick="CodeSource.indexDocument(${doc.id})" title="索引此文档">索引</button>
                    <button class="delete" onclick="CodeSource.deleteDocument(${doc.id})" title="删除文档">删除</button>
                </div>
            </div>
        `;
    },

    // ------------------------------------------------------------------
    // Document actions
    // ------------------------------------------------------------------

    async indexDocument(docId) {
        Toast.show('正在索引...', 'info');
        const result = await Api.post(`/api/code/documents/${docId}/index`);

        if (!result || result.error) {
            Toast.error(result?.message || '索引失败');
            return;
        }

        Toast.success(`索引完成：${result.chunk_count} 个分块`);
        this.loadDocuments();
    },

    async deleteDocument(docId) {
        Modal.confirm('确定删除此代码文档？相关向量索引也会被清除。', async () => {
            const result = await Api.delete(`/api/code/documents/${docId}`);
            if (!result || result.error) {
                Toast.error(result?.message || '删除失败');
                return;
            }
            Toast.success('文档已删除');
            this.loadDocuments();
        });
    },

    async rebuildAll() {
        Modal.confirm('确定重建所有代码文档的索引？', async () => {
            Toast.show('正在重建索引...', 'info');
            const result = await Api.post('/api/code/rebuild');

            if (!result || result.error) {
                Toast.error(result?.message || '重建失败');
                return;
            }

            Toast.success(`代码索引重建完成：${result.chunk_count || 0} 个分块`);
            this.loadDocuments();
        });
    },

    // ------------------------------------------------------------------
    // Helpers
    // ------------------------------------------------------------------

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    },
};
