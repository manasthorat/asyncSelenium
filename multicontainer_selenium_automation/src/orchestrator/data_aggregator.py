"""
Data Aggregator for collecting and managing scraped data.

This module handles:
- Centralized data collection from all scrapers
- Data buffering and batch writing
- CSV file management
- Data validation and deduplication
"""

import asyncio
import csv
import time
from typing import Dict, List, Any, Optional
from datetime import datetime
from pathlib import Path
import json
from collections import defaultdict
import threading

from ..config.settings import get_settings
from ..utils.logger import get_logger, get_performance_logger


class DataAggregator:
    """
    Aggregates scraped data from multiple sources and writes to CSV.
    """
    
    def __init__(self):
        """Initialize the data aggregator."""
        self.settings = get_settings()
        self.logger = get_logger(__name__)
        self.perf_logger = get_performance_logger(__name__)
        
        # Data queues and buffers
        self.data_queue: asyncio.Queue = asyncio.Queue()
        self.buffer: List[Dict[str, Any]] = []
        self.buffer_lock = threading.Lock()
        
        # Deduplication
        self.seen_books: set = set()  # Track by title + genre
        
        # Statistics
        self.stats = {
            'total_received': 0,
            'total_written': 0,
            'duplicates_skipped': 0,
            'write_operations': 0,
            'errors': 0,
            'by_genre': defaultdict(int),
            'by_session': defaultdict(int)
        }
        
        # File management
        self.output_file = self.settings.data.output_file_path
        self.temp_file = self.output_file.with_suffix('.tmp')
        
        # Initialize CSV file with headers
        self._initialize_csv()
        
        # Background tasks
        self.writer_task: Optional[asyncio.Task] = None
        self.last_write_time = time.time()
        
        self.logger.info(f"DataAggregator initialized, output: {self.output_file}")
    
    def _initialize_csv(self):
        """Initialize CSV file with headers."""
        try:
            # Create output directory if it doesn't exist
            self.output_file.parent.mkdir(parents=True, exist_ok=True)
            
            # Write headers if file doesn't exist
            if not self.output_file.exists():
                with open(self.output_file, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.DictWriter(f, fieldnames=self.settings.data.csv_columns)
                    writer.writeheader()
                
                self.logger.info("Created CSV file with headers")
        
        except Exception as e:
            self.logger.error(f"Failed to initialize CSV: {e}")
            raise
    
    async def start(self):
        """Start the background writer task."""
        if not self.writer_task:
            self.writer_task = asyncio.create_task(self._writer_loop())
            self.logger.info("Started data aggregator writer task")
    
    async def stop(self):
        """Stop the aggregator and flush remaining data."""
        self.logger.info("Stopping data aggregator...")
        
        # Flush remaining data
        await self._flush_buffer()
        
        # Cancel writer task
        if self.writer_task:
            self.writer_task.cancel()
            try:
                await self.writer_task
            except asyncio.CancelledError:
                pass
        
        self.logger.info("Data aggregator stopped")
    
    async def add_data(self, data: List[Dict[str, Any]], session_id: str):
        """
        Add scraped data to the aggregation queue.
        
        Args:
            data: List of book dictionaries
            session_id: Session that produced the data
        """
        for item in data:
            # Add tracking info
            item['processed_at'] = datetime.utcnow().isoformat()
            
            # Create deduplication key
            dedup_key = f"{item.get('title', '')}_{item.get('genre', '')}"
            
            # Check for duplicates
            if dedup_key in self.seen_books:
                self.stats['duplicates_skipped'] += 1
                self.logger.debug(f"Skipping duplicate: {dedup_key}")
                continue
            
            # Add to queue
            await self.data_queue.put(item)
            self.seen_books.add(dedup_key)
            
            # Update stats
            self.stats['total_received'] += 1
            self.stats['by_genre'][item.get('genre', 'unknown')] += 1
            self.stats['by_session'][session_id] += 1
        
        self.logger.info(
            f"Added {len(data)} items from session {session_id} "
            f"({self.stats['duplicates_skipped']} duplicates skipped)"
        )
    
    async def _writer_loop(self):
        """Background loop for processing data queue and writing to CSV."""
        self.logger.info("Writer loop started")
        
        try:
            while True:
                # Collect items from queue
                items_collected = 0
                deadline = time.time() + 1.0  # Collect for up to 1 second
                
                while time.time() < deadline:
                    try:
                        item = await asyncio.wait_for(
                            self.data_queue.get(), 
                            timeout=0.1
                        )
                        
                        with self.buffer_lock:
                            self.buffer.append(item)
                        items_collected += 1
                        
                    except asyncio.TimeoutError:
                        break
                
                # Check if we should write
                should_write = False
                current_time = time.time()
                
                with self.buffer_lock:
                    buffer_size = len(self.buffer)
                
                # Write conditions
                if buffer_size >= self.settings.data.buffer_size:
                    should_write = True
                    self.logger.debug(f"Buffer full ({buffer_size} items), writing...")
                
                elif buffer_size > 0 and (current_time - self.last_write_time) >= self.settings.data.write_interval:
                    should_write = True
                    self.logger.debug(f"Write interval reached, writing {buffer_size} items...")
                
                # Write if needed
                if should_write:
                    await self._flush_buffer()
                
                # Short sleep to prevent CPU spinning
                await asyncio.sleep(0.1)
        
        except asyncio.CancelledError:
            self.logger.info("Writer loop cancelled")
            raise
        except Exception as e:
            self.logger.error(f"Error in writer loop: {e}")
            raise
    
    async def _flush_buffer(self):
        """Flush buffer to CSV file."""
        with self.buffer_lock:
            if not self.buffer:
                return
            
            items_to_write = self.buffer.copy()
            self.buffer.clear()
        
        if not items_to_write:
            return
        
        with self.perf_logger.track_duration("csv_write", items=len(items_to_write)):
            try:
                # Write to temporary file first (atomic write)
                with open(self.temp_file, 'a', newline='', encoding='utf-8') as f:
                    writer = csv.DictWriter(
                        f, 
                        fieldnames=self.settings.data.csv_columns,
                        extrasaction='ignore'  # Ignore extra fields
                    )
                    
                    for item in items_to_write:
                        # Ensure all required fields are present
                        row = {col: item.get(col, '') for col in self.settings.data.csv_columns}
                        writer.writerow(row)
                
                # Append temp file contents to main file
                with open(self.temp_file, 'r', encoding='utf-8') as temp_f:
                    with open(self.output_file, 'a', encoding='utf-8') as main_f:
                        main_f.write(temp_f.read())
                
                # Clear temp file
                self.temp_file.unlink(missing_ok=True)
                
                # Update stats
                self.stats['total_written'] += len(items_to_write)
                self.stats['write_operations'] += 1
                self.last_write_time = time.time()
                
                self.logger.info(
                    f"Wrote {len(items_to_write)} items to CSV "
                    f"(total: {self.stats['total_written']})"
                )
            
            except Exception as e:
                self.logger.error(f"Failed to write to CSV: {e}")
                self.stats['errors'] += 1
                
                # Re-add items to buffer on failure
                with self.buffer_lock:
                    self.buffer.extend(items_to_write)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get aggregator statistics."""
        with self.buffer_lock:
            buffer_size = len(self.buffer)
        
        return {
            'total_received': self.stats['total_received'],
            'total_written': self.stats['total_written'],
            'buffer_size': buffer_size,
            'duplicates_skipped': self.stats['duplicates_skipped'],
            'write_operations': self.stats['write_operations'],
            'errors': self.stats['errors'],
            'by_genre': dict(self.stats['by_genre']),
            'by_session': dict(self.stats['by_session']),
            'output_file': str(self.output_file),
            'file_size_mb': round(self.output_file.stat().st_size / 1024 / 1024, 2) if self.output_file.exists() else 0
        }
    
    async def get_sample_data(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Get a sample of recently written data."""
        try:
            # Read last few lines from CSV
            with open(self.output_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                all_rows = list(reader)
                return all_rows[-limit:] if len(all_rows) > limit else all_rows
        except Exception as e:
            self.logger.error(f"Failed to read sample data: {e}")
            return []
    
    def save_stats(self, filepath: Optional[Path] = None):
        """Save statistics to a JSON file."""
        if not filepath:
            filepath = self.output_file.with_name('aggregator_stats.json')
        
        try:
            stats = self.get_stats()
            stats['timestamp'] = datetime.utcnow().isoformat()
            
            with open(filepath, 'w') as f:
                json.dump(stats, f, indent=2)
            
            self.logger.info(f"Saved stats to {filepath}")
        
        except Exception as e:
            self.logger.error(f"Failed to save stats: {e}")