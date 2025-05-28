"""
Main orchestrator for the web scraping system.

This module coordinates all components and manages the scraping workflow.
"""

import asyncio
import sys
import signal
import time
from typing import List, Dict, Any, Optional
from datetime import datetime
import json
from pathlib import Path

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent.parent))

from src.config.settings import get_settings
from src.utils.logger import get_logger, get_performance_logger
from src.orchestrator.session_manager import SessionManager
from src.orchestrator.task_manager import TaskManager, TaskPriority
from src.orchestrator.data_aggregator import DataAggregator
from src.scrapers.book_scraper import BookScraper


class ScraperOrchestrator:
    """
    Main orchestrator that coordinates all scraping components.
    """
    
    def __init__(self):
        """Initialize the orchestrator."""
        self.settings = get_settings()
        self.logger = get_logger(__name__)
        self.perf_logger = get_performance_logger(__name__)
        
        # Initialize components
        self.session_manager = SessionManager()
        self.task_manager = TaskManager()
        self.data_aggregator = DataAggregator()
        
        # Worker management
        self.workers: List[asyncio.Task] = []
        self.running = False
        self.start_time = None
        
        # Setup signal handlers
        self._setup_signal_handlers()
        
        self.logger.info("ScraperOrchestrator initialized")
    
    def _setup_signal_handlers(self):
        """Setup graceful shutdown handlers."""
        def signal_handler(sig, frame):
            self.logger.info(f"Received signal {sig}, initiating shutdown...")
            asyncio.create_task(self.shutdown())
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    
    async def start(self):
        """Start the orchestration system."""
        self.logger.info("Starting scraper orchestrator...")
        self.running = True
        self.start_time = time.time()
        
        try:
            # Start data aggregator
            await self.data_aggregator.start()
            
            # Create tasks for all genres
            genres = self.settings.scraping.genres_to_scrape
            await self.task_manager.create_tasks_from_genres(genres)
            
            # Start worker coroutines
            num_workers = self.settings.scraping.max_concurrent_sessions
            for i in range(num_workers):
                worker = asyncio.create_task(self._worker_loop(f"worker-{i}"))
                self.workers.append(worker)
            
            self.logger.info(f"Started {num_workers} workers for {len(genres)} genres")
            
            # Start monitoring task
            monitor_task = asyncio.create_task(self._monitor_loop())
            
            # Wait for all tasks to complete or shutdown
            await self.task_manager.wait_for_completion()
            
            # Shutdown
            await self.shutdown()
            
        except Exception as e:
            self.logger.error(f"Fatal error in orchestrator: {e}")
            await self.shutdown()
            raise
    
    async def _worker_loop(self, worker_id: str):
        """
        Worker loop that processes scraping tasks.
        
        Args:
            worker_id: Unique worker identifier
        """
        self.logger.info(f"Worker {worker_id} started")
        
        while self.running:
            try:
                # Check if we can create a new session
                if not await self.session_manager.can_create_session():
                    await asyncio.sleep(1)
                    continue
                
                # Get next task
                task = await self.task_manager.get_next_task(worker_id)
                if not task:
                    # No tasks available
                    if await self.task_manager.get_pending_count() == 0:
                        # No more tasks, exit
                        break
                    await asyncio.sleep(1)
                    continue
                
                # Process the task
                await self._process_task(task, worker_id)
                
            except Exception as e:
                self.logger.error(f"Error in worker {worker_id}: {e}")
                await asyncio.sleep(5)
        
        self.logger.info(f"Worker {worker_id} stopped")
    
    async def _process_task(self, task, worker_id: str):
        """
        Process a single scraping task.
        
        Args:
            task: Task to process
            worker_id: Worker processing the task
        """
        session = None
        
        try:
            # Create session
            session = await self.session_manager.create_session(task.genre)
            
            # Start task
            await self.task_manager.start_task(task.task_id, session.session_id)
            await self.session_manager.start_session(session.session_id, container_id=worker_id)
            
            self.logger.info(f"Worker {worker_id} processing {task.genre} (session: {session.session_id})")
            
            # Create scraper instance
            scraper = BookScraper(
                session_id=session.session_id,
                genre=task.genre,
                container_id=worker_id
            )
            
            # Perform scraping
            with self.perf_logger.track_duration("scrape_genre", genre=task.genre):
                books = await scraper.scrape_genre()
            
            # Get scraper stats
            stats = scraper.get_stats()
            
            # Update session progress
            await self.session_manager.update_session_progress(
                session.session_id,
                books_scraped=stats['books_scraped'],
                pages_scraped=stats['pages_scraped']
            )
            
            # Add data to aggregator
            if books:
                await self.data_aggregator.add_data(books, session.session_id)
            
            # Complete task and session
            await self.task_manager.complete_task(task.task_id, result=stats)
            await self.session_manager.complete_session(session.session_id, stats)
            
            self.logger.info(
                f"Worker {worker_id} completed {task.genre}: "
                f"{len(books)} books in {stats['duration_seconds']:.2f}s"
            )
            
        except Exception as e:
            error_msg = f"Failed to process {task.genre}: {str(e)}"
            self.logger.error(error_msg)
            
            # Fail task (will retry if attempts remaining)
            await self.task_manager.fail_task(task.task_id, error_msg)
            
            # Fail session if it exists
            if session:
                await self.session_manager.fail_session(session.session_id, e)
    
    async def _monitor_loop(self):
        """Background loop for monitoring and reporting progress."""
        while self.running:
            try:
                # Get stats from all components
                session_stats = await self.session_manager.get_session_stats()
                task_stats = await self.task_manager.get_task_stats()
                aggregator_stats = self.data_aggregator.get_stats()
                
                # Calculate overall progress
                runtime = time.time() - self.start_time if self.start_time else 0
                
                # Log progress
                self.logger.info(
                    f"Progress Report - "
                    f"Runtime: {runtime:.0f}s | "
                    f"Active: {session_stats['active_sessions']} | "
                    f"Completed: {task_stats['completed_tasks']}/{task_stats['total_tasks']} | "
                    f"Books: {aggregator_stats['total_written']} | "
                    f"Buffer: {aggregator_stats['buffer_size']}"
                )
                
                # Clean up stale sessions
                await self.session_manager.cleanup_stale_sessions(
                    timeout_seconds=self.settings.scraping.session_timeout
                )
                
                # Wait before next check
                await asyncio.sleep(10)
                
            except Exception as e:
                self.logger.error(f"Error in monitor loop: {e}")
                await asyncio.sleep(10)
    
    async def shutdown(self):
        """Gracefully shutdown the orchestrator."""
        if not self.running:
            return
        
        self.logger.info("Initiating graceful shutdown...")
        self.running = False
        
        # Cancel all workers
        for worker in self.workers:
            worker.cancel()
        
        # Wait for workers to finish
        if self.workers:
            await asyncio.gather(*self.workers, return_exceptions=True)
        
        # Stop data aggregator
        await self.data_aggregator.stop()
        
        # Save final statistics
        await self._save_final_report()
        
        runtime = time.time() - self.start_time if self.start_time else 0
        self.logger.info(f"Orchestrator shutdown complete. Total runtime: {runtime:.2f}s")
    
    async def _save_final_report(self):
        """Save final scraping report."""
        try:
            # Gather all statistics
            session_stats = await self.session_manager.get_session_stats()
            task_stats = await self.task_manager.get_task_stats()
            aggregator_stats = self.data_aggregator.get_stats()
            
            # Create report
            report = {
                'timestamp': datetime.utcnow().isoformat(),
                'runtime_seconds': time.time() - self.start_time if self.start_time else 0,
                'sessions': session_stats,
                'tasks': task_stats,
                'data': aggregator_stats,
                'settings': {
                    'genres': self.settings.scraping.genres_to_scrape,
                    'max_concurrent_sessions': self.settings.scraping.max_concurrent_sessions,
                    'max_pages_per_genre': self.settings.scraping.max_pages_per_genre
                }
            }
            
            # Save to file
            report_file = self.settings.data.output_file_path.parent / 'scraping_report.json'
            with open(report_file, 'w') as f:
                json.dump(report, f, indent=2)
            
            self.logger.info(f"Final report saved to {report_file}")
            
            # Print summary
            print("\n" + "="*60)
            print("SCRAPING COMPLETED - SUMMARY")
            print("="*60)
            print(f"Total Runtime: {report['runtime_seconds']:.2f} seconds")
            print(f"Genres Scraped: {len(self.settings.scraping.genres_to_scrape)}")
            print(f"Total Books: {aggregator_stats['total_written']}")
            print(f"Success Rate: {(task_stats['completed_tasks']/task_stats['total_tasks']*100):.1f}%")
            print(f"Output File: {aggregator_stats['output_file']}")
            print("="*60)
            
        except Exception as e:
            self.logger.error(f"Failed to save final report: {e}")


async def main():
    """Main entry point for the scraping system."""
    print("="*60)
    print("WEB SCRAPING SYSTEM")
    print("="*60)
    print(f"Starting at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Configuration loaded from: .env")
    print("="*60)
    
    # Create and run orchestrator
    orchestrator = ScraperOrchestrator()
    
    try:
        await orchestrator.start()
    except KeyboardInterrupt:
        print("\nShutdown requested by user...")
    except Exception as e:
        print(f"\nError: {e}")
        raise
    finally:
        print("\nScraping system terminated.")


if __name__ == "__main__":
    # Run the main async function
    asyncio.run(main())