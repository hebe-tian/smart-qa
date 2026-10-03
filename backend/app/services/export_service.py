"""Export service: generate test cases in HTML / Markdown / XMind / Excel formats."""
import io
import json
import uuid
import zipfile
from datetime import datetime

from app.extensions import db
from app.models.requirement import Requirement
from app.models.module import Module
from app.models.test_case import TestCase
from app.services.logging_service import get_logger

logger = get_logger("api")

# Priority display mapping
_PRIORITY_MAP = {
    "high": "高",
    "medium": "中",
    "low": "低",
}

# Case type display mapping
_CASE_TYPE_MAP = {
    "functional": "功能测试",
    "boundary": "边界测试",
    "exception": "异常测试",
    "performance": "性能测试",
}

# Format → (extension, mimetype)
_FORMAT_META = {
    "html": ("html", "text/html; charset=utf-8"),
    "md": ("md", "text/markdown; charset=utf-8"),
    "xmind": ("xmind", "application/x-xmind"),
}


class ExportService:
    """Service for exporting test cases in multiple formats."""

    def generate(self, req_id: int, fmt: str):
        """
        Generate exported file for a requirement.

        Returns: (filename: str, content: bytes, mimetype: str)
        """
        data = self._load_data(req_id)
        if not data["modules"]:
            raise ValueError("该需求下暂无模块数据，无法导出")

        ext, mimetype = _FORMAT_META[fmt]
        safe_title = data["title"].replace("/", "_").replace("\\", "_")[:60]
        date_str = datetime.now().strftime("%Y%m%d")
        filename = f"{safe_title}_{date_str}.{ext}"

        if fmt == "html":
            content = self._generate_html(data).encode("utf-8")
        elif fmt == "md":
            content = self._generate_markdown(data).encode("utf-8")
        elif fmt == "xmind":
            content = self._generate_xmind(data)
        else:
            raise ValueError(f"Unsupported format: {fmt}")

        logger.debug(f"Exported requirement {req_id} as {fmt}, filename={filename}")
        return filename, content, mimetype

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def _load_data(self, req_id: int) -> dict:
        """Load requirement with modules and cases into a plain dict."""
        req = db.session.get(Requirement, req_id)
        if not req:
            raise ValueError("需求不存在")

        modules = (
            Module.query.filter_by(requirement_id=req_id)
            .order_by(Module.order)
            .all()
        )

        result = {
            "id": req.id,
            "title": req.title,
            "content": req.content or "",
            "modules": [],
        }

        for m in modules:
            cases = (
                TestCase.query.filter_by(module_id=m.id)
                .order_by(TestCase.order)
                .all()
            )
            result["modules"].append({
                "id": m.id,
                "name": m.name,
                "description": m.description or "",
                "key_points": json.loads(m.key_points) if m.key_points else [],
                "cases": [self._case_to_dict(c) for c in cases],
            })

        return result

    def _case_to_dict(self, case: TestCase) -> dict:
        steps = json.loads(case.steps_json) if case.steps_json else []
        return {
            "id": case.id,
            "title": case.title,
            "preconditions": case.preconditions or "",
            "steps": steps,
            "expected_result": case.expected_result or "",
            "priority": _PRIORITY_MAP.get(case.priority, case.priority),
            "priority_raw": case.priority,
            "case_type": _CASE_TYPE_MAP.get(case.case_type, case.case_type),
            "case_type_raw": case.case_type,
        }

    # ------------------------------------------------------------------
    # HTML
    # ------------------------------------------------------------------

    def _generate_html(self, data: dict) -> str:
        title = data["title"]
        total_cases = sum(len(m["cases"]) for m in data["modules"])
        modules_html = []

        for m in data["modules"]:
            if not m["cases"]:
                continue
            rows = []
            for c in m["cases"]:
                steps_html = "<ol>" + "".join(
                    f"<li>{self._esc(s)}</li>" for s in c["steps"]
                ) + "</ol>" if c["steps"] else "无"
                rows.append(f"""
                <tr>
                    <td>{self._esc(c['title'])}</td>
                    <td class="center"><span class="priority priority-{c['priority_raw']}">{c['priority']}</span></td>
                    <td class="center">{c['case_type']}</td>
                    <td>{self._esc(c['preconditions']) or '无'}</td>
                    <td>{steps_html}</td>
                    <td>{self._esc(c['expected_result']) or '无'}</td>
                </tr>""")

            modules_html.append(f"""
            <div class="module-section">
                <h2 class="module-title">{self._esc(m['name'])}</h2>
                {f'<p class="module-desc">{self._esc(m["description"])}</p>' if m['description'] else ''}
                <table>
                    <thead>
                        <tr>
                            <th>用例标题</th>
                            <th class="center">优先级</th>
                            <th class="center">类型</th>
                            <th>前置条件</th>
                            <th>测试步骤</th>
                            <th>预期结果</th>
                        </tr>
                    </thead>
                    <tbody>
                        {''.join(rows)}
                    </tbody>
                </table>
            </div>""")

        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{self._esc(title)} - 测试用例</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: "Noto Sans", "Segoe UI", "Microsoft YaHei", sans-serif; background: #f8fafc; color: #1e293b; padding: 40px; line-height: 1.6; }}
  .header {{ text-align: center; margin-bottom: 32px; padding-bottom: 24px; border-bottom: 2px solid #2563eb; }}
  .header h1 {{ font-size: 24px; color: #1e293b; margin-bottom: 8px; }}
  .header .meta {{ font-size: 13px; color: #64748b; }}
  .module-section {{ background: #fff; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); margin-bottom: 24px; overflow: hidden; }}
  .module-title {{ font-size: 18px; padding: 16px 24px; background: #f1f5f9; border-bottom: 1px solid #e2e8f0; }}
  .module-desc {{ padding: 8px 24px; font-size: 13px; color: #64748b; background: #f8fafc; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  th {{ background: #2563eb; color: #fff; padding: 10px 12px; text-align: left; font-weight: 600; white-space: nowrap; }}
  td {{ padding: 10px 12px; border-bottom: 1px solid #e2e8f0; vertical-align: top; }}
  td.center, th.center {{ text-align: center; }}
  tr:hover td {{ background: #f1f5f9; }}
  .priority {{ display: inline-block; padding: 2px 10px; border-radius: 4px; font-size: 12px; font-weight: 500; }}
  .priority-high {{ background: #fee2e2; color: #dc2626; }}
  .priority-medium {{ background: #fef3c7; color: #d97706; }}
  .priority-low {{ background: #d1fae5; color: #059669; }}
  ol {{ padding-left: 20px; }}
  ol li {{ margin-bottom: 4px; }}
</style>
</head>
<body>
  <div class="header">
    <h1>{self._esc(title)} - 测试用例</h1>
    <div class="meta">导出时间: {datetime.now().strftime("%Y-%m-%d %H:%M")} | 模块: {len(data['modules'])} | 用例: {total_cases}</div>
  </div>
  {''.join(modules_html)}
</body>
</html>"""

    # ------------------------------------------------------------------
    # Markdown
    # ------------------------------------------------------------------

    def _generate_markdown(self, data: dict) -> str:
        title = data["title"]
        total_cases = sum(len(m["cases"]) for m in data["modules"])
        lines = [
            f"# {title}",
            "",
            f"> 导出时间: {datetime.now().strftime('%Y-%m-%d %H:%M')} | 模块: {len(data['modules'])} | 用例: {total_cases}",
            "",
        ]

        for m in data["modules"]:
            if not m["cases"]:
                continue
            lines.append(f"## {m['name']}")
            if m["description"]:
                lines.append("")
                lines.append(f"> {m['description']}")
            lines.append("")

            for c in m["cases"]:
                lines.append(f"### {c['title']}")
                lines.append("")
                lines.append(f"| 优先级 | 类型 |")
                lines.append(f"|--------|------|")
                lines.append(f"| {c['priority']} | {c['case_type']} |")
                lines.append("")
                lines.append(f"**前置条件**")
                lines.append("")
                lines.append(c["preconditions"] or "无")
                lines.append("")
                lines.append(f"**测试步骤**")
                lines.append("")
                if c["steps"]:
                    for i, s in enumerate(c["steps"], 1):
                        lines.append(f"{i}. {s}")
                else:
                    lines.append("无")
                lines.append("")
                lines.append(f"**预期结果**")
                lines.append("")
                lines.append(c["expected_result"] or "无")
                lines.append("")
                lines.append("---")
                lines.append("")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # XMind (.xmind is a ZIP archive containing JSON)
    # ------------------------------------------------------------------

    def _generate_xmind(self, data: dict) -> bytes:
        """Generate .xmind file (ZIP of content.json + metadata.json + manifest.json)."""

        def _topic_id():
            return uuid.uuid4().hex

        root_id = _topic_id()
        root_topic = {
            "id": root_id,
            "class": "topic",
            "title": data["title"],
            "children": {"attached": []},
        }

        for m in data["modules"]:
            mod_topic = {
                "id": _topic_id(),
                "class": "topic",
                "title": m["name"],
                "children": {"attached": []},
            }
            for c in m["cases"]:
                case_topic = {
                    "id": _topic_id(),
                    "class": "topic",
                    "title": c["title"],
                }
                # Add case details as notes
                note_parts = [f"优先级: {c['priority']}", f"类型: {c['case_type']}"]
                if c["preconditions"]:
                    note_parts.append(f"前置条件: {c['preconditions']}")
                if c["steps"]:
                    steps_text = "\n".join(
                        f"  {i}. {s}" for i, s in enumerate(c["steps"], 1)
                    )
                    note_parts.append(f"测试步骤:\n{steps_text}")
                if c["expected_result"]:
                    note_parts.append(f"预期结果: {c['expected_result']}")
                case_topic["notes"] = {
                    "plain": {"content": "\n".join(note_parts)}
                }
                mod_topic["children"]["attached"].append(case_topic)
            root_topic["children"]["attached"].append(mod_topic)

        content = [{
            "id": _topic_id(),
            "class": "sheet",
            "title": "Sheet 1",
            "rootTopic": root_topic,
        }]

        content_json = json.dumps(content, ensure_ascii=False)
        metadata = {
            "creator": {"name": "AI Test Case Platform", "version": "1.0.0"},
            "layoutEngine": {"type": "logic"},
        }
        metadata_json = json.dumps(metadata, ensure_ascii=False)
        manifest = {
            "file-entries": {
                "content.json": {},
                "metadata.json": {},
            },
        }
        manifest_json = json.dumps(manifest, ensure_ascii=False)

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("content.json", content_json)
            zf.writestr("metadata.json", metadata_json)
            zf.writestr("manifest.json", manifest_json)
        buf.seek(0)
        return buf.getvalue()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _esc(text: str) -> str:
        """HTML-escape text."""
        if not text:
            return ""
        return (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&#39;")
        )
