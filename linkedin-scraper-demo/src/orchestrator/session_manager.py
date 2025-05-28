"""
Session Manager for tracking and managing scraping sessions.

This module handles:
- Session lifecycle management
- Session state tracking
- Health monitoring
- Resource allocation
"""

import asyncio
import uuid
import time
from typing import Dict, List, Optional, Any
from datetime import datetime
from enum import Enum
from dataclasses import dataclass, field
import json
from pathlib import Path

from ..config.settings import get_settings
from ..utils.logger import get_logger, set_session_id


class SessionStatus(Enum):
    """Enum for session states."""
    PENDING = "pending"
    INITIALIZING = "initializing"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RECOVERING = "recovering"


@dataclass
class Session:
    """Data class representing a scraping session."""
    session_id: str
    genre: str
    status: SessionStatus
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    container_id: Optional[str] = None
    browser_id: Optional[str] = None
    
    # Tracking
    books_scraped: int = 0
    pages_scraped: int = 0
    errors: List[Dict[str, Any]] = field(default_factory=list)
    retries: int = 0
    
    # Checkpointing
    last_checkpoint: Optional[datetime] = None
    checkpoint_data: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert session to dictionary."""
        return {
            'session_id': self.session_id,
            'genre': self.genre,
            'status': self.status.value,
            'created_at': self.created_at.isoformat(),
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'container_id': self.container_id,
            'browser_id': self.browser_id,
            'books_scraped': self.books_scraped,
            'pages_scraped': self.pages_scraped,
            'errors': self.errors,
            'retries': self.retries,
            'last_checkpoint': self.last_checkpoint.isoformat() if self.last_checkpoint else None,
            'checkpoint_data': self.checkpoint_data
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Session':
        """Create session from dictionary."""
        return cls(
            session_id=data['session_id'],
            genre=data['genre'],
            status=SessionStatus(data['status']),
            created_at=datetime.fromisoformat(data['created_at']),
            started_at=datetime.fromisoformat(data['started_at']) if data.get('started_at') else None,
            completed_at=datetime.fromisoformat(data['completed_at']) if data.get('completed_at') else None,
            container_id=data.get('container_id'),
            browser_id=data.get('browser_id'),
            books_scraped=data.get('books_scraped', 0),
            pages_scraped=data.get('pages_scraped', 0),
            errors=data.get('errors', []),
            retries=data.get('retries', 0),
            last_checkpoint=datetime.fromisoformat(data['last_checkpoint']) if data.get('last_checkpoint') else None,
            checkpoint_data=data.get('checkpoint_data', {})
        )


class SessionManager:
    """
    Manages scraping sessions including lifecycle, state, and health monitoring.
    """
    
    def __init__(self):
        """Initialize the session manager."""
        self.settings = get_settings()
        self.logger = get_logger(__name__)
        
        # Session storage
        self.sessions: Dict[str, Session] = {}
        self._lock = asyncio.Lock()
        
        # Persistence
        self.checkpoint_dir = Path("checkpoints")
        self.checkpoint_dir.mkdir(exist_ok=True)
        
        # Load existing sessions from checkpoints
        self._load_checkpoints()
        
        self.logger.info("SessionManager initialized")
    
    async def create_session(self, genre: str) -> Session:
        """
        Create a new scraping session.
        
        Args:
            genre: The genre to scrape
            
        Returns:
            Created session object
        """
        session_id = f"{genre.lower()}-{uuid.uuid4().hex[:8]}"
        
        # Set session ID in logger context
        set_session_id(session_id)
        
        session = Session(
            session_id=session_id,
            genre=genre,
            status=SessionStatus.PENDING,
            created_at=datetime.utcnow()
        )
        
        async with self._lock:
            self.sessions[session_id] = session
        
        self.logger.info(f"Created session {session_id} for genre {genre}")
        
        # Save checkpoint
        await self._save_checkpoint(session)
        
        return session
    
    async def start_session(self, session_id: str, container_id: Optional[str] = None) -> Session:
        """
        Mark a session as started.
        
        Args:
            session_id: Session ID to start
            container_id: Optional container ID where session is running
            
        Returns:
            Updated session
        """
        session = await self.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        
        # Set session ID in logger context
        set_session_id(session_id)
        
        async with self._lock:
            session.status = SessionStatus.RUNNING
            session.started_at = datetime.utcnow()
            session.container_id = container_id
        
        self.logger.info(f"Started session {session_id}")
        
        # Save checkpoint
        await self._save_checkpoint(session)
        
        return session
    
    async def update_session_progress(
        self, 
        session_id: str, 
        books_scraped: Optional[int] = None,
        pages_scraped: Optional[int] = None,
        checkpoint_data: Optional[Dict[str, Any]] = None
    ) -> Session:
        """
        Update session progress.
        
        Args:
            session_id: Session ID to update
            books_scraped: Number of books scraped
            pages_scraped: Number of pages scraped
            checkpoint_data: Additional checkpoint data
            
        Returns:
            Updated session
        """
        session = await self.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        
        async with self._lock:
            if books_scraped is not None:
                session.books_scraped = books_scraped
            if pages_scraped is not None:
                session.pages_scraped = pages_scraped
            if checkpoint_data:
                session.checkpoint_data.update(checkpoint_data)
            
            session.last_checkpoint = datetime.utcnow()
        
        # Save checkpoint
        await self._save_checkpoint(session)
        
        return session
    
    async def complete_session(
        self, 
        session_id: str, 
        stats: Optional[Dict[str, Any]] = None
    ) -> Session:
        """
        Mark a session as completed.
        
        Args:
            session_id: Session ID to complete
            stats: Final statistics
            
        Returns:
            Updated session
        """
        session = await self.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        
        # Set session ID in logger context
        set_session_id(session_id)
        
        async with self._lock:
            session.status = SessionStatus.COMPLETED
            session.completed_at = datetime.utcnow()
            
            if stats:
                session.books_scraped = stats.get('books_scraped', session.books_scraped)
                session.pages_scraped = stats.get('pages_scraped', session.pages_scraped)
        
        duration = (session.completed_at - session.started_at).total_seconds() if session.started_at else 0
        
        self.logger.info(
            f"Completed session {session_id}: "
            f"{session.books_scraped} books in {duration:.2f} seconds"
        )
        
        # Save final checkpoint
        await self._save_checkpoint(session)
        
        # Remove checkpoint file since session is complete
        checkpoint_file = self.checkpoint_dir / f"{session_id}.json"
        if checkpoint_file.exists():
            checkpoint_file.unlink()
        
        return session
    
    async def fail_session(self, session_id: str, error: Exception) -> Session:
        """
        Mark a session as failed.
        
        Args:
            session_id: Session ID that failed
            error: The error that caused the failure
            
        Returns:
            Updated session
        """
        session = await self.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        
        # Set session ID in logger context
        set_session_id(session_id)
        
        async with self._lock:
            session.status = SessionStatus.FAILED
            session.completed_at = datetime.utcnow()
            session.errors.append({
                'timestamp': datetime.utcnow().isoformat(),
                'error_type': type(error).__name__,
                'error_message': str(error)
            })
        
        self.logger.error(f"Session {session_id} failed: {error}")
        
        # Save checkpoint for potential recovery
        await self._save_checkpoint(session)
        
        return session
    
    async def get_session(self, session_id: str) -> Optional[Session]:
        """Get a session by ID."""
        async with self._lock:
            return self.sessions.get(session_id)
    
    async def get_active_sessions(self) -> List[Session]:
        """Get all active (running) sessions."""
        async with self._lock:
            return [
                session for session in self.sessions.values()
                if session.status == SessionStatus.RUNNING
            ]
    
    async def get_all_sessions(self) -> List[Session]:
        """Get all sessions."""
        async with self._lock:
            return list(self.sessions.values())
    
    async def get_session_stats(self) -> Dict[str, Any]:
        """Get overall session statistics."""
        async with self._lock:
            sessions = list(self.sessions.values())
        
        total = len(sessions)
        by_status = {}
        for session in sessions:
            status = session.status.value
            by_status[status] = by_status.get(status, 0) + 1
        
        total_books = sum(s.books_scraped for s in sessions)
        total_pages = sum(s.pages_scraped for s in sessions)
        
        return {
            'total_sessions': total,
            'by_status': by_status,
            'total_books_scraped': total_books,
            'total_pages_scraped': total_pages,
            'active_sessions': len([s for s in sessions if s.status == SessionStatus.RUNNING])
        }
    
    async def can_create_session(self) -> bool:
        """Check if we can create a new session based on concurrency limits."""
        active_sessions = await self.get_active_sessions()
        return len(active_sessions) < self.settings.scraping.max_concurrent_sessions
    
    async def cleanup_stale_sessions(self, timeout_seconds: int = 300):
        """
        Clean up sessions that have been running too long.
        
        Args:
            timeout_seconds: Maximum time a session should run
        """
        current_time = datetime.utcnow()
        stale_sessions = []
        
        async with self._lock:
            for session in self.sessions.values():
                if session.status == SessionStatus.RUNNING and session.started_at:
                    runtime = (current_time - session.started_at).total_seconds()
                    if runtime > timeout_seconds:
                        stale_sessions.append(session)
        
        for session in stale_sessions:
            self.logger.warning(f"Cleaning up stale session {session.session_id}")
            await self.fail_session(
                session.session_id, 
                TimeoutError(f"Session exceeded timeout of {timeout_seconds} seconds")
            )
    
    async def _save_checkpoint(self, session: Session):
        """Save session checkpoint to disk."""
        checkpoint_file = self.checkpoint_dir / f"{session.session_id}.json"
        
        try:
            with open(checkpoint_file, 'w') as f:
                json.dump(session.to_dict(), f, indent=2)
        except Exception as e:
            self.logger.error(f"Failed to save checkpoint for {session.session_id}: {e}")
    
    def _load_checkpoints(self):
        """Load existing session checkpoints from disk."""
        checkpoint_files = list(self.checkpoint_dir.glob("*.json"))
        
        for checkpoint_file in checkpoint_files:
            try:
                with open(checkpoint_file, 'r') as f:
                    data = json.load(f)
                
                session = Session.from_dict(data)
                
                # Only load incomplete sessions
                if session.status in [SessionStatus.PENDING, SessionStatus.RUNNING]:
                    # Mark as recovering
                    session.status = SessionStatus.RECOVERING
                    self.sessions[session.session_id] = session
                    self.logger.info(f"Loaded checkpoint for session {session.session_id}")
                
            except Exception as e:
                self.logger.error(f"Failed to load checkpoint {checkpoint_file}: {e}")
    
    async def recover_session(self, session_id: str) -> Optional[Session]:
        """
        Attempt to recover a failed or interrupted session.
        
        Args:
            session_id: Session ID to recover
            
        Returns:
            Recovered session or None if recovery not possible
        """
        session = await self.get_session(session_id)
        if not session or session.status != SessionStatus.RECOVERING:
            return None
        
        self.logger.info(f"Attempting to recover session {session_id}")
        
        # Update session status
        async with self._lock:
            session.status = SessionStatus.PENDING
            session.retries += 1
        
        return session