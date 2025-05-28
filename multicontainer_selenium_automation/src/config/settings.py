"""
Configuration management for the web scraper demo.

This module loads configuration from environment variables and provides
a centralized settings object for the entire application.
"""

import os
from dataclasses import dataclass, field
from typing import List, Optional
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


@dataclass
class SeleniumConfig:
    """Configuration for Selenium WebDriver and Grid."""
    
    hub_url: str = field(default_factory=lambda: os.getenv('SELENIUM_HUB_URL', 'http://localhost:4444/wd/hub'))
    implicit_wait: int = field(default_factory=lambda: int(os.getenv('SELENIUM_IMPLICIT_WAIT', '10')))
    page_load_timeout: int = field(default_factory=lambda: int(os.getenv('SELENIUM_PAGE_LOAD_TIMEOUT', '30')))
    headless: bool = field(default_factory=lambda: os.getenv('SELENIUM_HEADLESS', 'False').lower() == 'true')
    
    # Browser capabilities
    browser_name: str = 'chrome'  # or 'firefox'
    window_size: tuple = (1920, 1080)
    
    # Chrome specific options
    chrome_options: List[str] = field(default_factory=lambda: [
        '--disable-blink-features=AutomationControlled',  # Avoid detection
        '--disable-dev-shm-usage',  # Overcome limited resource problems
        '--no-sandbox',  # Required for Docker
        '--disable-gpu',  # Applicable to windows os only
        '--disable-web-security',
        '--disable-features=VizDisplayCompositor'
    ])


@dataclass
class ScrapingConfig:
    """Configuration for scraping behavior."""
    
    max_concurrent_sessions: int = field(default_factory=lambda: int(os.getenv('MAX_CONCURRENT_SESSIONS', '5')))
    scrape_delay_min: float = field(default_factory=lambda: float(os.getenv('SCRAPE_DELAY_MIN', '1')))
    scrape_delay_max: float = field(default_factory=lambda: float(os.getenv('SCRAPE_DELAY_MAX', '3')))
    max_retries: int = field(default_factory=lambda: int(os.getenv('MAX_RETRIES', '3')))
    retry_delay: float = field(default_factory=lambda: float(os.getenv('RETRY_DELAY', '5')))
    
    # Target website
    base_url: str = field(default_factory=lambda: os.getenv('BASE_URL', 'http://books.toscrape.com'))
    genres_to_scrape: List[str] = field(default_factory=lambda: 
        os.getenv('GENRES_TO_SCRAPE', 'Fiction,Mystery,Science,History,Romance').split(',')
    )
    
    # Limits
    max_pages_per_genre: int = field(default_factory=lambda: int(os.getenv('MAX_PAGES_PER_GENRE', '5')))
    session_timeout: int = field(default_factory=lambda: int(os.getenv('SESSION_TIMEOUT', '300')))


@dataclass
class DataConfig:
    """Configuration for data handling and storage."""
    
    output_file_path: Path = field(default_factory=lambda: Path(os.getenv('OUTPUT_FILE_PATH', './output/books_data.csv')))
    buffer_size: int = field(default_factory=lambda: int(os.getenv('BUFFER_SIZE', '50')))
    write_interval: int = field(default_factory=lambda: int(os.getenv('WRITE_INTERVAL', '30')))
    
    # CSV columns
    csv_columns: List[str] = field(default_factory=lambda: [
        'title',
        'price',
        'availability',
        'rating',
        'genre',
        'url',
        'image_url',
        'description',
        'upc',
        'scraped_at',
        'session_id',
        'container_id',
        'scrape_duration',
        'retry_count'
    ])
    
    def ensure_output_dir(self):
        """Create output directory if it doesn't exist."""
        self.output_file_path.parent.mkdir(parents=True, exist_ok=True)


