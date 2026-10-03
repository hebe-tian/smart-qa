"""Prompt service: templates for all AI generation steps."""

SYSTEM_PROMPT = """You are a senior software test engineer with extensive experience in test case design. \
You analyze software requirements and generate comprehensive, structured test cases. \
You think from multiple perspectives: functional, boundary, exception, and performance. \
You always respond in the same language as the user's requirement. \
When asked to output JSON, you must output valid JSON only, no markdown fences or extra text."""


class PromptService:
    """Service for building AI prompt messages for each generation step."""

    @staticmethod
    def analyze_requirement_prompt(requirement_content):
        """Step 1: Analyze if requirement needs clarification.
        Returns messages for AI to determine if clarification is needed."""
        user_prompt = f"""Analyze the following software requirement and determine if there are any \
ambiguities, missing details, or unclear points that need clarification before test cases can be generated.

Requirement:
{requirement_content}

Respond in JSON format:
{{
    "need_clarification": true/false,
    "clarification_points": ["point 1", "point 2", ...],
    "analysis_summary": "Brief summary of the requirement analysis"
}}

If the requirement is clear and complete enough to generate test cases, set "need_clarification" to false.
If clarification is needed, set it to true and list specific questions in "clarification_points".
"""
        return [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

    @staticmethod
    def qa_followup_prompt(requirement_content, qa_history):
        """Step 2: Generate follow-up questions or determine sufficient context.
        qa_history: list of {"role": "assistant"/"user", "content": str}
        """
        history_text = ""
        for msg in qa_history:
            role_label = "AI" if msg["role"] == "assistant" else "User"
            history_text += f"{role_label}: {msg['content']}\n"

        user_prompt = f"""Original requirement:
{requirement_content}

Previous Q&A:
{history_text}

Based on the requirement and the Q&A so far, determine if the context is now sufficient to generate \
comprehensive test cases. If still insufficient, ask the next most important clarification question(s).

Respond in JSON format:
{{
    "context_sufficient": true/false,
    "next_questions": ["question 1", ...],
    "reasoning": "Brief explanation of why context is or is not sufficient"
}}

Ask at most 2 questions per round. Only set "context_sufficient" to true when you have enough information.
"""
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
        ]
        for msg in qa_history:
            messages.append({"role": msg["role"], "content": msg["content"]})
        messages.append({"role": "user", "content": user_prompt})
        return messages

    @staticmethod
    def generate_modules_prompt(requirement_content, qa_context, rag_context=None, code_context=None):
        """Step 3: Generate module breakdown from requirement + QA context.

        Args:
            rag_context: Optional RAG-retrieved similar module structures from
                         past production projects. Injected as reference.
            code_context: Optional RAG-retrieved business code snippets from
                         the imported codebase. Injected as implementation reference.
        """
        qa_text = ""
        if qa_context:
            for msg in qa_context:
                role_label = "Q" if msg["role"] == "assistant" else "A"
                qa_text += f"{role_label}: {msg['content']}\n"

        rag_section = ""
        if rag_context:
            rag_section = f"""
Reference: Similar module structures from past projects (use as inspiration, not for copying):
{rag_context}
"""
        code_section = ""
        if code_context:
            code_section = f"""
Implementation Reference: Relevant business code from the project codebase (use to understand actual implementation details and module boundaries):
{code_context}
"""
        user_prompt = f"""Based on the following requirement and clarification Q&A, \
break down the software into functional modules for test case organization.
{rag_section}{code_section}
Requirement:
{requirement_content}

Clarification Q&A:
{qa_text}

Generate a list of modules. Each module should represent a logical grouping of related functionality.

Respond in JSON format:
{{
    "modules": [
        {{
            "module_name": "Module name",
            "description": "What this module covers",
            "key_points": ["key testing point 1", "key testing point 2"]
        }},
        ...
    ]
}}

Generate between 3-8 modules depending on requirement complexity. Cover all major functionality areas.
"""
        return [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

    @staticmethod
    def generate_cases_prompt(requirement_content, module_name, module_description, module_key_points, rag_context=None, code_context=None):
        """Step 4: Generate test cases for a specific module.

        Args:
            rag_context: Optional RAG-retrieved similar test cases from
                         past production projects. Injected as few-shot examples.
            code_context: Optional RAG-retrieved business code snippets from
                         the imported codebase. Injected as implementation reference.
        """
        key_points_text = "\n".join(f"- {p}" for p in (module_key_points or []))

        rag_section = ""
        if rag_context:
            rag_section = f"""
Reference: Similar test cases from past projects (use as few-shot examples for style and coverage, not for copying):
{rag_context}
"""
        code_section = ""
        if code_context:
            code_section = f"""
Implementation Reference: Relevant business code from the project codebase (use to understand actual implementation logic, APIs, and data structures for precise test design):
{code_context}
"""
        user_prompt = f"""Generate detailed test cases for the following module.
{rag_section}{code_section}
Overall Requirement Context:
{requirement_content}

Module: {module_name}
Description: {module_description}
Key Testing Points:
{key_points_text}

Generate comprehensive test cases covering: functional, boundary, exception, and edge cases.

Respond in JSON format:
{{
    "test_cases": [
        {{
            "title": "Test case title",
            "preconditions": "Preconditions and setup needed",
            "steps": ["Step 1: ...", "Step 2: ...", "Step 3: ..."],
            "expected_result": "Expected outcome",
            "priority": "high"/"medium"/"low",
            "case_type": "functional"/"boundary"/"exception"/"performance"
        }},
        ...
    ]
}}

Generate 3-8 test cases per module. Ensure each test case is specific and actionable.
"""
        return [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

    @staticmethod
    def regenerate_prompt(target_type, original_content, reason, description, requirement_content=None):
        """Step 5: Regenerate based on original content + reason + description."""
        if target_type == "module":
            user_prompt = f"""Regenerate the following test module based on the provided feedback.

Original module content:
{original_content}

Reason for regeneration: {reason}
Additional requirements: {description}

Requirement context:
{requirement_content or "N/A"}

Respond in JSON format:
{{
    "module_name": "Module name",
    "description": "Updated description",
    "key_points": ["key point 1", ...]
}}
"""
        else:
            user_prompt = f"""Regenerate the following test case(s) based on the provided feedback.

Original test case content:
{original_content}

Reason for regeneration: {reason}
Additional requirements: {description}

Respond in JSON format:
{{
    "test_cases": [
        {{
            "title": "Test case title",
            "preconditions": "Preconditions",
            "steps": ["Step 1", "Step 2", ...],
            "expected_result": "Expected result",
            "priority": "high"/"medium"/"low",
            "case_type": "functional"/"boundary"/"exception"/"performance"
        }},
        ...
    ]
}}
"""
        return [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

    @staticmethod
    def extract_requirement_prompt(document_text):
        """Pre-step: Extract a structured requirement {title, content} from an uploaded document's raw text.

        Used by the document upload flow — the AI cleans formatting noise and organizes
        the requirement body, then the user reviews/edits before saving.
        """
        user_prompt = f"""The following text was extracted from a document uploaded by the user. \
Please extract a structured software requirement from it.

Document text:
{document_text}

Tasks:
1. Generate a concise and accurate requirement title (max ~30 characters).
2. Extract and clean the requirement body: keep all functional points, business rules, and \
acceptance criteria; remove formatting noise (headers/footers, table of contents, page numbers, \
redundant blank lines); organize into clear, structured plain text.

Respond in JSON format:
{{
    "title": "Requirement title",
    "content": "Cleaned requirement body"
}}

Output JSON only, no markdown fences or extra text."""
        return [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]
