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
        # This is specific to books.toscrape.com structure
        # In real implementation, this might come from a database or API
        genre_url_map = {
            'Fiction': f'{self.scraping.base_url}/catalogue/category/books/fiction_10/index.html',
            'Mystery': f'{self.scraping.base_url}/catalogue/category/books/mystery_3/index.html',
            'Science': f'{self.scraping.base_url}/catalogue/category/books/science_22/index.html',
            'History': f'{self.scraping.base_url}/catalogue/category/books/history_32/index.html',
            'Romance': f'{self.scraping.base_url}/catalogue/category/books/romance_8/index.html',
            'Fantasy': f'{self.scraping.base_url}/catalogue/category/books/fantasy_19/index.html',
            'Horror': f'{self.scraping.base_url}/catalogue/category/books/horror_31/index.html',
            'Poetry': f'{self.scraping.base_url}/catalogue/category/books/poetry_23/index.html',
        }
        
        # Return only requested genres
        return {genre: genre_url_map.get(genre, f'{self.scraping.base_url}/catalogue/category/books/{genre.lower()}_1/index.html')
                for genre in self.scraping.genres_to_scrape if genre in genre_url_map}


# Create global settings instance
settings = Settings()


# Convenience function for getting settings in other modules
def get_settings() -> Settings:
    """Get the global settings instance."""
    return settings