@dataclass
class LoggingConfig:
    """Configuration for logging."""
    
    log_level: str = field(default_factory=lambda: os.getenv('LOG_LEVEL', 'INFO'))
    log_file_path: Path = field(default_factory=lambda: Path(os.getenv('LOG_FILE_PATH', './logs/scraper.log')))
    log_max_size_mb: int = field(default_factory=lambda: int(os.getenv('LOG_MAX_SIZE_MB', '10')))
    log_backup_count: int = field(default_factory=lambda: int(os.getenv('LOG_BACKUP_COUNT', '5')))
    
    # Log format
    log_format: str = '%(asctime)s - %(name)s - %(levelname)s - [%(session_id)s] - %(message)s'
    date_format: str = '%Y-%m-%d %H:%M:%S'
    
    def ensure_log_dir(self):
        """Create log directory if it doesn't exist."""
        self.log_file_path.parent.mkdir(parents=True, exist_ok=True)


@dataclass
class MonitoringConfig:
    """Configuration for monitoring and metrics."""
    
    enable_metrics: bool = field(default_factory=lambda: os.getenv('ENABLE_METRICS', 'True').lower() == 'true')
    metrics_port: int = field(default_factory=lambda: int(os.getenv('METRICS_PORT', '9090')))
    
    # Health check settings
    health_check_interval: int = 30  # seconds
    session_health_timeout: int = 60  # seconds


