"""
Test script to verify the environment setup.
Run this to ensure everything is configured correctly.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.config.settings import get_settings
from src.utils.logger import get_logger
from selenium import webdriver
import requests

# Get logger
logger = get_logger(__name__)

def test_environment():
    """Test all components of the environment."""
    
    print("=" * 50)
    print("ENVIRONMENT SETUP TEST")
    print("=" * 50)
    
    # Test 1: Configuration
    print("\n1. Testing Configuration...")
    try:
        settings = get_settings()
        print(f"   ✓ Configuration loaded")
        print(f"   - Selenium Hub: {settings.selenium.hub_url}")
        print(f"   - Max Sessions: {settings.scraping.max_concurrent_sessions}")
        print(f"   - Genres: {', '.join(settings.scraping.genres_to_scrape)}")
    except Exception as e:
        print(f"   ✗ Configuration Error: {e}")
        return False
    
    # Test 2: Logging
    print("\n2. Testing Logging...")
    try:
        logger.info("Test log message")
        logger.error("Test error message")
        print("   ✓ Logging working")
        print(f"   - Log file: {settings.logging.log_file_path}")
    except Exception as e:
        print(f"   ✗ Logging Error: {e}")
    
    # Test 3: Selenium Grid
    print("\n3. Testing Selenium Grid...")
    try:
        response = requests.get(f"{settings.selenium.hub_url}/status")
        if response.status_code == 200:
            grid_status = response.json()
            ready_nodes = sum(1 for node in grid_status['value']['nodes'] 
                            if node['availability'] == 'UP')
            print(f"   ✓ Selenium Grid is running")
            print(f"   - Ready nodes: {ready_nodes}")
        else:
            print(f"   ✗ Selenium Grid returned status: {response.status_code}")
    except Exception as e:
        print(f"   ✗ Cannot connect to Selenium Grid: {e}")
        print("   Make sure Docker containers are running!")
        return False
    
    # Test 4: Browser Connection
    print("\n4. Testing Browser Connection...")
    try:
        options = webdriver.ChromeOptions()
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        
        # For Selenium 4, use options directly without desired_capabilities
        driver = webdriver.Remote(
            command_executor=settings.selenium.hub_url,
            options=options
        )
        
        driver.get(settings.scraping.base_url)
        title = driver.title
        driver.quit()
        
        print(f"   ✓ Browser connection successful")
        print(f"   - Accessed: {settings.scraping.base_url}")
        print(f"   - Page title: {title}")
    except Exception as e:
        print(f"   ✗ Browser Connection Error: {e}")
        return False
    
    # Test 5: File System
    print("\n5. Testing File System...")
    try:
        # Check output directory
        output_dir = settings.data.output_file_path.parent
        if output_dir.exists():
            print(f"   ✓ Output directory exists: {output_dir}")
        else:
            print(f"   ✗ Output directory missing: {output_dir}")
        
        # Check log directory
        log_dir = settings.logging.log_file_path.parent
        if log_dir.exists():
            print(f"   ✓ Log directory exists: {log_dir}")
        else:
            print(f"   ✗ Log directory missing: {log_dir}")
    except Exception as e:
        print(f"   ✗ File System Error: {e}")
    
    print("\n" + "=" * 50)
    print("SETUP TEST COMPLETE")
    print("=" * 50)
    
    return True


if __name__ == "__main__":
    test_environment()