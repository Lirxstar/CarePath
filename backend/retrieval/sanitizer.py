"""Application-controlled sanitization for retrieved untrusted text.

Natural-language evidence never receives instruction authority.  This module removes
common instruction-like spans before retrieved text reaches planner/model-facing
surfaces and emits only bounded security metadata for audit/debugging.
"""

from __future__ import annotations

import re
from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class InjectionPattern(StrEnum):
    POLICY_OVERRIDE = "policy_override"
    SAFETY_BYPASS = "safety_bypass"
    SECRET_EXFILTRATION = "secret_exfiltration"
    TOOL_EXECUTION = "tool_execution"
    SCOPE_OVERRIDE = "scope_override"
    CROSS_USER_ACCESS = "cross_user_access"
    DATABASE_EXECUTION = "database_execution"
    ARBITRARY_URL = "arbitrary_url"


class SanitizedEvidence(BaseModel):
    """Sanitized representation of one untrusted retrieved payload."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    content: str
    detected_patterns: tuple[InjectionPattern, ...] = ()
    sanitized: bool = False
    allow_as_evidence: bool = True

    def render_untrusted_packet(self) -> str:
        """Wrap text as data, never as an instruction block."""

        return f"<UNTRUSTED_EVIDENCE_DATA>\n{self.content}\n</UNTRUSTED_EVIDENCE_DATA>"


_REPLACEMENT = "[instruction-like content removed]"
_PATTERN_SPECS: tuple[tuple[InjectionPattern, re.Pattern[str]], ...] = (
    (
        InjectionPattern.POLICY_OVERRIDE,
        re.compile(
            r"ignore\s+(?:all\s+|the\s+)?(?:previous|prior|system)\s+instructions?|"
            r"(?:override|replace|change)\s+(?:the\s+)?system\s+(?:prompt|policy)|"
            r"忽略(?:之前|先前|系统)(?:的)?指令|覆盖系统(?:提示词|规则)|"
            r"以前の(?:指示|命令)を無視|システム(?:プロンプト|規則)を上書き",
            re.IGNORECASE,
        ),
    ),
    (
        InjectionPattern.SAFETY_BYPASS,
        re.compile(
            r"(?:disable|bypass|skip|turn off).{0,24}(?:safety|triage|verifier|guardrail)|"
            r"(?:downgrade|set).{0,24}risk\s+level|"
            r"(?:关闭|绕过|跳过).{0,16}(?:安全|分诊|验证器)|降低风险等级|"
            r"(?:安全|トリアージ|検証)を(?:無効|回避|スキップ)",
            re.IGNORECASE,
        ),
    ),
    (
        InjectionPattern.SECRET_EXFILTRATION,
        re.compile(
            r"(?:reveal|print|show|expose|return).{0,32}"
            r"(?:system\s+prompt|api\s+key|secret|credential|access\s+token)|"
            r"(?:显示|泄露|输出).{0,20}(?:系统提示词|密钥|凭据|令牌)|"
            r"(?:表示|公開|出力).{0,20}(?:システムプロンプト|APIキー|秘密|認証情報)",
            re.IGNORECASE,
        ),
    ),
    (
        InjectionPattern.TOOL_EXECUTION,
        re.compile(
            r"(?:call|invoke|execute|run).{0,24}(?:tool|function|shell|command)|"
            r"(?:调用|执行|运行).{0,16}(?:工具|函数|命令|shell)|"
            r"(?:ツール|関数|コマンド|shell)を(?:呼び出|実行)",
            re.IGNORECASE,
        ),
    ),
    (
        InjectionPattern.SCOPE_OVERRIDE,
        re.compile(
            r"(?:change|switch|override|impersonate).{0,28}"
            r"(?:user|persona|tenant|scope|permission)|"
            r"(?:切换|更改|冒充|覆盖).{0,16}(?:用户|人格|租户|权限|范围)|"
            r"(?:ユーザー|権限|スコープ)を(?:変更|切替|上書き)",
            re.IGNORECASE,
        ),
    ),
    (
        InjectionPattern.CROSS_USER_ACCESS,
        re.compile(
            r"(?:retrieve|access|read|fetch).{0,24}(?:another|other).{0,16}"
            r"(?:user|patient|persona)|"
            r"(?:读取|访问|获取).{0,16}(?:其他|别的)(?:用户|患者)|"
            r"(?:他|別)の(?:ユーザー|患者).{0,16}(?:読|取得|アクセス)",
            re.IGNORECASE,
        ),
    ),
    (
        InjectionPattern.DATABASE_EXECUTION,
        re.compile(
            r"(?:execute|run).{0,24}(?:sql|query)|"
            r"\b(?:select|insert|update|delete|drop)\s+.{0,48}\b(?:from|into|table)\b|"
            r"执行.{0,12}(?:SQL|数据库查询)|SQLを実行",
            re.IGNORECASE,
        ),
    ),
    (
        InjectionPattern.ARBITRARY_URL,
        re.compile(
            r"(?:fetch|request|open).{0,32}https?://\S+|"
            r"(?:send|post|upload|forward).{0,64}(?:to\s+)?https?://\S+|"
            r"(?:访问|请求|打开|发送|上传).{0,32}https?://\S+|"
            r"https?://\S+.{0,20}(?:へ送信|にアクセス)",
            re.IGNORECASE,
        ),
    ),
)


def sanitize_retrieved_content(text: str) -> SanitizedEvidence:
    """Remove instruction-like spans and mark hostile payloads as non-evidence.

    Detection is defence-in-depth only.  Authorization, user scoping, tool allowlists,
    typed arguments, and verifier checks remain independent controls.
    """

    cleaned = text
    detected: list[InjectionPattern] = []
    for pattern_id, pattern in _PATTERN_SPECS:
        if pattern.search(cleaned):
            detected.append(pattern_id)
            cleaned = pattern.sub(_REPLACEMENT, cleaned)

    normalized = " ".join(cleaned.split())
    return SanitizedEvidence(
        content=normalized,
        detected_patterns=tuple(dict.fromkeys(detected)),
        sanitized=bool(detected),
        allow_as_evidence=not detected,
    )
