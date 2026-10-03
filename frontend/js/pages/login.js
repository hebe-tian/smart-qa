// Login page logic
const Login = {
    async handleLogin() {
        const btn = document.getElementById('loginBtn');
        const username = document.getElementById('username').value.trim();
        const password = document.getElementById('password').value;
        const errorEl = document.getElementById('loginError');

        if (!username || !password) {
            errorEl.textContent = '请输入用户名和密码';
            errorEl.style.display = 'block';
            return;
        }

        btn.disabled = true;
        btn.innerHTML = '<span class="spinner"></span> 登录中...';

        const success = await Auth.login(username, password);

        if (success) {
            Toast.success('登录成功，正在跳转...');
            Analytics.track('login');
            setTimeout(() => {
                window.location.href = '/dashboard.html';
            }, 500);
        } else {
            errorEl.textContent = '用户名或密码错误';
            errorEl.style.display = 'block';
            btn.disabled = false;
            btn.textContent = '登录';
        }
    },
    async handleGuest() {
        const btn = document.getElementById('guestBtn');
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner"></span> 进入中...';

        const result = await Api.post('/api/auth/guest');
        if (result && !result.error) {
            Auth.setAuth(result.token, result.user);
            Toast.success('已进入游客模式，仅可浏览');
            Analytics.track('guest_login');
            setTimeout(() => {
                window.location.href = '/dashboard.html';
            }, 500);
        } else {
            Toast.error(result?.message || '进入游客模式失败');
            btn.disabled = false;
            btn.textContent = '游客访问';
        }
    },
};

// Auto redirect if already logged in
if (Auth.isLoggedIn()) {
    window.location.href = '/dashboard.html';
}

// Enter key to submit
document.getElementById('loginForm')?.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') Login.handleLogin();
});
