// Tree component: module-case hierarchical tree with expand/collapse and checkboxes
const Tree = {
    data: [],
    selectedIds: new Set(),
    onSelectCallback: null,

    render(containerId, data, onSelect) {
        const container = document.getElementById(containerId);
        if (!container) return;

        this.data = data;
        this.onSelectCallback = onSelect;
        this.selectedIds = new Set();

        let html = '';
        for (const module of data) {
            html += this._renderModule(module);
        }
        container.innerHTML = html || '<div class="empty-state"><div class="empty-state-text">暂无数据</div></div>';

        this._bindEvents(container);
    },

    _renderModule(module) {
        const cases = module.cases || [];
        const caseCount = cases.length;
        return `
            <div class="tree-node">
                <div class="tree-item" onclick="Tree._toggle(this)">
                    <span class="tree-toggle">></span>
                    <input type="checkbox" class="tree-checkbox"
                           onchange="Tree._toggleSelect(${module.id}, 'module', this.checked, event)"
                           ${this.selectedIds.has('module_' + module.id) ? 'checked' : ''}>
                    <span class="tree-label font-semibold">${module.name}</span>
                    <span class="badge badge-muted">${caseCount}</span>
                </div>
                <div class="tree-children">
                    ${cases.map(c => this._renderCase(module.id, c)).join('')}
                </div>
            </div>
        `;
    },

    _renderCase(moduleId, caseItem) {
        return `
            <div class="tree-node">
                <div class="tree-item" onclick="Tree._selectCase(${moduleId}, ${caseItem.id}, this)">
                    <span class="tree-toggle" style="visibility:hidden;">.</span>
                    <input type="checkbox" class="tree-checkbox"
                           onchange="Tree._toggleSelect(${caseItem.id}, 'case', this.checked, event)"
                           ${this.selectedIds.has('case_' + caseItem.id) ? 'checked' : ''}>
                    <span class="tree-label">${caseItem.title}</span>
                    <span class="badge ${PRIORITY_MAP[caseItem.priority]?.class || 'badge-muted'}">${PRIORITY_MAP[caseItem.priority]?.label || caseItem.priority}</span>
                </div>
            </div>
        `;
    },

    _toggle(el) {
        const toggle = el.querySelector('.tree-toggle');
        const children = el.nextElementSibling;
        if (toggle) toggle.classList.toggle('expanded');
        if (children) children.classList.toggle('expanded');
    },

    _selectCase(moduleId, caseId, el) {
        document.querySelectorAll('.tree-item').forEach(item => item.classList.remove('active'));
        el.classList.add('active');
        if (this.onSelectCallback) {
            this.onSelectCallback('case', caseId);
        }
    },

    _toggleSelect(id, type, checked, event) {
        event.stopPropagation();
        const key = `${type}_${id}`;
        if (checked) {
            this.selectedIds.add(key);
        } else {
            this.selectedIds.delete(key);
        }
    },

    getSelected() {
        const result = { cases: [], modules: [] };
        for (const key of this.selectedIds) {
            const [type, id] = key.split('_');
            if (type === 'case') result.cases.push(parseInt(id));
            else if (type === 'module') result.modules.push(parseInt(id));
        }
        return result;
    },

    expandAll() {
        document.querySelectorAll('.tree-toggle').forEach(t => t.classList.add('expanded'));
        document.querySelectorAll('.tree-children').forEach(c => c.classList.add('expanded'));
    },

    _bindEvents(container) {
        // Prevent checkbox click from triggering row click
        container.querySelectorAll('.tree-checkbox').forEach(cb => {
            cb.addEventListener('click', (e) => e.stopPropagation());
        });
    },
};
