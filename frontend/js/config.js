// API configuration and constants
const CONFIG = {
    API_BASE: '',  // Same origin, Flask serves both API and static files
    TOKEN_KEY: 'ai_testcase_token',
    USER_KEY: 'ai_testcase_user',
    POLL_INTERVAL: 2000,  // 2 seconds for task polling
    PAGE_SIZE: 20,
};

const STATUS_MAP = {
    'draft': { label: '草稿', class: 'badge-muted' },
    'analyzing': { label: '分析中', class: 'badge-info' },
    'qa': { label: '问答中', class: 'badge-warning' },
    'generating': { label: '生成中', class: 'badge-info' },
    'completed': { label: '已完成', class: 'badge-success' },
};

const CALL_STATUS_MAP = {
    'success': { label: '成功', class: 'badge-success' },
    'failed': { label: '失败', class: 'badge-danger' },
    'running': { label: '运行中', class: 'badge-warning' },
};

const TASK_TYPE_MAP = {
    'analyze': '需求分析',
    'qa': '问答追问',
    'module_gen': '模块生成',
    'case_gen': '用例生成',
    'case_gen_all': '全量用例生成',
    'regen': '重新生成',
    'test_conn': '连接测试',
    'chat': '对话',
};

const PRIORITY_MAP = {
    'high': { label: '高', class: 'badge-danger' },
    'medium': { label: '中', class: 'badge-warning' },
    'low': { label: '低', class: 'badge-info' },
};

const CASE_TYPE_MAP = {
    'functional': '功能测试',
    'boundary': '边界测试',
    'exception': '异常测试',
    'performance': '性能测试',
};

const CHUNK_TYPE_MAP = {
    'requirement': '需求',
    'module': '模块',
    'test_case': '测试用例',
    'qa': '历史问答',
    'qa_negative': '错误问答',
    'code': '业务代码',
    'sop': 'SOP 文档',
};

const PROJECT_TYPE_MAP = {
    'production': { label: '线上', class: 'badge-success' },
    'test': { label: '测试', class: 'badge-warning' },
};
