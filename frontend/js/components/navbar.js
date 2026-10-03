// Top navbar component
const Navbar = {
    render() {
        const el = document.getElementById('navbarRight');
        if (!el) return;

        const user = Auth.getUser() || {};
        const username = user.username || 'User';
        const initials = username.substring(0, 2).toUpperCase();
        const isGuest = Auth.isGuest();

        el.innerHTML = `
            <div class="navbar-user" ${isGuest ? 'title="游客模式：仅可浏览"' : ''}>
                <div class="navbar-user-avatar">${isGuest ? '客' : initials}</div>
                <span>${isGuest ? '游客' : username}</span>
            </div>
        `;
    },
};
