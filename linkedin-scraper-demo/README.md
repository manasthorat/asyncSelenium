# Web Scraper Demo

A demonstration of high-scale web scraping architecture using Selenium Grid, Docker, and AsyncIO. This project scrapes book data from books.toscrape.com to simulate LinkedIn automation patterns.

## Architecture Overview

- **Orchestration Layer**: AsyncIO-based task management
- **Browser Execution Layer**: Dockerized Selenium Grid with multiple browser nodes
- **Data Aggregation**: Centralized data collection into single CSV
- **Monitoring**: Real-time progress tracking and metrics


## Quick Start

1. **Clone the repository**
   ```bash
   git clone <your-repo-url>
   cd linkedin-scraper-demo
   ```

2. **Set up Python environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env with your settings
   ```

4. **Start Selenium Grid**
   ```bash
   cd docker
   docker-compose up -d
   # Wait for all services to be healthy
   docker-compose ps
   ```

5. **Verify Selenium Grid**
   - Open http://localhost:4444 in your browser
   - You should see the Grid console with connected nodes

6. **Run the scraper**
   ```bash
   python -m src.orchestrator.main
   ```

## Project Structure

```
linkedin-scraper-demo/
├── docker/                 # Docker configurations
│   └── docker-compose.yml  # Selenium Grid setup
├── src/                    # Source code
│   ├── orchestrator/       # Core orchestration logic
│   ├── scrapers/          # Web scraping modules
│   ├── config/            # Configuration management
│   └── utils/             # Utility functions
├── output/                # CSV output files
├── logs/                  # Application logs
└── requirements.txt       # Python dependencies
```


- **Selenium Grid UI**: http://localhost:4444

### Selenium Grid not starting
```bash
# Check container status
docker-compose ps

# View logs
docker-compose logs selenium-hub

# Restart services
docker-compose down
docker-compose up -d
```
