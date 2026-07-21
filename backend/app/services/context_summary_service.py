from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.models.entities import ContextSummary, Message

SUMMARY_MAX_CHARS = 12_000
PREVIOUS_SUMMARY_MAX_CHARS = 4_000


class ContextSummaryService:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        settings: Settings,
    ) -> None:
        self.sessions = sessions
        self.settings = settings

    async def compress_if_needed(self, conversation_id: str) -> ContextSummary | None:
        async with self.sessions() as session:
            latest = await session.scalar(
                select(ContextSummary)
                .where(ContextSummary.conversation_id == conversation_id)
                .order_by(ContextSummary.end_seq_no.desc())
                .limit(1)
            )
            covered_seq = latest.end_seq_no if latest else 0
            messages = list(
                await session.scalars(
                    select(Message)
                    .where(
                        Message.conversation_id == conversation_id,
                        Message.seq_no > covered_seq,
                    )
                    .order_by(Message.seq_no.asc())
                )
            )
            total_chars = sum(len(message.content or "") for message in messages)
            if (
                len(messages) < self.settings.context_summary_message_threshold
                and total_chars < self.settings.context_summary_char_threshold
            ):
                return None
            retain = self.settings.context_summary_retain_messages
            compressible = messages[:-retain] if retain else messages
            if not compressible:
                return None
            summary = ContextSummary(
                conversation_id=conversation_id,
                start_seq_no=compressible[0].seq_no,
                end_seq_no=compressible[-1].seq_no,
                summary_text=build_factual_summary(latest, compressible),
                summary_version=(latest.summary_version + 1) if latest else 1,
            )
            session.add(summary)
            await session.commit()
            return summary


def build_factual_summary(
    previous: ContextSummary | None,
    messages: list[Message],
) -> str:
    message_entries: list[tuple[str, str]] = []
    for message in messages:
        role = {"user": "用户", "assistant": "分析助手"}.get(message.role, message.role)
        content = (message.content or "").strip().replace("\n", " ")
        message_entries.append((f"{role}[{message.seq_no}]：", content))

    line_count = len(message_entries) + (1 if previous else 0)
    separator_chars = max(0, line_count - 1)
    required_chars = separator_chars + sum(len(prefix) for prefix, _ in message_entries)
    if previous:
        required_chars += len("既有摘要：")
    content_budget = max(0, SUMMARY_MAX_CHARS - required_chars)

    previous_text = ""
    if previous:
        previous_budget = min(
            PREVIOUS_SUMMARY_MAX_CHARS,
            content_budget // 3,
        )
        previous_text = compact_text(previous.summary_text, previous_budget)
        content_budget -= len(previous_text)

    per_message_budget = (
        content_budget // len(message_entries) if message_entries else 0
    )
    remainder = content_budget % len(message_entries) if message_entries else 0
    lines: list[str] = []
    if previous:
        lines.append(f"既有摘要：{previous_text}")
    for index, (prefix, content) in enumerate(message_entries):
        item_budget = per_message_budget + (1 if index < remainder else 0)
        lines.append(f"{prefix}{compact_text(content, item_budget)}")
    return "\n".join(lines)


def compact_text(value: str, budget: int) -> str:
    if budget <= 0:
        return ""
    if len(value) <= budget:
        return value
    marker = "…[已压缩]…"
    if budget <= len(marker):
        return marker[:budget]
    remaining = budget - len(marker)
    head = (remaining + 1) // 2
    tail = remaining - head
    return f"{value[:head]}{marker}{value[-tail:] if tail else ''}"
