// Sidebar navigation component
const Sidebar = {
    items: [
        { id: 'dashboard', label: '需求管理', icon: '[L]', page: 'dashboard' },
        { id: 'requirement', label: '需求详情', icon: '[R]', page: 'dashboard' },
        { id: 'qa', label: '问答', icon: '[Q]', page: 'qa' },
        { id: 'knowledge-base', label: '知识库', icon: '[KB]', page: 'knowledge-base' },
        { id: 'sop', label: 'SOP管理', icon: '[P]', page: 'sop' },
        { id: 'ai-config', label: 'AI配置', icon: '[A]', page: 'ai-config' },
        { id: 'call-logs', label: '调用记录', icon: '[C]', page: 'call-logs' },
        { id: 'analytics', label: '数据概览', icon: '[S]', page: 'analytics' },
    ],

    // Pages hidden from guests (management / sensitive pages)
    guestHiddenIds: ['knowledge-base', 'ai-config', 'call-logs'],

    render(activeId) {
        const sidebar = document.getElementById('sidebar');
        if (!sidebar) return;

        const user = Auth.getUser() || {};
        const username = user.username || 'User';
        const initials = username.substring(0, 2).toUpperCase();
        const isGuest = Auth.isGuest();

        let navHtml = '';
        for (const item of this.items) {
            if (item.id === 'requirement' && activeId !== 'requirement') continue;
            if (isGuest && this.guestHiddenIds.includes(item.id)) continue;
            navHtml += `
                <div class="sidebar-nav-item ${activeId === item.id ? 'active' : ''}"
                     onclick="Router.navigate('${item.page}')">
                    <span class="sidebar-nav-icon">${item.icon}</span>
                    <span>${item.label}</span>
                </div>
            `;
        }

        sidebar.innerHTML = `
            <div class="sidebar-header">
                <div class="sidebar-logo">AI</div>
                <div>
                    <div class="sidebar-title">SMART-QA</div>
                    <div class="sidebar-subtitle">智能QA系统</div>
                </div>
            </div>
            <nav class="sidebar-nav">
                ${navHtml}
            </nav>
            <div class="sidebar-footer">
                ${isGuest ? '<div class="sidebar-guest-badge">游客模式 · 仅浏览</div>' : ''}
                <div class="sidebar-nav-item" onclick="Auth.logout()">
                    <span>${isGuest ? '退出游客模式' : '退出登录'}</span>
                </div>
            </div>
        `;
    },
};
