// Progress component: async task progress with polling and animation
const Progress = {
    show(containerId, taskId, onComplete, onError) {
        const container = document.getElementById(containerId);
        if (!container) return;

        container.innerHTML = `
            <div class="progress-container">
                <div class="progress-bar-bg">
                    <div class="progress-bar-fill" id="progressBar" style="width: 0%"></div>
                </div>
                <div class="progress-text" id="progressText">初始化中...</div>
            </div>
        `;

        const progressBar = document.getElementById('progressBar');
        const progressText = document.getElementById('progressText');

        Api.pollTask(
            taskId,
            (task) => {
                progressBar.style.width = task.progress + '%';
                progressText.textContent = task.message || `${task.progress}%`;
            },
            (result) => {
                if (result && result.result) {
                    progressBar.style.width = '100%';
                    progressText.textContent = '完成';
                }
                if (onComplete) onComplete(result);
            },
            (error) => {
                progressText.textContent = '失败: ' + error;
                progressText.style.color = 'var(--danger)';
                if (onError) onError(error);
            }
        );
    },
};
