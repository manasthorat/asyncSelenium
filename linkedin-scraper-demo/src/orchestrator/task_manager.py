"""
Task Manager for distributing and managing scraping tasks.

This module handles:
- Task queue management
- Task distribution to workers
- Retry logic
- Priority handling
"""

import asyncio
import time
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import uuid
from queue import PriorityQueue

from ..config.settings import get_settings
from ..utils.logger import get_logger


class TaskPriority(Enum):
    """Task priority levels."""
    HIGH = 1
    NORMAL = 2
    LOW = 3


class TaskStatus(Enum):
    """Task status states."""
    PENDING = "pending"
    ASSIGNED = "assigned"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class Task:
    """Represents a scraping task."""
    task_id: str
    genre: str
    priority: TaskPriority
    status: TaskStatus
    created_at: datetime
    session_id: Optional[str] = None
    assigned_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    attempts: int = 0
    max_attempts: int = 3
    error: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    
    def __lt__(self, other):
        """Compare tasks by priority for priority queue."""
        return self.priority.value < other.priority.value


class TaskManager:
    """
    Manages task queue and distribution for scraping operations.
    """
    
    def __init__(self):
        """Initialize the task manager."""
        self.settings = get_settings()
        self.logger = get_logger(__name__)
        
        # Task queues
        self.pending_queue: asyncio.Queue = asyncio.Queue()
        self.priority_queue: PriorityQueue = PriorityQueue()
        
        # Task storage
        self.tasks: Dict[str, Task] = {}
        self._lock = asyncio.Lock()
        
        # Worker tracking
        self.active_workers: Dict[str, Task] = {}
        
        # Statistics
        self.stats = {
            'total_tasks': 0,
            'completed_tasks': 0,
            'failed_tasks': 0,
            'total_retries': 0
        }
        
        self.logger.info("TaskManager initialized")
    
    async def create_task(
        self, 
        genre: str, 
        priority: TaskPriority = TaskPriority.NORMAL
    ) -> Task:
        """
        Create a new scraping task.
        
        Args:
            genre: Genre to scrape
            priority: Task priority
            
        Returns:
            Created task
        """
        task_id = f"task-{uuid.uuid4().hex[:8]}"
        
        task = Task(
            task_id=task_id,
            genre=genre,
            priority=priority,
            status=TaskStatus.PENDING,
            created_at=datetime.utcnow(),
            max_attempts=self.settings.scraping.max_retries
        )
        
        async with self._lock:
            self.tasks[task_id] = task
            self.stats['total_tasks'] += 1
        
        # Add to appropriate queue
        if priority == TaskPriority.HIGH:
            self.priority_queue.put((priority.value, task))
        else:
            await self.pending_queue.put(task)
        
        self.logger.info(f"Created task {task_id} for genre {genre} with priority {priority.name}")
        
        return task
    
    async def create_tasks_from_genres(
        self, 
        genres: List[str], 
        priority: TaskPriority = TaskPriority.NORMAL
    ) -> List[Task]:
        """
        Create tasks for multiple genres.
        
        Args:
            genres: List of genres to create tasks for
            priority: Priority for all tasks
            
        Returns:
            List of created tasks
        """
        tasks = []
        for genre in genres:
            task = await self.create_task(genre, priority)
            tasks.append(task)
        
        self.logger.info(f"Created {len(tasks)} tasks for genres: {genres}")
        return tasks
    
    async def get_next_task(self, worker_id: str) -> Optional[Task]:
        """
        Get the next available task for a worker.
        
        Args:
            worker_id: ID of the requesting worker
            
        Returns:
            Next task or None if no tasks available
        """
        task = None
        
        # First check priority queue
        if not self.priority_queue.empty():
            try:
                _, task = self.priority_queue.get_nowait()
            except:
                pass
        
        # Then check regular queue
        if not task:
            try:
                task = await asyncio.wait_for(
                    self.pending_queue.get(), 
                    timeout=1.0
                )
            except asyncio.TimeoutError:
                return None
        
        if task:
            async with self._lock:
                task.status = TaskStatus.ASSIGNED
                task.assigned_at = datetime.utcnow()
                self.active_workers[worker_id] = task
            
            self.logger.info(f"Assigned task {task.task_id} to worker {worker_id}")
        
        return task
    
    async def start_task(self, task_id: str, session_id: str) -> Task:
        """
        Mark a task as started.
        
        Args:
            task_id: Task ID
            session_id: Associated session ID
            
        Returns:
            Updated task
        """
        async with self._lock:
            task = self.tasks.get(task_id)
            if not task:
                raise ValueError(f"Task {task_id} not found")
            
            task.status = TaskStatus.RUNNING
            task.started_at = datetime.utcnow()
            task.session_id = session_id
            task.attempts += 1
        
        self.logger.info(f"Started task {task_id} (attempt {task.attempts}/{task.max_attempts})")
        
        return task
    
    async def complete_task(
        self, 
        task_id: str, 
        result: Optional[Dict[str, Any]] = None
    ) -> Task:
        """
        Mark a task as completed.
        
        Args:
            task_id: Task ID
            result: Task result data
            
        Returns:
            Updated task
        """
        async with self._lock:
            task = self.tasks.get(task_id)
            if not task:
                raise ValueError(f"Task {task_id} not found")
            
            task.status = TaskStatus.COMPLETED
            task.completed_at = datetime.utcnow()
            task.result = result
            
            # Update stats
            self.stats['completed_tasks'] += 1
            
            # Remove from active workers
            worker_id = None
            for wid, active_task in self.active_workers.items():
                if active_task.task_id == task_id:
                    worker_id = wid
                    break
            if worker_id:
                del self.active_workers[worker_id]
        
        duration = (task.completed_at - task.started_at).total_seconds() if task.started_at else 0
        self.logger.info(f"Completed task {task_id} in {duration:.2f} seconds")
        
        return task
    
    async def fail_task(
        self, 
        task_id: str, 
        error: str,
        retry: bool = True
    ) -> Task:
        """
        Mark a task as failed and optionally retry.
        
        Args:
            task_id: Task ID
            error: Error message
            retry: Whether to retry the task
            
        Returns:
            Updated task
        """
        async with self._lock:
            task = self.tasks.get(task_id)
            if not task:
                raise ValueError(f"Task {task_id} not found")
            
            task.error = error
            
            # Remove from active workers
            worker_id = None
            for wid, active_task in self.active_workers.items():
                if active_task.task_id == task_id:
                    worker_id = wid
                    break
            if worker_id:
                del self.active_workers[worker_id]
            
            # Check if we should retry
            if retry and task.attempts < task.max_attempts:
                task.status = TaskStatus.PENDING
                task.assigned_at = None
                task.started_at = None
                self.stats['total_retries'] += 1
                
                # Re-queue with higher priority
                self.priority_queue.put((TaskPriority.HIGH.value, task))
                
                self.logger.warning(
                    f"Task {task_id} failed (attempt {task.attempts}/{task.max_attempts}), "
                    f"retrying: {error}"
                )
            else:
                task.status = TaskStatus.FAILED
                task.completed_at = datetime.utcnow()
                self.stats['failed_tasks'] += 1
                
                self.logger.error(f"Task {task_id} failed permanently: {error}")
        
        return task
    
    async def cancel_task(self, task_id: str) -> Task:
        """
        Cancel a task.
        
        Args:
            task_id: Task ID to cancel
            
        Returns:
            Updated task
        """
        async with self._lock:
            task = self.tasks.get(task_id)
            if not task:
                raise ValueError(f"Task {task_id} not found")
            
            task.status = TaskStatus.CANCELLED
            task.completed_at = datetime.utcnow()
        
        self.logger.info(f"Cancelled task {task_id}")
        
        return task
    
    async def get_task(self, task_id: str) -> Optional[Task]:
        """Get a task by ID."""
        async with self._lock:
            return self.tasks.get(task_id)
    
    async def get_pending_count(self) -> int:
        """Get count of pending tasks."""
        return self.pending_queue.qsize() + self.priority_queue.qsize()
    
    async def get_active_tasks(self) -> List[Task]:
        """Get all active (running) tasks."""
        async with self._lock:
            return [
                task for task in self.tasks.values()
                if task.status == TaskStatus.RUNNING
            ]
    
    async def get_task_stats(self) -> Dict[str, Any]:
        """Get task statistics."""
        async with self._lock:
            tasks = list(self.tasks.values())
            stats = self.stats.copy()
        
        # Count by status
        by_status = {}
        for task in tasks:
            status = task.status.value
            by_status[status] = by_status.get(status, 0) + 1
        
        # Average completion time
        completed_tasks = [t for t in tasks if t.status == TaskStatus.COMPLETED]
        if completed_tasks:
            total_time = sum(
                (t.completed_at - t.started_at).total_seconds()
                for t in completed_tasks
                if t.started_at and t.completed_at
            )
            avg_time = total_time / len(completed_tasks)
        else:
            avg_time = 0
        
        stats.update({
            'by_status': by_status,
            'pending_count': await self.get_pending_count(),
            'active_workers': len(self.active_workers),
            'average_completion_time': round(avg_time, 2)
        })
        
        return stats
    
    async def wait_for_completion(self, timeout: Optional[float] = None) -> bool:
        """
        Wait for all tasks to complete.
        
        Args:
            timeout: Maximum time to wait
            
        Returns:
            True if all tasks completed, False if timeout
        """
        start_time = time.time()
        
        while True:
            async with self._lock:
                pending = [
                    t for t in self.tasks.values()
                    if t.status in [TaskStatus.PENDING, TaskStatus.ASSIGNED, TaskStatus.RUNNING]
                ]
            
            if not pending:
                return True
            
            if timeout and (time.time() - start_time) > timeout:
                return False
            
            await asyncio.sleep(1)
    
    def release_worker(self, worker_id: str):
        """Release a worker from active workers."""
        if worker_id in self.active_workers:
            del self.active_workers[worker_id]