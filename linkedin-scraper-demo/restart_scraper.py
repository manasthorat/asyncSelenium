"""
Script to restart the scraping environment and run the scraper.
"""

import os
import sys
import subprocess
import time
import shutil
from pathlib import Path

def restart_docker():
    """Restart Docker containers."""
    print("🔄 Restarting Docker containers...")
    
    # Change to docker directory
    os.chdir('docker')
    
    # Stop existing containers
    print("   Stopping existing containers...")
    subprocess.run(['docker-compose', 'down'], capture_output=True)
    time.sleep(2)
    
    # Remove old containers and volumes
    print("   Cleaning up old resources...")
    subprocess.run(['docker', 'system', 'prune', '-f'], capture_output=True)
    
    # Start new containers
    print("   Starting new containers...")
    result = subprocess.run(['docker-compose', 'up', '-d'], capture_output=True, text=True)
    if result.returncode != 0:
        print(f"   ❌ Error starting containers: {result.stderr}")
        return False
    
    # Wait for containers to be ready
    print("   Waiting for containers to be ready...")
    for i in range(30):
        result = subprocess.run(['docker-compose', 'ps'], capture_output=True, text=True)
        if 'healthy' in result.stdout:
            print("   ✅ Containers are healthy!")
            break
        time.sleep(2)
        print(f"   Waiting... ({i+1}/30)")
    
    # Go back to project root
    os.chdir('..')
    
    return True

def clean_output():
    """Clean output directory."""
    print("🧹 Cleaning output directory...")
    
    output_dir = Path('output')
    if output_dir.exists():
        # Remove existing CSV files
        for csv_file in output_dir.glob('*.csv'):
            csv_file.unlink()
            print(f"   Removed {csv_file.name}")
        
        # Remove report files
        for json_file in output_dir.glob('*.json'):
            json_file.unlink()
            print(f"   Removed {json_file.name}")
    
    # Clean checkpoints
    checkpoint_dir = Path('checkpoints')
    if checkpoint_dir.exists():
        shutil.rmtree(checkpoint_dir)
        print("   Removed checkpoints directory")
    checkpoint_dir.mkdir(exist_ok=True)
    
    print("   ✅ Output cleaned!")

def verify_selenium_grid():
    """Verify Selenium Grid is accessible."""
    print("🔍 Verifying Selenium Grid...")
    
    import requests
    
    try:
        response = requests.get('http://localhost:4444/status', timeout=10)
        if response.status_code == 200:
            status = response.json()
            nodes = status.get('value', {}).get('nodes', [])
            ready_nodes = sum(1 for node in nodes if node.get('availability') == 'UP')
            print(f"   ✅ Selenium Grid is ready with {ready_nodes} nodes!")
            
            # Show capacity
            total_slots = sum(node.get('maxSessions', 0) for node in nodes)
            print(f"   Total capacity: {total_slots} concurrent sessions")
            
            return True
        else:
            print(f"   ❌ Grid returned status {response.status_code}")
            return False
            
    except Exception as e:
        print(f"   ❌ Cannot connect to Selenium Grid: {e}")
        return False

def run_scraper():
    """Run the main scraper."""
    print("\n🚀 Starting scraper...")
    print("="*60)
    
    # Run the scraper
    subprocess.run([sys.executable, '-m', 'src.orchestrator.main'])

def main():
    """Main function."""
    print("="*60)
    print("SCRAPER RESTART UTILITY")
    print("="*60)
    
    # Ask for confirmation
    response = input("\nThis will restart Docker and clean output. Continue? (y/n): ")
    if response.lower() != 'y':
        print("Cancelled.")
        return
    
    # Restart Docker
    if not restart_docker():
        print("\n❌ Failed to restart Docker. Please check Docker Desktop is running.")
        return
    
    # Clean output
    clean_output()
    
    # Verify Selenium Grid
    if not verify_selenium_grid():
        print("\n❌ Selenium Grid verification failed. Check Docker logs.")
        return
    
    # Show configuration
    print("\n📋 Configuration:")
    print(f"   - Max concurrent sessions: {os.getenv('MAX_CONCURRENT_SESSIONS', '25')}")
    print(f"   - Number of genres: 50")
    print(f"   - Output file: {os.getenv('OUTPUT_FILE_PATH', './output/books_data.csv')}")
    
    # Run scraper
    response = input("\nStart scraping? (y/n): ")
    if response.lower() == 'y':
        run_scraper()
    else:
        print("Ready to scrape! Run: python -m src.orchestrator.main")

if __name__ == "__main__":
    main() 