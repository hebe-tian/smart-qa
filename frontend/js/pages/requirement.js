// Requirement detail page: core logic for QA, generate, tree, regenerate
const RequirementPage = {
    reqId: null,
    requirement: null,
    qaMessages: [],
    treeData: [],

    async init(reqId) {
        this.reqId = reqId;
        if (!reqId) {
            Toast.error('缺少需求ID');
            Router.navigate('dashboard');
            return;
        }
        await this.loadRequirement();
        await this.loadQAMessages();
        await this.loadTree();
        this._setupExportClickOutside();
    },

    _setupExportClickOutside() {
        document.addEventListener('click', (e) => {
            const dropdown = document.getElementById('exportDropdown');
            if (!dropdown || !dropdown.classList.contains('open')) return;
            if (!dropdown.contains(e.target)) {
                dropdown.classList.remove('open');
            }
        });
    },

    async loadRequirement() {
        const result = await Api.get(`/api/requirements/${this.reqId}`);
        if (!result || result.error) {
            Toast.error(result?.message || '加载需求失败');
            Router.navigate('dashboard');
            return;
        }
        this.requirement = result;
        document.getElementById('reqBreadcrumb').textContent = result.title;
        this.renderInfo();
        this.renderActions();
    },

    renderInfo() {
        const req = this.requirement;
        const statusInfo = STATUS_MAP[req.status] || STATUS_MAP['draft'];
        const ptInfo = PROJECT_TYPE_MAP[req.project_type] || PROJECT_TYPE_MAP['production'];
        document.getElementById('reqInfoCard').innerHTML = `
            <div class="flex justify-between items-start">
                <div style="flex: 1;">
                    <div class="flex gap-2 items-center mb-2">
                        <span class="badge ${statusInfo.class}">${statusInfo.label}</span>
                        <span class="badge ${ptInfo.class} project-type-badge">${ptInfo.label}</span>
                        <span style="font-size: 12px; color: var(--text-muted);">#${req.id}</span>
                    </div>
                    <h2 class="requirement-info-title">${req.title}</h2>
                </div>
            </div>
            <div class="requirement-info-content">${req.content}</div>
        `;
    },

    renderActions() {
        const req = this.requirement;
        // Guests are read-only: no action buttons at all
        if (Auth.isGuest()) {
            document.getElementById('actionBar').innerHTML = '';
            return;
        }
        let actions = '';

        if (req.status === 'draft' || req.status === 'analyzing') {
            actions += `<button class="btn btn-primary" onclick="RequirementPage.analyzeRequirement()">AI分析需求</button>`;
        }
        if (req.status === 'qa' || req.status === 'generating' || req.status === 'completed') {
            actions += `<button class="btn btn-primary" onclick="RequirementPage.switchTab('generate', null); RequirementPage.startGenerateModules()">生成模块</button>`;
            const hasModules = this.treeData && this.treeData.length > 0;
            if (hasModules) {
                actions += `<button class="btn btn-secondary" onclick="RequirementPage.switchTab('generate', null); RequirementPage.startGenerateAllCases()">生成用例</button>`;
            }
        }
        actions += `<button class="btn btn-secondary" onclick="RequirementPage.edit(${req.id})">编辑</button>`;

        document.getElementById('actionBar').innerHTML = actions;
    },

    switchTab(tabId, el) {
        document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
        if (el) {
            el.classList.add('active');
        } else {
            const targetTab = document.querySelector(`.tab[onclick*="${tabId}"]`);
            if (targetTab) targetTab.classList.add('active');
        }
        document.getElementById(`tab-${tabId}`).classList.add('active');
    },

    async edit(id) {
        const result = await Api.get(`/api/requirements/${id}`);
        if (!result || result.error) {
            Toast.error(result?.message || '加载需求失败');
            return;
        }
        Modal.show({
            title: '编辑需求',
            body: `
                <div class="form-group">
                    <label class="form-label">需求标题</label>
                    <input type="text" class="form-input" id="reqTitle" value="${result.title || ''}" placeholder="请输入需求标题">
                </div>
                <div class="form-group">
                    <label class="form-label">项目类型</label>
                    <select class="form-select" id="reqProjectType">
                        <option value="production" ${(result.project_type || 'production') === 'production' ? 'selected' : ''}>线上项目</option>
                        <option value="test" ${result.project_type === 'test' ? 'selected' : ''}>测试项目</option>
                    </select>
                    <div class="form-hint">线上项目数据纳入知识库索引，测试项目不纳入</div>
                </div>
                <div class="form-group">
                    <label class="form-label">需求内容</label>
                    <textarea class="form-textarea" id="reqContent" rows="10" placeholder="请输入需求描述，支持多行文本...">${result.content || ''}</textarea>
                    <div class="form-hint">详细的需求描述有助于AI更准确地生成测试用例</div>
                </div>
            `,
            footer: `
                <button class="btn btn-secondary" onclick="Modal.close()">取消</button>
                <button class="btn btn-primary" onclick="RequirementPage.saveEdit(${id})">保存</button>
            `,
        });
    },

    async saveEdit(id) {
        const title = document.getElementById('reqTitle').value.trim();
        const content = document.getElementById('reqContent').value.trim();
        const projectType = document.getElementById('reqProjectType').value;
        if (!title || !content) {
            Toast.warning('标题和内容不能为空');
            return;
        }
        const result = await Api.put(`/api/requirements/${id}`, { title, content, project_type: projectType });
        if (result && !result.error) {
            Toast.success('需求已更新');
            Modal.close();
            await this.loadRequirement();
        } else {
            Toast.error(result?.message || '更新失败');
        }
    },

    // === QA ===
    async loadQAMessages() {
        const result = await Api.get(`/api/qa/${this.reqId}/history`);
        if (result && !result.error) {
            this.qaMessages = result.messages || [];
            this.renderQAMessages();
        }
    },

    renderQAMessages() {
        const container = document.getElementById('chatMessages');
        if (this.qaMessages.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <div class="empty-state-text">点击"AI分析需求"开始多轮问答补全</div>
                </div>
            `;
            return;
        }

        container.innerHTML = this.qaMessages.map(msg => {
            const isAssistant = msg.role === 'assistant';
            const initials = isAssistant ? 'AI' : (Auth.getUser()?.username || 'U').substring(0, 2).toUpperCase();
            return `
                <div class="chat-message ${msg.role}">
                    <div class="chat-avatar">${initials}</div>
                    <div class="chat-bubble">${msg.content}</div>
                </div>
            `;
        }).join('');
        container.scrollTop = container.scrollHeight;
    },

    async analyzeRequirement() {
        const btn = event.target;
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner"></span> 分析中...';

        const result = await Api.post(`/api/qa/analyze/${this.reqId}`);

        btn.disabled = false;
        btn.textContent = 'AI分析需求';

        if (!result || result.error) {
            Toast.error(result?.message || '分析失败');
            return;
        }

        await this.loadQAMessages();
        await this.loadRequirement();

        if (result.need_clarification) {
            Toast.info('AI有' + result.questions.length + '个问题需要确认');
            Analytics.track('qa_round', { requirement_id: this.reqId });
        } else {
            Toast.success('需求已充分，可以开始生成');
        }
    },

    handleQAKeydown(event) {
        if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault();
            this.sendAnswer();
        }
    },

    async sendAnswer() {
        const input = document.getElementById('qaInput');
        const answer = input.value.trim();

        if (!answer) {
            Toast.warning('请输入回答');
            return;
        }

        const btn = document.getElementById('qaSendBtn');
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner"></span>';

        // Add user message immediately
        this.qaMessages.push({ role: 'user', content: answer });
        this.renderQAMessages();
        input.value = '';

        // Show typing indicator
        const container = document.getElementById('chatMessages');
        container.innerHTML += `
            <div class="chat-message assistant" id="typingMsg">
                <div class="chat-avatar">AI</div>
                <div class="chat-bubble">
                    <div class="typing-indicator"><span></span><span></span><span></span></div>
                </div>
            </div>
        `;
        container.scrollTop = container.scrollHeight;

        const result = await Api.post(`/api/qa/answer/${this.reqId}`, { answer });

        document.getElementById('typingMsg')?.remove();
        btn.disabled = false;
        btn.textContent = '发送';

        if (!result || result.error) {
            Toast.error(result?.message || '提交失败');
            return;
        }

        await this.loadQAMessages();
        await this.loadRequirement();

        if (result.context_sufficient) {
            Toast.success('上下文已充分，可以开始生成');
            this.switchTab('generate', null);
        } else if (result.next_questions) {
            Toast.info('AI提出了新的问题');
        }
    },

    // === Generate ===
    async startGenerateModules() {
        const result = await Api.post('/api/generate/modules', { requirement_id: parseInt(this.reqId) });
        if (!result || result.error) {
            Toast.error(result?.message || '启动生成失败');
            return;
        }

        Toast.success('模块生成已启动');
        Analytics.track('generate_start', { requirement_id: this.reqId, type: 'modules' });

        Progress.show('generatePanel', result.task_id, async (taskResult) => {
            Toast.success('模块生成完成');
            Analytics.track('generate_complete', { requirement_id: this.reqId, type: 'modules' });
            await this.loadTree();
            await this.loadRequirement();
        }, (error) => {
            Toast.error('模块生成失败: ' + error);
        });
    },

    async startGenerateAllCases() {
        const result = await Api.post('/api/generate/cases', { requirement_id: parseInt(this.reqId) });
        if (!result || result.error) {
            Toast.error(result?.message || '启动生成失败');
            return;
        }

        Toast.success('用例生成已启动');
        Analytics.track('generate_start', { requirement_id: this.reqId, type: 'cases' });

        Progress.show('generatePanel', result.task_id, async () => {
            Toast.success('用例生成完成');
            Analytics.track('generate_complete', { requirement_id: this.reqId, type: 'cases' });
            await this.loadTree();
            this.switchTab('tree', null);
        }, (error) => {
            Toast.error('用例生成失败: ' + error);
        });
    },

    async startGenerateCases(moduleId, moduleName) {
        const result = await Api.post('/api/generate/cases', { module_id: moduleId });
        if (!result || result.error) {
            Toast.error(result?.message || '启动生成失败');
            return;
        }

        Toast.success(`正在生成"${moduleName}"的用例`);

        Progress.show('generatePanel', result.task_id, async () => {
            Toast.success('用例生成完成');
            await this.loadTree();
        }, (error) => {
            Toast.error('用例生成失败: ' + error);
        });
    },

    // === Tree ===
    async loadTree() {
        const result = await Api.get(`/api/requirements/${this.reqId}`);
        if (!result || result.error) return;

        const modules = result.modules || [];
        // Load cases for each module
        for (const m of modules) {
            const casesResult = await Api.get(`/api/cases/module/${m.id}`);
            if (casesResult && !casesResult.error) {
                m.cases = casesResult.cases || [];
            }
        }
        this.treeData = modules;
        Tree.render('treeContainer', modules, (type, id) => this.selectNode(type, id));
        Tree.expandAll();
        this.renderActions();
    },

    selectNode(type, id) {
        if (type === 'case') {
            this.renderCaseDetail(id);
        }
    },

    async renderCaseDetail(caseId) {
        const result = await Api.get(`/api/cases/${caseId}`);
        if (!result || result.error) return;

        const caseItem = result;
        const priority = PRIORITY_MAP[caseItem.priority] || PRIORITY_MAP['medium'];
        const caseType = CASE_TYPE_MAP[caseItem.case_type] || caseItem.case_type;
        const steps = caseItem.steps || [];

        document.getElementById('detailPanel').innerHTML = `
            <div class="flex justify-between items-start mb-4">
                <h3 class="font-bold" style="font-size: 16px;">${caseItem.title}</h3>
                <div class="flex gap-2">
                    <span class="badge ${priority.class}">${priority.label}</span>
                    <span class="badge badge-info">${caseType}</span>
                </div>
            </div>
            <div class="call-log-section">
                <div class="call-log-section-title">前置条件</div>
                <div class="call-log-content">${caseItem.preconditions || '无'}</div>
            </div>
            <div class="call-log-section">
                <div class="call-log-section-title">测试步骤</div>
                <ol style="padding-left: var(--space-5); line-height: 2;">
                    ${steps.map((s, i) => `<li>${s}</li>`).join('')}
                </ol>
            </div>
            <div class="call-log-section">
                <div class="call-log-section-title">预期结果</div>
                <div class="call-log-content">${caseItem.expected_result || '无'}</div>
            </div>
        `;
    },

    // === Export ===
    toggleExportMenu(event) {
        if (event) event.stopPropagation();
        const dropdown = document.getElementById('exportDropdown');
        if (!dropdown) return;
        const hasData = this.treeData && this.treeData.length > 0;
        if (!hasData) {
            Toast.warning('暂无模块数据，无法导出');
            return;
        }
        dropdown.classList.toggle('open');
    },

    closeExportMenu() {
        const dropdown = document.getElementById('exportDropdown');
        if (dropdown) dropdown.classList.remove('open');
    },

    async exportCases(format) {
        this.closeExportMenu();

        const hasData = this.treeData && this.treeData.length > 0;
        if (!hasData) {
            Toast.warning('暂无模块数据，无法导出');
            return;
        }

        const btn = document.getElementById('exportBtn');
        if (btn) {
            btn.disabled = true;
            btn.style.opacity = '0.6';
        }
        Toast.info('正在生成导出文件...');

        const result = await Api.downloadFile(`/api/export/${this.reqId}?format=${format}`);

        if (btn) {
            btn.disabled = false;
            btn.style.opacity = '';
        }

        if (!result || result.error) {
            Toast.error(result?.message || '导出失败');
            return;
        }

        Toast.success(`已导出: ${result.filename}`);
        Analytics.track('export', { requirement_id: this.reqId, format });
    },

    // === Regenerate ===
    showRegenModal() {
        const selected = Tree.getSelected();
        const totalSelected = selected.cases.length + selected.modules.length;

        if (totalSelected === 0) {
            Toast.warning('请先勾选要重新生成的用例或模块');
            return;
        }

        Modal.show({
            title: '重新生成',
            body: `
                <div class="form-group">
                    <div class="call-log-section-title mb-2">已选择目标</div>
                    <div class="flex gap-2 flex-wrap">
                        ${selected.cases.length ? `<span class="badge badge-info">${selected.cases.length} 个用例</span>` : ''}
                        ${selected.modules.length ? `<span class="badge badge-warning">${selected.modules.length} 个模块</span>` : ''}
                    </div>
                </div>
                <div class="form-group">
                    <label class="form-label">重新生成原因 <span style="color: var(--danger);">*</span></label>
                    <select class="form-select" id="regenReason">
                        <option value="">请选择原因...</option>
                        <option value="覆盖不全">测试场景覆盖不全</option>
                        <option value="描述不清晰">用例描述不清晰</option>
                        <option value="步骤不合理">测试步骤不合理</option>
                        <option value="缺少边界">缺少边界值测试</option>
                        <option value="缺少异常">缺少异常场景</option>
                        <option value="优先级不当">优先级设置不当</option>
                        <option value="其他">其他</option>
                    </select>
                </div>
                <div class="form-group">
                    <label class="form-label">补充描述 <span style="color: var(--danger);">*</span></label>
                    <textarea class="form-textarea" id="regenDesc" rows="5"
                              placeholder="请描述你期望的改进方向，例如：需要增加登录失败的边界测试..."></textarea>
                </div>
            `,
            footer: `
                <button class="btn btn-secondary" onclick="Modal.close()">取消</button>
                <button class="btn btn-primary" onclick="RequirementPage.executeRegen()">确认重新生成</button>
            `,
            size: 'large',
        });
    },

    async executeRegen() {
        const selected = Tree.getSelected();
        const reason = document.getElementById('regenReason').value;
        const description = document.getElementById('regenDesc').value.trim();

        if (!reason) {
            Toast.warning('请选择重新生成原因');
            return;
        }
        if (!description) {
            Toast.warning('请输入补充描述');
            return;
        }

        Modal.close();

        // Send separate requests for cases and modules (they query different tables)
        const requests = [];
        if (selected.cases.length > 0) {
            requests.push(Api.post('/api/regenerate', {
                target_type: 'case',
                target_ids: selected.cases,
                reason, description,
            }));
        }
        if (selected.modules.length > 0) {
            requests.push(Api.post('/api/regenerate', {
                target_type: 'module',
                target_ids: selected.modules,
                reason, description,
            }));
        }

        const results = await Promise.all(requests);
        const failed = results.filter(r => !r || r.error);
        if (failed.length > 0) {
            Toast.error(failed[0]?.message || '重新生成失败');
            return;
        }

        // Collect all task IDs and total count
        const allTaskIds = [];
        let totalCount = 0;
        for (const r of results) {
            totalCount += r.target_count || 0;
            if (r.task_ids) allTaskIds.push(...r.task_ids);
            if (r.task_id) allTaskIds.push(r.task_id);
        }

        Toast.success(`已启动${totalCount}个目标的重新生成`);
        Analytics.track('regenerate', { count: totalCount });

        // Switch to generate tab and poll all tasks
        this.switchTab('generate', null);

        if (allTaskIds.length > 1) {
            for (const taskId of allTaskIds) {
                Api.pollTask(taskId, null, async () => {
                    await this.loadTree();
                }, (error) => {
                    Toast.error('重新生成失败: ' + error);
                });
            }
        } else if (allTaskIds.length === 1) {
            Progress.show('generatePanel', allTaskIds[0], async () => {
                Toast.success('重新生成完成');
                await this.loadTree();
                this.switchTab('tree', null);
            }, (error) => {
                Toast.error('重新生成失败: ' + error);
            });
        }
    },
};
