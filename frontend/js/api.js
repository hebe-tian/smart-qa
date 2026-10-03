// Fetch API wrapper with JWT auth, error handling, and task polling
const Api = {
    getToken() {
        return localStorage.getItem(CONFIG.TOKEN_KEY) || '';
    },

    async request(url, options = {}) {
        const token = this.getToken();
        const headers = {
            'Content-Type': 'application/json',
            ...(options.headers || {}),
        };
        if (token) {
            headers['Authorization'] = `Bearer ${token}`;
        }

        const config = {
            ...options,
            headers,
        };

        try {
            const response = await fetch(CONFIG.API_BASE + url, config);
            const data = await response.json();

            if (response.status === 401) {
                Auth.logout();
                return null;
            }

            if (!response.ok) {
                const errMsg = data.error || `HTTP ${response.status}`;
                return { error: true, message: errMsg, status: response.status };
            }

            return data;
        } catch (e) {
            console.error('API Error:', e);
            return { error: true, message: e.message || 'Network error' };
        }
    },

    get(url) {
        return this.request(url, { method: 'GET' });
    },

    post(url, body) {
        return this.request(url, {
            method: 'POST',
            body: body ? JSON.stringify(body) : undefined,
        });
    },

    put(url, body) {
        return this.request(url, {
            method: 'PUT',
            body: body ? JSON.stringify(body) : undefined,
        });
    },

    delete(url) {
        return this.request(url, { method: 'DELETE' });
    },

    // --- SOP ---
    sopList() {
        return this.get('/api/sop');
    },
    sopGenerate(sessionId, messageId) {
        return this.post('/api/sop/generate', { session_id: sessionId, message_id: messageId });
    },
    sopGetTemplate() {
        return this.get('/api/sop/template');
    },
    sopUpdateTemplate(content) {
        return this.put('/api/sop/template', { content });
    },
    sopResetTemplate() {
        return this.post('/api/sop/template/reset');
    },
    sopGet(id) {
        return this.get(`/api/sop/${id}`);
    },
    sopUpdate(id, data) {
        return this.put(`/api/sop/${id}`, data);
    },
    sopIndex(id) {
        return this.post(`/api/sop/${id}/index`, {});
    },
    sopDelete(id) {
        return this.delete(`/api/sop/${id}`);
    },

    // Upload multipart/form-data (file + fields)
    async upload(url, formData) {
        const token = this.getToken();
        const headers = {};
        if (token) {
            headers['Authorization'] = `Bearer ${token}`;
        }
        try {
            const response = await fetch(CONFIG.API_BASE + url, {
                method: 'POST',
                headers,
                body: formData,
            });
            const data = await response.json();
            if (response.status === 401) {
                Auth.logout();
                return null;
            }
            if (!response.ok) {
                const errMsg = data.error || `HTTP ${response.status}`;
                return { error: true, message: errMsg, status: response.status };
            }
            return data;
        } catch (e) {
            console.error('API Upload Error:', e);
            return { error: true, message: e.message || 'Network error' };
        }
    },

    // Download a file from the API (blob download with JWT auth)
    async downloadFile(url) {
        const token = this.getToken();
        const headers = {};
        if (token) {
            headers['Authorization'] = `Bearer ${token}`;
        }

        try {
            const response = await fetch(CONFIG.API_BASE + url, { headers });

            if (response.status === 401) {
                Auth.logout();
                return { error: true, message: '认证已过期，请重新登录' };
            }

            if (!response.ok) {
                // Try to parse error JSON
                let errMsg = `HTTP ${response.status}`;
                try {
                    const data = await response.json();
                    errMsg = data.error || errMsg;
                } catch (_) { /* response body not JSON */ }
                return { error: true, message: errMsg };
            }

            const blob = await response.blob();

            // Extract filename from Content-Disposition header
            const cd = response.headers.get('Content-Disposition') || '';
            let filename = 'export';
            const utf8Match = cd.match(/filename\*=UTF-8''(.+)/i);
            if (utf8Match) {
                filename = decodeURIComponent(utf8Match[1]);
            } else {
                const plainMatch = cd.match(/filename="?([^";\n]+)"?/i);
                if (plainMatch) filename = plainMatch[1];
            }

            // Trigger browser download
            const objectUrl = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = objectUrl;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(objectUrl);

            return { success: true, filename };
        } catch (e) {
            console.error('Download Error:', e);
            return { error: true, message: e.message || 'Network error' };
        }
    },

    // Poll a task until completed or failed
    async pollTask(taskId, onProgress, onComplete, onError) {
        return new Promise((resolve, reject) => {
            const poll = async () => {
                const result = await this.get(`/api/tasks/${taskId}/status`);
                if (result && result.error) {
                    if (onError) onError(result.message);
                    reject(result.message);
                    return;
                }
                if (!result) {
                    reject('Task not found');
                    return;
                }

                if (onProgress) onProgress(result);

                if (result.status === 'completed') {
                    const taskResult = await this.get(`/api/tasks/${taskId}/result`);
                    if (onComplete) onComplete(taskResult);
                    resolve(taskResult);
                    return;
                }

                if (result.status === 'failed') {
                    if (onError) onError(result.error || 'Task failed');
                    reject(result.error || 'Task failed');
                    return;
                }

                // Continue polling
                setTimeout(poll, CONFIG.POLL_INTERVAL);
            };
            poll();
        });
    },
};
