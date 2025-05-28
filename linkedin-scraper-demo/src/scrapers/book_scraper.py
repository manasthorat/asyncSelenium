"""
Book scraper module for extracting book data from books.toscrape.com.

This module handles the actual web scraping logic, including navigation,
data extraction, and pagination handling.
"""

import asyncio
import time
import random
from typing import Dict, List, Optional, Any
from datetime import datetime
from urllib.parse import urljoin, urlparse
import re

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException, 
    NoSuchElementException, 
    WebDriverException
)

from ..config.settings import get_settings
from ..utils.logger import get_logger, get_performance_logger, log_exception


class BookScraper:
    """
    Scraper for extracting book information from books.toscrape.com.
    
    This class handles:
    - Browser session management
    - Page navigation and pagination
    - Data extraction from book listings and detail pages
    - Error handling and retries
    """
    
    def __init__(self, session_id: str, genre: str, container_id: Optional[str] = None):
        """
        Initialize the book scraper.
        
        Args:
            session_id: Unique identifier for this scraping session
            genre: The book genre to scrape
            container_id: Optional container ID for tracking
        """
        self.session_id = session_id
        self.genre = genre
        self.container_id = container_id or "local"
        
        # Get configuration
        self.settings = get_settings()
        
        # Set up logging
        self.logger = get_logger(__name__, session_id)
        self.perf_logger = get_performance_logger(__name__)
        
        # Initialize browser as None
        self.driver: Optional[webdriver.Remote] = None
        
        # Tracking
        self.books_scraped = 0
        self.pages_scraped = 0
        self.retry_count = 0
        self.start_time = time.time()
        
        self.logger.info(f"BookScraper initialized for genre: {genre}")
    
    def initialize_browser(self) -> webdriver.Remote:
        """
        Initialize a remote browser session with proper configuration.
        
        Returns:
            Configured WebDriver instance
        """
        self.logger.info("Initializing browser session")
        
        # Configure Chrome options
        options = webdriver.ChromeOptions()
        
        # Add options from settings with some modifications for stability
        stable_options = [
            '--disable-blink-features=AutomationControlled',
            '--disable-dev-shm-usage',
            '--no-sandbox',
            '--disable-gpu',
            '--disable-web-security',
            '--disable-features=VizDisplayCompositor',
            '--disable-setuid-sandbox',
            '--disable-extensions',
            '--dns-prefetch-disable',
            '--disable-browser-side-navigation',
            '--disable-infobars',
            '--mute-audio',
            '--no-first-run',
            '--no-default-browser-check',
            '--disable-background-timer-throttling',
            '--disable-backgrounding-occluded-windows',
            '--disable-renderer-backgrounding',
            '--disable-features=TranslateUI',
            '--disable-ipc-flooding-protection'
        ]
        
        for option in stable_options:
            options.add_argument(option)
        
        # Set window size
        options.add_argument(f'--window-size={self.settings.selenium.window_size[0]},{self.settings.selenium.window_size[1]}')
        
        # Add user agent to appear more human-like
        user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        ]
        options.add_argument(f'user-agent={random.choice(user_agents)}')
        
        # Add experimental options to avoid detection
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)
        
        # Additional preferences for stability
        prefs = {
            "credentials_enable_service": False,
            "profile.password_manager_enabled": False,
            "profile.default_content_setting_values.notifications": 2,
            "profile.default_content_settings.popups": 0,
            "profile.managed_default_content_settings.images": 2  # Disable image loading for speed
        }
        options.add_experimental_option("prefs", prefs)
        
        # Set page load strategy
        options.page_load_strategy = 'eager'  # Don't wait for all resources
        
        try:
            # Create remote driver with increased timeout
            driver = webdriver.Remote(
                command_executor=self.settings.selenium.hub_url,
                options=options,
                keep_alive=True
            )
            
            # Set timeouts
            driver.implicitly_wait(self.settings.selenium.implicit_wait)
            driver.set_page_load_timeout(self.settings.selenium.page_load_timeout)
            
            # Set window size again to ensure it's applied
            driver.set_window_size(self.settings.selenium.window_size[0], self.settings.selenium.window_size[1])
            
            self.logger.info("Browser session initialized successfully")
            return driver
            
        except Exception as e:
            self.logger.error(f"Failed to initialize browser: {e}")
            raise
    
    async def scrape_genre(self) -> List[Dict[str, Any]]:
        """
        Main method to scrape all books from a genre.
        
        Returns:
            List of dictionaries containing book data
        """
        all_books = []
        
        try:
            # Initialize browser with retry
            max_browser_retries = 3
            for attempt in range(max_browser_retries):
                try:
                    self.driver = self.initialize_browser()
                    break
                except Exception as e:
                    self.logger.warning(f"Browser initialization attempt {attempt + 1} failed: {e}")
                    if attempt < max_browser_retries - 1:
                        await asyncio.sleep(5)
                    else:
                        raise
            
            # Get genre URL
            genre_urls = self.settings.get_genre_urls()
            genre_url = genre_urls.get(self.genre)
            
            if not genre_url:
                raise ValueError(f"Unknown genre: {self.genre}")
            
            self.logger.info(f"Starting to scrape genre: {self.genre} from {genre_url}")
            
            # Navigate to genre page with retry
            for attempt in range(3):
                try:
                    with self.perf_logger.track_duration("initial_page_load", genre=self.genre):
                        self.driver.get(genre_url)
                        await self._wait_for_page_load()
                    break
                except Exception as e:
                    self.logger.warning(f"Page load attempt {attempt + 1} failed: {e}")
                    if attempt < 2:
                        await asyncio.sleep(5)
                    else:
                        raise
            
            # Scrape books from all pages
            page_num = 1
            while page_num <= self.settings.scraping.max_pages_per_genre:
                self.logger.info(f"Scraping page {page_num} of {self.genre}")
                
                # Extract books from current page
                try:
                    with self.perf_logger.track_duration("page_scraping", page=page_num):
                        books = await self._extract_books_from_page()
                        all_books.extend(books)
                    
                    self.pages_scraped += 1
                except Exception as e:
                    self.logger.error(f"Failed to extract books from page {page_num}: {e}")
                    # Continue to next page instead of failing completely
                
                # Check for next page
                if not await self._go_to_next_page():
                    self.logger.info(f"No more pages found for {self.genre}")
                    break
                
                page_num += 1
                
                # Add delay between pages
                await self._random_delay()
            
            self.logger.info(f"Completed scraping {self.genre}: {len(all_books)} books found")
            
        except Exception as e:
            log_exception(self.logger, e, {'genre': self.genre, 'pages_scraped': self.pages_scraped})
            raise
            
        finally:
            if self.driver:
                try:
                    self.driver.quit()
                    self.logger.info("Browser session closed")
                except Exception as e:
                    self.logger.warning(f"Error closing browser: {e}")
        
        return all_books
    
    async def _wait_for_page_load(self):
        """Wait for the page to be fully loaded."""
        try:
            # Wait for the main content to be present
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CLASS_NAME, "product_pod"))
            )
            # Additional wait for dynamic content
            await asyncio.sleep(0.5)
        except TimeoutException:
            self.logger.warning("Timeout waiting for page load")
    
    async def _extract_books_from_page(self) -> List[Dict[str, Any]]:
        """
        Extract book data from the current page.
        
        Returns:
            List of book dictionaries
        """
        books = []
        
        try:
            # Find all book containers
            book_elements = self.driver.find_elements(By.CLASS_NAME, "product_pod")
            
            for book_elem in book_elements:
                try:
                    book_data = await self._extract_book_data(book_elem)
                    if book_data:
                        books.append(book_data)
                        self.books_scraped += 1
                        
                except Exception as e:
                    self.logger.warning(f"Failed to extract book data: {e}")
                    continue
            
            self.logger.info(f"Extracted {len(books)} books from current page")
            
        except Exception as e:
            self.logger.error(f"Error extracting books from page: {e}")
        
        return books
    
    async def _extract_book_data(self, book_element) -> Optional[Dict[str, Any]]:
        """
        Extract data from a single book element.
        
        Args:
            book_element: Selenium WebElement for the book
            
        Returns:
            Dictionary containing book data
        """
        try:
            # Extract basic information
            title_elem = book_element.find_element(By.TAG_NAME, "h3").find_element(By.TAG_NAME, "a")
            title = title_elem.get_attribute("title")
            relative_url = title_elem.get_attribute("href")
            
            # Get absolute URL
            current_url = self.driver.current_url
            book_url = urljoin(current_url, relative_url)
            
            # Extract price
            price_elem = book_element.find_element(By.CLASS_NAME, "price_color")
            price = price_elem.text
            
            # Extract availability
            availability_elem = book_element.find_element(By.CLASS_NAME, "availability")
            availability = availability_elem.text.strip()
            
            # Extract rating
            rating_elem = book_element.find_element(By.TAG_NAME, "p")
            rating_class = rating_elem.get_attribute("class")
            rating_match = re.search(r'star-rating (\w+)', rating_class)
            
            rating_map = {
                'One': 1, 'Two': 2, 'Three': 3, 
                'Four': 4, 'Five': 5
            }
            rating = rating_map.get(rating_match.group(1), 0) if rating_match else 0
            
            # Extract image URL
            img_elem = book_element.find_element(By.TAG_NAME, "img")
            image_url = urljoin(current_url, img_elem.get_attribute("src"))
            
            # Optionally fetch additional details from book page
            # (commented out for performance in demo)
            # details = await self._fetch_book_details(book_url)
            
            # Compile book data
            book_data = {
                'title': title,
                'price': price,
                'availability': availability,
                'rating': rating,
                'genre': self.genre,
                'url': book_url,
                'image_url': image_url,
                'description': '',  # Would be fetched from detail page
                'upc': '',  # Would be fetched from detail page
                'scraped_at': datetime.utcnow().isoformat(),
                'session_id': self.session_id,
                'container_id': self.container_id,
                'scrape_duration': round(time.time() - self.start_time, 2),
                'retry_count': self.retry_count
            }
            
            return book_data
            
        except Exception as e:
            self.logger.debug(f"Error extracting book data: {e}")
            return None
    
    async def _go_to_next_page(self) -> bool:
        """
        Navigate to the next page if available.
        
        Returns:
            True if successfully navigated to next page, False otherwise
        """
        try:
            # Look for "next" button
            next_button = self.driver.find_element(By.CLASS_NAME, "next")
            next_link = next_button.find_element(By.TAG_NAME, "a")
            
            # Click the next button
            next_link.click()
            
            # Wait for new page to load
            await self._wait_for_page_load()
            
            return True
            
        except NoSuchElementException:
            # No next button found - we're on the last page
            return False
        except Exception as e:
            self.logger.warning(f"Error navigating to next page: {e}")
            return False
    
    async def _random_delay(self):
        """Add a random delay between requests to appear more human-like."""
        delay = random.uniform(
            self.settings.scraping.scrape_delay_min,
            self.settings.scraping.scrape_delay_max
        )
        self.logger.debug(f"Waiting {delay:.2f} seconds")
        await asyncio.sleep(delay)
    
    async def _fetch_book_details(self, book_url: str) -> Dict[str, Any]:
        """
        Fetch additional details from the book's detail page.
        
        Args:
            book_url: URL of the book detail page
            
        Returns:
            Dictionary with additional book details
        """
        # This is optional and commented out for performance
        # In a real scraper, you might want to fetch additional details
        pass
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get scraping statistics.
        
        Returns:
            Dictionary containing scraping stats
        """
        duration = time.time() - self.start_time
        return {
            'session_id': self.session_id,
            'genre': self.genre,
            'books_scraped': self.books_scraped,
            'pages_scraped': self.pages_scraped,
            'duration_seconds': round(duration, 2),
            'books_per_second': round(self.books_scraped / duration, 2) if duration > 0 else 0,
            'retry_count': self.retry_count,
            'status': 'completed'
        }