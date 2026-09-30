import os
import json
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

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
        self.base_dir.mkdir(parents=True, exist_ok=True)
        with open(self.metadata_file, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)

    def append_turn(self, user_prompt: str, agent_response: str, duration_sec: Optional[float] = None):
        self.turn_count += 1
        self.updated_at = datetime.now().isoformat()
        
        # Auto-title on first turn if generic title
        if self.turn_count == 1 and (self.title.startswith("Session ") or self.title == "New Session"):
            clean_first = user_prompt.strip().replace("\n", " ")
            self.title = clean_first[:45] + ("..." if len(clean_first) > 45 else "")

        self.save()

        # Append to human-readable transcript
        is_new_transcript = not self.transcript_file.exists()
        with open(self.transcript_file, "a", encoding="utf-8") as f:
            if is_new_transcript:
                f.write(f"# Session: {self.title}\n\n")
                f.write(f"- **ID:** `{self.session_id}`\n")
                f.write(f"- **Created:** {self.created_at}\n")
                if self.model:
                    f.write(f"- **Model:** `{self.model}`\n")
                f.write("\n---\n\n")

            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            timing = f" *(⏱ {duration_sec:.1f}s)*" if duration_sec is not None else ""
            f.write(f"### Turn {self.turn_count} — {now_str}{timing}\n\n")
            f.write(f"**You:**\n```text\n{user_prompt}\n```\n\n")
            f.write(f"**Gemma 4:**\n\n{agent_response}\n\n")
            f.write("---\n\n")

    def update_title(self, new_title: str):
        self.title = new_title
        self.updated_at = datetime.now().isoformat()
        self.save()


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

    def delete_session(self, session_id: str) -> bool:
        session = self.get_session(session_id)
        if session and session.base_dir.exists():
            shutil.rmtree(session.base_dir, ignore_errors=True)
            return True
        return False
