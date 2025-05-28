"""
Test script for Phase 2 components.
"""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.append(str(Path(__file__).parent))

from src.config.settings import get_settings
from src.utils.logger import get_logger
from src.orchestrator.session_manager import SessionManager
from src.orchestrator.task_manager import TaskManager, TaskPriority
from src.orchestrator.data_aggregator import DataAggregator
from src.scrapers.book_scraper import BookScraper


async def test_components():
    """Test all Phase 2 components."""
    
    print("="*60)
    print("PHASE 2 COMPONENT TEST")
    print("="*60)
    
    logger = get_logger(__name__)
    settings = get_settings()
    
    # Test 1: Session Manager
    print("\n1. Testing Session Manager...")
    try:
        session_manager = SessionManager()
        
        # Create a test session
        session = await session_manager.create_session("TestGenre")
        print(f"   ✓ Created session: {session.session_id}")
        
        # Start session
        await session_manager.start_session(session.session_id)
        print(f"   ✓ Started session")
        
        # Update progress
        await session_manager.update_session_progress(
            session.session_id,
            books_scraped=10,
            pages_scraped=2
        )
        print(f"   ✓ Updated session progress")
        
        # Get stats
        stats = await session_manager.get_session_stats()
        print(f"   ✓ Session stats: {stats}")
        
    except Exception as e:
        print(f"   ✗ Session Manager Error: {e}")
        return False
    
    # Test 2: Task Manager
    print("\n2. Testing Task Manager...")
    try:
        task_manager = TaskManager()
        
        # Create tasks
        tasks = await task_manager.create_tasks_from_genres(
            ["Fiction", "Mystery"], 
            TaskPriority.NORMAL
        )
        print(f"   ✓ Created {len(tasks)} tasks")
        
        # Get next task
        task = await task_manager.get_next_task("test-worker")
        print(f"   ✓ Retrieved task: {task.genre}")
        
        # Start task
        await task_manager.start_task(task.task_id, session.session_id)
        print(f"   ✓ Started task")
        
        # Complete task
        await task_manager.complete_task(task.task_id, {"test": "result"})
        print(f"   ✓ Completed task")
        
        # Get stats
        task_stats = await task_manager.get_task_stats()
        print(f"   ✓ Task stats: Completed {task_stats['completed_tasks']}/{task_stats['total_tasks']}")
        
    except Exception as e:
        print(f"   ✗ Task Manager Error: {e}")
        return False
    
    # Test 3: Data Aggregator
    print("\n3. Testing Data Aggregator...")
    try:
        aggregator = DataAggregator()
        await aggregator.start()
        
        # Add test data
        test_data = [
            {
                'title': 'Test Book 1',
                'price': '$10.99',
                'availability': 'In stock',
                'rating': 4,
                'genre': 'Fiction',
                'url': 'http://example.com/book1',
                'image_url': 'http://example.com/book1.jpg',
                'description': 'Test description',
                'upc': '12345',
                'scraped_at': '2024-01-01T00:00:00',
                'session_id': 'test-session',
                'container_id': 'test-container',
                'scrape_duration': 1.5,
                'retry_count': 0
            }
        ]
        
        await aggregator.add_data(test_data, "test-session")
        print(f"   ✓ Added test data")
        
        # Wait for write
        await asyncio.sleep(2)
        
        # Get stats
        agg_stats = aggregator.get_stats()
        print(f"   ✓ Aggregator stats: {agg_stats['total_received']} received, {agg_stats['total_written']} written")
        
        # Stop aggregator
        await aggregator.stop()
        print(f"   ✓ Aggregator stopped")
        
    except Exception as e:
        print(f"   ✗ Data Aggregator Error: {e}")
        return False
    
    # Test 4: Book Scraper (limited test)
    print("\n4. Testing Book Scraper...")
    try:
        # Just test initialization
        scraper = BookScraper(
            session_id="test-session",
            genre="Fiction",
            container_id="test-container"
        )
        print(f"   ✓ BookScraper initialized")
        
        # Test browser initialization (without scraping)
        print("   - Testing browser connection...")
        driver = scraper.initialize_browser()
        driver.get("http://books.toscrape.com")
        title = driver.title
        driver.quit()
        print(f"   ✓ Browser test successful: {title}")
        
    except Exception as e:
        print(f"   ✗ Book Scraper Error: {e}")
        return False
    
    print("\n" + "="*60)
    print("ALL COMPONENT TESTS PASSED!")
    print("="*60)
    
    return True


async def test_mini_scrape():
    """Test a mini scraping run with one genre."""
    
    print("\n" + "="*60)
    print("MINI SCRAPE TEST")
    print("="*60)
    
    # Override settings for test
    settings = get_settings()
    settings.scraping.max_pages_per_genre = 1  # Only scrape 1 page
    
    print(f"Testing with 1 genre, 1 page max")
    print("This will create actual output in output/books_data.csv")
    
    response = input("\nProceed with mini scrape? (y/n): ")
    if response.lower() != 'y':
        print("Skipping mini scrape test")
        return
    
    # Import and modify the orchestrator
    from src.orchestrator.main import ScraperOrchestrator
    
    # Create orchestrator
    orchestrator = ScraperOrchestrator()
    
    # Override to scrape only Fiction
    orchestrator.settings.scraping.genres_to_scrape = ["Fiction"]
    orchestrator.settings.scraping.max_concurrent_sessions = 1
    
    try:
        # Run the scraper
        await orchestrator.start()
        
        print("\nMini scrape completed! Check output/books_data.csv")
        
    except Exception as e:
        print(f"\nMini scrape failed: {e}")


async def main():
    """Run all tests."""
    
    # Test components
    success = await test_components()
    
    if success:
        # Optionally run mini scrape
        await test_mini_scrape()


if __name__ == "__main__":
    asyncio.run(main())