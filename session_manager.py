import os
import json
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

def safe_code_block(text: str) -> str:
    """Wraps text in a markdown code block with enough backticks to avoid collision."""
    count = 3
    while ("`" * count) in text:
        count += 1
    fence = "`" * count
    return f"{fence}text\n{text}\n{fence}"

class Session:
    def __init__(
        self,
        session_id: str,
        title: str,
        created_at: str,
        updated_at: str,
        turn_count: int = 0,
        model: str = "",
        base_dir: Optional[Path] = None,
    ):
        self.session_id = session_id
        self.title = title
        self.created_at = created_at
        self.updated_at = updated_at
        self.turn_count = turn_count
        self.model = model
        self.base_dir = base_dir or (Path(__file__).parent / "sessions" / session_id)

    @property
    def dir(self) -> Path:
        return self.base_dir

    @property
    def conversation_dir(self) -> Path:
        p = self.base_dir / "conversation"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def app_data_dir(self) -> Path:
        p = self.base_dir / "app_data"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def metadata_file(self) -> Path:
        return self.base_dir / "metadata.json"

    @property
    def transcript_file(self) -> Path:
        return self.base_dir / "transcript.md"

    @property
    def events_file(self) -> Path:
        return self.base_dir / "events.jsonl"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "title": self.title,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "turn_count": self.turn_count,
            "model": self.model,
        }

    def save(self):
        """Atomic write for metadata.json using a temp file + os.replace to prevent corruption."""
        self.base_dir.mkdir(parents=True, exist_ok=True)
        tmp_file = self.metadata_file.with_suffix(".tmp")
        try:
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(self.to_dict(), f, indent=2)
            os.replace(tmp_file, self.metadata_file)
        except Exception:
            if tmp_file.exists():
                tmp_file.unlink(missing_ok=True)
            raise

    def log_event(self, event_type: str, data: Dict[str, Any]):
        """Appends a structured event to events.jsonl."""
        self.base_dir.mkdir(parents=True, exist_ok=True)
        event = {
            "timestamp": datetime.now().isoformat(),
            "session_id": self.session_id,
            "event": event_type,
            **data,
        }
        with open(self.events_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")

    def _ensure_transcript_header(self):
        if not self.transcript_file.exists():
            with open(self.transcript_file, "w", encoding="utf-8") as f:
                f.write(f"# Session: {self.title}\n\n")
                f.write(f"- **ID:** `{self.session_id}`\n")
                f.write(f"- **Created:** {self.created_at}\n")
                if self.model:
                    f.write(f"- **Model:** `{self.model}`\n")
                f.write("\n---\n\n")

    def append_turn(self, user_prompt: str, agent_response: str, duration_sec: Optional[float] = None):
        """Appends a completed conversation turn to transcript.md and events.jsonl."""
        self.turn_count += 1
        self.updated_at = datetime.now().isoformat()
        
        # Auto-title on first turn if default title
        if self.turn_count == 1 and (self.title.startswith("Session ") or self.title == "New Session"):
            clean_first = user_prompt.strip().replace("\n", " ")
            self.title = clean_first[:45] + ("..." if len(clean_first) > 45 else "")

        self.save()
        self._ensure_transcript_header()

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        timing = f" *(⏱ {duration_sec:.1f}s)*" if duration_sec is not None else ""
        prompt_block = safe_code_block(user_prompt)

        with open(self.transcript_file, "a", encoding="utf-8") as f:
            f.write(f"### Turn {self.turn_count} — {now_str}{timing}\n\n")
            f.write(f"**You:**\n{prompt_block}\n\n")
            f.write(f"**Gemma 4:**\n\n{agent_response}\n\n")
            f.write("---\n\n")

        self.log_event("turn_complete", {
            "turn": self.turn_count,
            "prompt": user_prompt,
            "response": agent_response,
            "duration_sec": duration_sec,
        })

    def append_interrupted_turn(self, user_prompt: str, partial_response: str, duration_sec: Optional[float] = None):
        """Preserves partial output when user presses Ctrl+C mid-generation."""
        self.turn_count += 1
        self.updated_at = datetime.now().isoformat()
        self.save()
        self._ensure_transcript_header()

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        timing = f" *(⏱ {duration_sec:.1f}s - Interrupted)*" if duration_sec is not None else " *(Interrupted)*"
        prompt_block = safe_code_block(user_prompt)
        content = partial_response.strip() or "*(No output produced before interruption)*"

        with open(self.transcript_file, "a", encoding="utf-8") as f:
            f.write(f"### Turn {self.turn_count} — {now_str}{timing}\n\n")
            f.write(f"**You:**\n{prompt_block}\n\n")
            f.write(f"**Gemma 4 (Partial):**\n\n{content}\n\n> ⚠️ *Turn interrupted by user (Ctrl+C)*\n\n")
            f.write("---\n\n")

        self.log_event("turn_interrupted", {
            "turn": self.turn_count,
            "prompt": user_prompt,
            "partial_response": partial_response,
            "duration_sec": duration_sec,
        })

    def log_tool_call(self, name: str, args: Dict[str, Any], duration_sec: float, allowed: bool, error: Optional[str] = None):
        """Logs structured tool execution to events.jsonl and a concise block in transcript.md."""
        self.log_event("tool_call", {
            "turn": self.turn_count + 1,
            "tool_name": name,
            "args": args,
            "allowed": allowed,
            "duration_sec": duration_sec,
            "error": error,
        })
        self._ensure_transcript_header()
        status_icon = "✓" if allowed and not error else "✗"
        err_msg = f" (Error: {error})" if error else ""
        with open(self.transcript_file, "a", encoding="utf-8") as f:
            f.write(f"> `{status_icon} Tool:` **{name}** `({duration_sec:.2f}s)`{err_msg}\n")

    def update_title(self, new_title: str):
        self.title = new_title
        self.updated_at = datetime.now().isoformat()
        self.save()
        self.log_event("session_renamed", {"new_title": new_title})


class SessionManager:
    def __init__(self, root_dir: Optional[str] = None):
        if root_dir:
            self.sessions_dir = Path(root_dir) / "sessions"
        else:
            self.sessions_dir = Path(__file__).parent / "sessions"
        self.sessions_dir.mkdir(parents=True, exist_ok=True)

    def create_session(self, title: Optional[str] = None, model: str = "") -> Session:
        now = datetime.now()
        # SDK requires conversation_id >= 32 chars matching [a-zA-Z0-9-]
        session_id = f"{now.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4()}"
        session_title = title or f"Session {now.strftime('%b %d, %H:%M')}"
        now_iso = now.isoformat()
        session = Session(
            session_id=session_id,
            title=session_title,
            created_at=now_iso,
            updated_at=now_iso,
            turn_count=0,
            model=model,
            base_dir=self.sessions_dir / session_id,
        )
        session.save()
        session.log_event("session_created", {"title": session.title, "model": model})
        return session

    def get_session(self, session_id: str) -> Optional[Session]:
        session_path = self.sessions_dir / session_id
        if not session_path.exists():
            # Try fuzzy/prefix match
            matches = [p for p in self.sessions_dir.iterdir() if p.is_dir() and p.name.startswith(session_id)]
            if len(matches) == 1:
                session_path = matches[0]
            else:
                return None

        meta_file = session_path / "metadata.json"
        if not meta_file.exists():
            return None

        try:
            with open(meta_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return Session(
                session_id=data.get("session_id", session_path.name),
                title=data.get("title", session_path.name),
                created_at=data.get("created_at", ""),
                updated_at=data.get("updated_at", ""),
                turn_count=data.get("turn_count", 0),
                model=data.get("model", ""),
                base_dir=session_path,
            )
        except Exception:
            return None

    def resolve_session(self, query: str) -> Optional[Session]:
        """Resolves a session by 1-based index number, session ID (exact or prefix), or title."""
        query = str(query).strip()
        if not query:
            return None
        sessions = self.list_sessions()
        # 1. 1-based numeric index (e.g. '1', '2')
        if query.isdigit():
            idx = int(query) - 1
            if 0 <= idx < len(sessions):
                return sessions[idx]
            return None
        # 2. 'latest' keyword
        if query.lower() == "latest":
            return sessions[0] if sessions else None
        # 3. ID match (exact or prefix)
        target = self.get_session(query)
        if target:
            return target
        # 4. Case-insensitive title match
        title_matches = [s for s in sessions if query.lower() in s.title.lower()]
        if len(title_matches) == 1:
            return title_matches[0]
        return None

    def list_sessions(self) -> List[Session]:
        sessions = []
        if not self.sessions_dir.exists():
            return sessions

        for path in self.sessions_dir.iterdir():
            if path.is_dir():
                s = self.get_session(path.name)
                if s:
                    sessions.append(s)

        # Sort descending by updated_at or created_at
        sessions.sort(key=lambda s: s.updated_at or s.created_at, reverse=True)
        return sessions

    def get_latest_session(self) -> Optional[Session]:
        sessions = self.list_sessions()
        return sessions[0] if sessions else None

    def delete_session(self, identifier: str) -> bool:
        """Deletes a session resolved by number, ID, or title."""
        session = self.resolve_session(identifier) if identifier.isdigit() else self.get_session(identifier)
        if session and session.base_dir.exists():
            shutil.rmtree(session.base_dir, ignore_errors=True)
            return True
        return False