@dataclass
class Settings:
    """Main settings container combining all configuration sections."""
    
    selenium: SeleniumConfig = field(default_factory=SeleniumConfig)
    scraping: ScrapingConfig = field(default_factory=ScrapingConfig)
    data: DataConfig = field(default_factory=DataConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    monitoring: MonitoringConfig = field(default_factory=MonitoringConfig)
    
    def __post_init__(self):
        """Initialize directories and validate settings."""
        self.data.ensure_output_dir()
        self.logging.ensure_log_dir()
        self._validate_settings()
    
    def _validate_settings(self):
        """Validate configuration values."""
        # Check concurrent sessions
        if self.scraping.max_concurrent_sessions < 1:
            raise ValueError("MAX_CONCURRENT_SESSIONS must be at least 1")
        
        # Check delays
        if self.scraping.scrape_delay_min > self.scraping.scrape_delay_max:
            raise ValueError("SCRAPE_DELAY_MIN cannot be greater than SCRAPE_DELAY_MAX")
        
        # Check genres
        if not self.scraping.genres_to_scrape:
            raise ValueError("At least one genre must be specified in GENRES_TO_SCRAPE")
        
        # Validate URLs
        if not self.scraping.base_url.startswith(('http://', 'https://')):
            raise ValueError("BASE_URL must start with http:// or https://")
    
    def get_genre_urls(self) -> dict:
        """Get mapping of genre names to their URLs."""
        # Complete mapping for all genres on books.toscrape.com
        # These are the actual category IDs used by the site
        genre_url_map = {
            'Travel': f'{self.scraping.base_url}/catalogue/category/books/travel_2/index.html',
            'Mystery': f'{self.scraping.base_url}/catalogue/category/books/mystery_3/index.html',
            'Historical Fiction': f'{self.scraping.base_url}/catalogue/category/books/historical-fiction_4/index.html',
            'Sequential Art': f'{self.scraping.base_url}/catalogue/category/books/sequential-art_5/index.html',
            'Classics': f'{self.scraping.base_url}/catalogue/category/books/classics_6/index.html',
            'Philosophy': f'{self.scraping.base_url}/catalogue/category/books/philosophy_7/index.html',
            'Romance': f'{self.scraping.base_url}/catalogue/category/books/romance_8/index.html',
            'Womens Fiction': f'{self.scraping.base_url}/catalogue/category/books/womens-fiction_9/index.html',
            'Fiction': f'{self.scraping.base_url}/catalogue/category/books/fiction_10/index.html',
            'Childrens': f'{self.scraping.base_url}/catalogue/category/books/childrens_11/index.html',
            'Religion': f'{self.scraping.base_url}/catalogue/category/books/religion_12/index.html',
            'Nonfiction': f'{self.scraping.base_url}/catalogue/category/books/nonfiction_13/index.html',
            'Music': f'{self.scraping.base_url}/catalogue/category/books/music_14/index.html',
            'Default': f'{self.scraping.base_url}/catalogue/category/books/default_15/index.html',
            'Science Fiction': f'{self.scraping.base_url}/catalogue/category/books/science-fiction_16/index.html',
            'Sports and Games': f'{self.scraping.base_url}/catalogue/category/books/sports-and-games_17/index.html',
            'Add a comment': f'{self.scraping.base_url}/catalogue/category/books/add-a-comment_18/index.html',
            'Fantasy': f'{self.scraping.base_url}/catalogue/category/books/fantasy_19/index.html',
            'New Adult': f'{self.scraping.base_url}/catalogue/category/books/new-adult_20/index.html',
            'Young Adult': f'{self.scraping.base_url}/catalogue/category/books/young-adult_21/index.html',
            'Science': f'{self.scraping.base_url}/catalogue/category/books/science_22/index.html',
            'Poetry': f'{self.scraping.base_url}/catalogue/category/books/poetry_23/index.html',
            'Paranormal': f'{self.scraping.base_url}/catalogue/category/books/paranormal_24/index.html',
            'Art': f'{self.scraping.base_url}/catalogue/category/books/art_25/index.html',
            'Psychology': f'{self.scraping.base_url}/catalogue/category/books/psychology_26/index.html',
            'Autobiography': f'{self.scraping.base_url}/catalogue/category/books/autobiography_27/index.html',
            'Parenting': f'{self.scraping.base_url}/catalogue/category/books/parenting_28/index.html',
            'Adult Fiction': f'{self.scraping.base_url}/catalogue/category/books/adult-fiction_29/index.html',
            'Humor': f'{self.scraping.base_url}/catalogue/category/books/humor_30/index.html',
            'Horror': f'{self.scraping.base_url}/catalogue/category/books/horror_31/index.html',
            'History': f'{self.scraping.base_url}/catalogue/category/books/history_32/index.html',
            'Food and Drink': f'{self.scraping.base_url}/catalogue/category/books/food-and-drink_33/index.html',
            'Christian Fiction': f'{self.scraping.base_url}/catalogue/category/books/christian-fiction_34/index.html',
            'Business': f'{self.scraping.base_url}/catalogue/category/books/business_35/index.html',
            'Biography': f'{self.scraping.base_url}/catalogue/category/books/biography_36/index.html',
            'Thriller': f'{self.scraping.base_url}/catalogue/category/books/thriller_37/index.html',
            'Contemporary': f'{self.scraping.base_url}/catalogue/category/books/contemporary_38/index.html',
            'Spirituality': f'{self.scraping.base_url}/catalogue/category/books/spirituality_39/index.html',
            'Academic': f'{self.scraping.base_url}/catalogue/category/books/academic_40/index.html',
            'Self Help': f'{self.scraping.base_url}/catalogue/category/books/self-help_41/index.html',
            'Historical': f'{self.scraping.base_url}/catalogue/category/books/historical_42/index.html',
            'Christian': f'{self.scraping.base_url}/catalogue/category/books/christian_43/index.html',
            'Suspense': f'{self.scraping.base_url}/catalogue/category/books/suspense_44/index.html',
            'Short Stories': f'{self.scraping.base_url}/catalogue/category/books/short-stories_45/index.html',
            'Novels': f'{self.scraping.base_url}/catalogue/category/books/novels_46/index.html',
            'Health': f'{self.scraping.base_url}/catalogue/category/books/health_47/index.html',
            'Politics': f'{self.scraping.base_url}/catalogue/category/books/politics_48/index.html',
            'Cultural': f'{self.scraping.base_url}/catalogue/category/books/cultural_49/index.html',
            'Erotica': f'{self.scraping.base_url}/catalogue/category/books/erotica_50/index.html',
            'Crime': f'{self.scraping.base_url}/catalogue/category/books/crime_51/index.html',
        }
        
        # Return only requested genres
        requested_genres = {}
        for genre in self.scraping.genres_to_scrape:
            if genre in genre_url_map:
                requested_genres[genre] = genre_url_map[genre]
            else:
                # Log warning for unknown genres
                print(f"Warning: Unknown genre '{genre}', skipping...")
        
        return requested_genres


# Create global settings instance
settings = Settings()


# Convenience function for getting settings in other modules
def get_settings() -> Settings:
    """Get the global settings instance."""
    return settings