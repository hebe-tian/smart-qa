// Dashboard page: requirement list, search, filter, create/edit/delete
const Dashboard = {
    currentPage: 1,
    searchTimer: null,

    async load() {
        const search = document.getElementById('searchInput')?.value || '';
        const status = document.getElementById('statusFilter')?.value || '';
        const projectType = document.getElementById('projectTypeFilter')?.value || '';

        const params = new URLSearchParams({
            page: this.currentPage,
            per_page: CONFIG.PAGE_SIZE,
        });
        if (search) params.append('search', search);
        if (status) params.append('status', status);
        if (projectType) params.append('project_type', projectType);

        const result = await Api.get(`/api/requirements?${params}`);
        if (!result || result.error) {
            Toast.error(result?.message || '加载失败');
            return;
        }

        this.renderList(result.requirements);
        this.renderPagination(result);
    },

    renderList(requirements) {
        const listEl = document.getElementById('requirementList');
        const emptyEl = document.getElementById('emptyState');

        if (!requirements || requirements.length === 0) {
            listEl.innerHTML = '';
            emptyEl.style.display = 'block';
            return;
        }

        emptyEl.style.display = 'none';
        listEl.innerHTML = requirements.map(req => {
            const statusInfo = STATUS_MAP[req.status] || STATUS_MAP['draft'];
            const ptInfo = PROJECT_TYPE_MAP[req.project_type] || PROJECT_TYPE_MAP['production'];
            const date = new Date(req.created_at).toLocaleString('zh-CN');
            const content = (req.content || '').substring(0, 150);
            return `
                <div class="requirement-card card-hover" onclick="Dashboard.open(${req.id})">
                    <div class="flex justify-between items-start mb-2">
                        <div class="flex gap-2">
                            <span class="badge ${statusInfo.class}">${statusInfo.label}</span>
                            <span class="badge ${ptInfo.class} project-type-badge">${ptInfo.label}</span>
                        </div>
                        <span class="font-normal" style="font-size: 11px; color: var(--text-muted);">#${req.id}</span>
                    </div>
                    <h3 class="requirement-card-title">${req.title}</h3>
                    <p class="requirement-card-content">${content}</p>
                    <div class="requirement-card-meta">
                        <span>${date}</span>
                        <span>|</span>
                        <span>${req.module_count || 0} 模块</span>
                        <span>${req.case_count || 0} 用例</span>
                    </div>
                    <div class="flex gap-2 mt-3 user-only" style="position: absolute; right: var(--space-5); bottom: var(--space-5);">
                        <button class="btn btn-ghost btn-sm" onclick="event.stopPropagation(); Dashboard.edit(${req.id})">编辑</button>
                        <button class="btn btn-ghost btn-sm" onclick="event.stopPropagation(); Dashboard.deleteReq(${req.id})">删除</button>
                    </div>
                </div>
            `;
        }).join('');
    },

    renderPagination(data) {
        const el = document.getElementById('pagination');
        if (data.pages <= 1) {
            el.innerHTML = '';
            return;
        }

        let html = '';
        if (data.current_page > 1) {
            html += `<button onclick="Dashboard.goToPage(${data.current_page - 1})">上一页</button>`;
        }
        for (let i = 1; i <= data.pages; i++) {
            html += `<button class="${i === data.current_page ? 'active' : ''}" onclick="Dashboard.goToPage(${i})">${i}</button>`;
        }
        if (data.current_page < data.pages) {
            html += `<button onclick="Dashboard.goToPage(${data.current_page + 1})">下一页</button>`;
        }
        el.innerHTML = html;
    },

    goToPage(page) {
        this.currentPage = page;
        this.load();
    },

    handleSearch() {
        clearTimeout(this.searchTimer);
        this.searchTimer = setTimeout(() => {
            this.currentPage = 1;
            this.load();
        }, 300);
    },

    open(id) {
        Router.navigate('requirement', { id });
    },

    async edit(id) {
        const result = await Api.get(`/api/requirements/${id}`);
        if (result && !result.error) {
            this.showCreateModal(result);
        }
    },

    showCreateModal(existing = null) {
        const isEdit = !!existing;
        const title = isEdit ? '编辑需求' : '新建需求';
        const data = existing || { title: '', content: '', project_type: 'production' };

        Modal.show({
            title,
            body: `
                <div class="form-group">
                    <label class="form-label">需求标题</label>
                    <input type="text" class="form-input" id="reqTitle" value="${data.title || ''}" placeholder="请输入需求标题">
                </div>
                <div class="form-group">
                    <label class="form-label">项目类型</label>
                    <select class="form-select" id="reqProjectType">
                        <option value="production" ${(data.project_type || 'production') === 'production' ? 'selected' : ''}>线上项目</option>
                        <option value="test" ${data.project_type === 'test' ? 'selected' : ''}>测试项目</option>
                    </select>
                    <div class="form-hint">线上项目数据纳入知识库索引，测试项目不纳入</div>
                </div>
                <div class="form-group">
                    <label class="form-label">需求内容</label>
                    <textarea class="form-textarea" id="reqContent" rows="10" placeholder="请输入需求描述，支持多行文本...">${data.content || ''}</textarea>
                    <div class="form-hint">详细的需求描述有助于AI更准确地生成测试用例</div>
                </div>
            `,
            footer: `
                <button class="btn btn-secondary" onclick="Modal.close()">取消</button>
                <button class="btn btn-primary" onclick="Dashboard.save(${isEdit ? data.id : 'null'})">保存</button>
            `,
        });
    },

    uploadDocument() {
        // Trigger a hidden file picker for document upload (PDF/Word/Markdown)
        const input = document.createElement('input');
        input.type = 'file';
        input.accept = '.pdf,.docx,.md,.markdown,.txt';
        input.style.display = 'none';
        input.onchange = (e) => {
            const file = e.target.files[0];
            input.remove();
            if (file) this._processDocumentUpload(file);
        };
        document.body.appendChild(input);
        input.click();
    },

    async _processDocumentUpload(file) {
        // Front-end size guard (10MB, matches backend limit)
        if (file.size > 10 * 1024 * 1024) {
            Toast.error('文件过大，最大支持 10MB');
            return;
        }

        const sizeKB = (file.size / 1024).toFixed(1);
        // Show a loading modal during parse + AI extraction
        Modal.show({
            title: '上传文档解析',
            body: `
                <div style="display:flex;flex-direction:column;align-items:center;gap:16px;padding:24px 0;">
                    <div class="spinner spinner-lg"></div>
                    <p style="font-size:14px;color:var(--text-primary);margin:0;">正在解析文档并 AI 提取需求...</p>
                    <p style="font-size:12px;color:var(--text-muted);margin:0;">${file.name} (${sizeKB} KB)</p>
                </div>
            `,
        });

        const formData = new FormData();
        formData.append('file', file);

        const result = await Api.upload('/api/requirements/upload', formData);

        if (!result || result.error) {
            Modal.close();
            Toast.error(result?.message || '文档解析失败');
            return;
        }

        // Fill the create modal with extracted title + content for user review/edit
        Modal.close();
        Toast.success('文档解析完成，请确认并编辑需求内容');
        Analytics.track('document_upload', { filename: file.name });
        this.showCreateModal({
            title: result.title || '',
            content: result.content || '',
            project_type: 'production',
        });
    },

    async save(id) {
        const title = document.getElementById('reqTitle').value.trim();
        const content = document.getElementById('reqContent').value.trim();
        const projectType = document.getElementById('reqProjectType').value;

        if (!title || !content) {
            Toast.warning('标题和内容不能为空');
            return;
        }

        if (id) {
            const result = await Api.put(`/api/requirements/${id}`, { title, content, project_type: projectType });
            if (result && !result.error) {
                Toast.success('需求已更新');
                Modal.close();
                this.load();
            } else {
                Toast.error(result?.message || '更新失败');
            }
        } else {
            const result = await Api.post('/api/requirements', { title, content, project_type: projectType });
            if (result && !result.error) {
                Toast.success('需求已创建');
                Analytics.track('requirement_create', { requirement_id: result.id });
                Modal.close();
                this.load();
            } else {
                Toast.error(result?.message || '创建失败');
            }
        }
    },

    async deleteReq(id) {
        Modal.confirm('确定删除此需求及其所有模块和用例？', async () => {
            const result = await Api.delete(`/api/requirements/${id}`);
            if (result && !result.error) {
                Toast.success('需求已删除');
                this.load();
            } else {
                Toast.error(result?.message || '删除失败');
            }
        });
    },
};
