# LinkedIn-Style Web Scraper Demo

A demonstration of high-scale web scraping architecture using Selenium Grid, Docker, and AsyncIO. This project scrapes book data from books.toscrape.com to simulate LinkedIn automation patterns.

## Architecture Overview

- **Orchestration Layer**: AsyncIO-based task management
- **Browser Execution Layer**: Dockerized Selenium Grid with multiple browser nodes
- **Data Aggregation**: Centralized data collection into single CSV
- **Monitoring**: Real-time progress tracking and metrics

## Prerequisites

- Python 3.10+
- Docker and Docker Compose
- 8GB RAM minimum (for running multiple browser containers)
- Unix-based OS (Linux/MacOS) or WSL2 on Windows

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

## Configuration

Key settings in `.env`:
- `MAX_CONCURRENT_SESSIONS`: Number of parallel browser sessions
- `SCRAPE_DELAY_MIN/MAX`: Delay between requests (seconds)
- `OUTPUT_FILE_PATH`: Where to save scraped data
- `LOG_LEVEL`: Logging verbosity (DEBUG, INFO, WARNING, ERROR)

## Monitoring

- **Selenium Grid UI**: http://localhost:4444
- **cAdvisor** (container metrics): http://localhost:8080
- **Application logs**: `./logs/scraper.log`

## Development

### Running Tests
```bash
pytest tests/
```

### Code Formatting
```bash
black src/
flake8 src/
```

### Debugging
- Set `LOG_LEVEL=DEBUG` in `.env`
- Check browser screenshots in `./logs/screenshots/`
- Monitor container logs: `docker-compose logs -f`

## Troubleshooting

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

### Browser sessions failing
- Increase memory limits in docker-compose.yml
- Reduce MAX_CONCURRENT_SESSIONS
- Check available system resources

### Data not being saved
- Verify OUTPUT_FILE_PATH exists and is writable
- Check logs for write errors
- Ensure BUFFER_SIZE is appropriate

## Performance Tuning

- **Memory**: Each Chrome node uses ~2GB RAM
- **CPU**: Allocate 1 CPU core per 2-3 browser sessions
- **Disk**: Ensure sufficient space for logs and output

## License

MIT License - See LICENSE file for details