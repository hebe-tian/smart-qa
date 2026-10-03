// AI config page: list, create, edit, delete, test connection
const AIConfigPage = {
    async load() {
        const result = await Api.get('/api/ai-config');
        if (!result || result.error) {
            Toast.error(result?.message || '加载失败');
            return;
        }
        this.renderTable(result.configs || []);
    },


    renderTable(configs) {
        const tbody = document.getElementById('configTableBody');
        if (configs.length === 0) {
            tbody.innerHTML = `
                <tr><td colspan="8" style="text-align: center; padding: var(--space-12); color: var(--text-muted);">
                    暂无AI模型配置，点击"添加模型"开始
                </td></tr>
            `;
            return;
        }

        tbody.innerHTML = configs.map(c => {
            const statusBadge = c.is_active
                ? `<span class="badge badge-success">已启用</span>`
                : `<span class="badge badge-muted">已禁用</span>`;
            const connBadge = c.connection_status === 'connected'
                ? `<span class="badge badge-success">已连接</span>`
                : c.connection_status === 'failed'
                ? `<span class="badge badge-danger">连接失败</span>`
                : `<span class="badge badge-muted">未测试</span>`;
            const typeLabel = {chat: '对话', embedding: '向量', both: '综合'}[c.config_type] || '综合';
            const typeBadge = `<span class="badge badge-${c.config_type === 'embedding' ? 'info' : c.config_type === 'chat' ? 'success' : 'primary'}">${typeLabel}</span>`;
            const embBadge = c.embedding_model
                ? `<span class="badge badge-info">${c.embedding_model}</span>`
                : `<span class="badge badge-muted">未配置</span>`;
            const isEmb = c.config_type === 'embedding';
            const modelDisplay = isEmb || !c.model || c.model === 'n/a'
                ? '<span style="color: var(--text-muted);">—</span>'
                : c.model;
            return `
                <tr>
                    <td class="font-semibold">${c.name}</td>
                    <td>${typeBadge}</td>
                    <td style="max-width: 200px;" class="truncate">${c.base_url}</td>
                    <td>${modelDisplay}</td>
                    <td>${embBadge}</td>
                    <td>${statusBadge}<br><span style="margin-top: 4px; display: inline-block;">${connBadge}</span></td>
                    <td>${c.is_default ? '<span class="badge badge-info">默认</span>' : ''}</td>
                    <td>
                        <button class="btn btn-ghost btn-sm" onclick="AIConfigPage.testConnection(${c.id})">测试</button>
                        <button class="btn btn-ghost btn-sm" onclick="AIConfigPage.showFormModal(${c.id})">编辑</button>
                        <button class="btn btn-ghost btn-sm" onclick="AIConfigPage.delete(${c.id})">删除</button>
                    </td>
                </tr>
            `;
        }).join('');
    },

    async showFormModal(configId = null) {
        let config = null;
        if (configId) {
            const result = await Api.get(`/api/ai-config/${configId}`);
            if (!result || result.error) {
                Toast.error(result?.message || '加载配置失败');
                return;
            }
            config = result;
        }

        const title = configId ? '编辑AI模型' : '添加AI模型';
        const data = config || { name: '', base_url: 'https://api.openai.com/v1', api_key: '', model: 'gpt-4o', temperature: 0.7, max_tokens: 4096, embedding_model: '', config_type: 'both', is_default: false, is_active: true };

        Modal.show({
            title,
            body: `
                <div class="form-group">
                    <label class="form-label">名称</label>
                    <input type="text" class="form-input" id="cfgName" value="${data.name || ''}" placeholder="如：OpenAI GPT-4o">
                </div>
                <div class="form-group">
                    <label class="form-label">配置类型</label>
                    <select class="form-input" id="cfgConfigType" onchange="AIConfigPage.onTypeChange()">
                        <option value="both" ${(data.config_type || 'both') === 'both' ? 'selected' : ''}>综合（对话+向量）</option>
                        <option value="chat" ${(data.config_type || '') === 'chat' ? 'selected' : ''}>对话模型</option>
                        <option value="embedding" ${(data.config_type || '') === 'embedding' ? 'selected' : ''}>Embedding 向量模型</option>
                    </select>
                    <div class="form-hint">对话模型用于AI分析/生成；向量模型用于知识库RAG。不同类型可使用不同服务商。</div>
                </div>
                <div class="form-group">
                    <label class="form-label">Base URL</label>
                    <input type="text" class="form-input" id="cfgBaseUrl" value="${data.base_url || ''}" placeholder="https://api.openai.com/v1">
                    <div class="form-hint">支持OpenAI/智谱/通义/Moonshot/DeepSeek等兼容API</div>
                </div>
                <div class="form-group">
                    <label class="form-label">API Key ${configId ? '(留空则不修改)' : ''}</label>
                    <input type="password" class="form-input" id="cfgApiKey" value="" placeholder="sk-...">
                </div>
                <div class="form-group" id="cfgModelGroup">
                    <label class="form-label">对话模型名称</label>
                    <input type="text" class="form-input" id="cfgModel" value="${data.model || ''}" placeholder="gpt-4o">
                    <div class="form-hint" id="cfgModelHint"></div>
                </div>
                <div class="form-group" id="cfgEmbeddingGroup">
                    <label class="form-label">Embedding 模型</label>
                    <input type="text" class="form-input" id="cfgEmbeddingModel" value="${data.embedding_model || ''}" placeholder="text-embedding-3-small">
                    <div class="form-hint">用于知识库RAG功能。OpenAI: text-embedding-3-small，智谱: embedding-2</div>
                </div>
                <div class="flex gap-4">
                    <div class="form-group" style="flex: 1;">
                        <label class="form-label">温度 (0-1)</label>
                        <input type="number" class="form-input" id="cfgTemp" value="${data.temperature || 0.7}" min="0" max="1" step="0.1">
                    </div>
                    <div class="form-group" style="flex: 1;">
                        <label class="form-label">最大Token</label>
                        <input type="number" class="form-input" id="cfgMaxTokens" value="${data.max_tokens || 4096}" min="100" step="100">
                    </div>
                </div>
                <div class="flex gap-6">
                    <label class="flex items-center gap-2 cursor-pointer">
                        <input type="checkbox" id="cfgDefault" ${data.is_default ? 'checked' : ''}>
                        <span>设为默认</span>
                    </label>
                    <label class="flex items-center gap-2 cursor-pointer">
                        <input type="checkbox" id="cfgActive" ${data.is_active ? 'checked' : ''}>
                        <span>启用</span>
                    </label>
                </div>
            `,
            footer: `
                <button class="btn btn-secondary" onclick="Modal.close()">取消</button>
                <button class="btn btn-primary" onclick="AIConfigPage.save(${configId || 'null'})">保存</button>
            `,
        });

        // Trigger initial field visibility based on config_type
        this.onTypeChange();
    },

    onTypeChange() {
        const type = document.getElementById('cfgConfigType').value;
        const modelGroup = document.getElementById('cfgModelGroup');
        const embeddingGroup = document.getElementById('cfgEmbeddingGroup');
        const modelInput = document.getElementById('cfgModel');
        const modelHint = document.getElementById('cfgModelHint');

        if (type === 'embedding') {
            modelGroup.style.display = 'none';
            embeddingGroup.style.display = '';
        } else if (type === 'chat') {
            modelGroup.style.display = '';
            embeddingGroup.style.display = 'none';
            if (modelHint) modelHint.textContent = '';
        } else {
            modelGroup.style.display = '';
            embeddingGroup.style.display = '';
            if (modelHint) modelHint.textContent = '';
        }
    },

    async save(configId) {
        const data = {
            name: document.getElementById('cfgName').value.trim(),
            config_type: document.getElementById('cfgConfigType').value,
            base_url: document.getElementById('cfgBaseUrl').value.trim(),
            api_key: document.getElementById('cfgApiKey').value.trim(),
            model: document.getElementById('cfgModel').value.trim(),
            embedding_model: document.getElementById('cfgEmbeddingModel').value.trim(),
            temperature: parseFloat(document.getElementById('cfgTemp').value),
            max_tokens: parseInt(document.getElementById('cfgMaxTokens').value),
            is_default: document.getElementById('cfgDefault').checked,
            is_active: document.getElementById('cfgActive').checked,
        };

        // Embedding-only configs must not carry a stale chat model value
        if (data.config_type === 'embedding') {
            data.model = '';
        }

        if (!data.name || !data.base_url) {
            Toast.warning('名称和Base URL为必填项');
            return;
        }
        if (data.config_type !== 'embedding' && !data.model) {
            Toast.warning('对话模型名称为必填项（Embedding类型可留空）');
            return;
        }
        if (data.config_type === 'embedding' && !data.embedding_model) {
            Toast.warning('Embedding类型必须填写Embedding模型名称');
            return;
        }
        if (!configId && !data.api_key) {
            Toast.warning('API Key为必填项');
            return;
        }

        let result;
        if (configId) {
            result = await Api.put(`/api/ai-config/${configId}`, data);
        } else {
            result = await Api.post('/api/ai-config', data);
        }

        if (!result || result.error) {
            Toast.error(result?.message || '保存失败');
            return;
        }

        Toast.success(configId ? '配置已更新' : '配置已创建');
        Analytics.track('config_save', { config_id: configId || result.id });
        Modal.close();
        this.load();
    },

    async testConnection(configId) {
        Toast.info('正在测试连接...');

        const result = await Api.post(`/api/ai-config/${configId}/test`);
        if (!result || result.error) {
            Toast.error(result?.message || '测试失败');
            return;
        }

        if (result.success) {
            Toast.success(result.message);
            Analytics.track('config_test', { config_id: configId, success: true });
        } else {
            Toast.error(result.message);
            Analytics.track('config_test', { config_id: configId, success: false });
        }
        this.load();
    },

    async delete(configId) {
        Modal.confirm('确定删除此AI模型配置？', async () => {
            const result = await Api.delete(`/api/ai-config/${configId}`);
            if (!result || result.error) {
                Toast.error(result?.message || '删除失败');
                return;
            }
            Toast.success('配置已删除');
            this.load();
        });
    },
};
