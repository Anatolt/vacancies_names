# Job Scraper

A modular Python application that scrapes job titles, locations, and descriptions from LinkedIn and other job posting URLs.

## Features

- **Modular Architecture**: Clean separation of concerns with dedicated modules for parsing, authentication, and utilities
- **Multi-site Support**: Extracts job information from LinkedIn and other job posting sites
- **Applied Jobs Collection**: Automatically collect all job links from LinkedIn "My Jobs" (Applied) page with pagination support
- **Smart Authentication**: Handles LinkedIn login with session persistence via `linkedin_auth.json`
- **Comprehensive History**: Stores complete job data (URL, title, location, description, timestamp) in JSON format to avoid duplicates and enable analysis
- **Progress Saving**: Continuous saving of collected links with resume functionality
- **Debug Mode**: Saves HTML content and screenshots for troubleshooting
- **Telegram Notifications**: Optional completion notifications via Telegram bot
- **Robust Error Handling**: Graceful handling of browser closure and network issues
- **CSV Export**: Clean tabular output with job titles, locations, and descriptions

## Prerequisites

- Python 3.x
- Chrome browser

## Installation

1. Install required Python packages:
```bash
pip install -r requirements.txt
```

2. Install Chrome browser for Playwright:
```bash
playwright install chromium
```

3. Create a `.env` file in the project root with your credentials:
```bash
cp env.example .env
```

Then edit `.env` with your actual credentials.

## Project Structure

```
├── main.py                    # Main entry point for scraping job details
├── collect_applied_jobs.py    # Collect all Applied Jobs links with pagination
├── applied_check.py          # Debug tool for Applied Jobs page analysis
├── src/                      # Source code modules
│   ├── process_links.py      # Core link processing logic
│   ├── linkedin_auth.py      # LinkedIn authentication module
│   ├── applied_jobs_parser.py # Applied Jobs page parser with pagination
│   ├── utils.py             # Utility functions (browser, debug, telegram)
│   └── parsers/             # Parser modules
│       ├── __init__.py
│       ├── linkedin.py      # LinkedIn job parser
│       └── generic.py       # Generic job site parser
├── data/                     # Data files and outputs
│   ├── links.txt            # Input URLs
│   ├── results.csv          # Output results
│   ├── history.txt          # Processed URLs history
│   └── linkedin_auth.json   # LinkedIn session data
├── debug/                    # Debug outputs (created when --debug used)
│   ├── html/                # Saved HTML files
│   ├── screenshots/         # Page screenshots
│   └── applied/             # Applied Jobs debug files
├── .env                     # Environment variables (create from env.example)
└── requirements.txt         # Python dependencies
```

## Usage

### Method 1: Collect Applied Jobs Automatically

The easiest way to scrape all jobs you've applied to on LinkedIn:

1. **Collect all Applied Jobs links:**
```bash
python collect_applied_jobs.py
```

2. **Scrape job details from collected links:**
```bash
python main.py --links-file data/applied_jobs_links_YYYYMMDD_HHMMSS.txt --output data/applied_jobs_results.csv --debug
```

### Method 2: Manual Links File

1. Create a text file (e.g., `links.txt`) containing job URLs, one per line:
```
https://www.linkedin.com/jobs/view/123456789/
https://www.linkedin.com/jobs/view/987654321/
```

2. Run the scraper:
```bash
python main.py
```

3. With custom options:
```bash
python main.py --links-file my_links.txt --output results.csv --debug
```

### Command Line Options

#### main.py (Job Details Scraper)
- `--links-file`: Input file with URLs (default: `data/links.txt`)
- `--output`: Output CSV file (default: `data/results.csv`)
- `--debug`: Enable debug mode (saves HTML and screenshots)
- `--history`: History file to track processed URLs (default: `data/history.txt`)

#### collect_applied_jobs.py (Applied Jobs Collector)
- `--output`: Output file for job links (default: auto-generated with timestamp)
- `--resume`: Resume from existing file (useful if collection was interrupted)
- `--max-pages`: Maximum pages to process (default: 50)
- `--headless`: Run browser in headless mode

The script will:
- Attempt to log in to LinkedIn if necessary. On the first successful login, it creates a `linkedin_auth.json` file to try and speed up future logins.
- Process each URL in the input file.
- For LinkedIn job URLs, it will first try to get data without a forced re-login. If that fails, it ensures an active login session and tries again.
- Extract job titles, locations, and descriptions.
- In debug mode, save HTML content and screenshots to a `debug/` folder for troubleshooting.
- Save results to the specified CSV file.
- Gracefully handle situations where the browser is closed by the user during execution

## Output

The script generates a CSV file with the following columns:
- `url`: Original job posting URL
- `title`: Job title
- `location`: Job location
- `description`: Job description text

## Debug Mode

When the `--debug` flag is used, the script creates a `debug/` directory with two subdirectories:
- `debug/html/`: Contains HTML files of the job pages
- `debug/screenshots/`: Contains PNG screenshots of the job pages

Each file is named with a timestamp, job ID (when available), and attempt number to help with troubleshooting. These files can be extremely useful when debugging parsing issues and understanding why certain job details might not be extracted correctly.

## History Management

The scraper now maintains comprehensive history in JSON format, storing complete job data rather than just URLs. This enables:

- **Duplicate Prevention**: Automatically skips previously processed URLs
- **Data Analysis**: Full job information available for analysis
- **Progress Tracking**: Timestamps for all processed jobs
- **Search Capabilities**: Find jobs by title, location, or description

### History File Format

The history file (`data/history.txt`) stores one JSON object per line:
```json
{"url": "https://linkedin.com/jobs/view/123", "title": "Android Developer", "location": "Berlin, Germany", "description": "Job description...", "processed_at": "2025-01-16T10:30:00"}
```

### History Management Commands

Use the `history_manager.py` utility to interact with your history:

```bash
# View recent entries
python history_manager.py view --limit 20

# Search for specific jobs
python history_manager.py search "android developer"

# Show statistics
python history_manager.py stats

# Migrate old plain-text history to new JSON format
python history_manager.py migrate data/old_history.txt
```

## Applied Jobs Collection Examples

### Basic Collection
```bash
# Collect all applied jobs links
python collect_applied_jobs.py

# Output: data/applied_jobs_links_20250716_164500.txt
```

### Advanced Collection Options
```bash
# Limit to first 10 pages
python collect_applied_jobs.py --max-pages 10

# Save to specific file
python collect_applied_jobs.py --output my_applied_jobs.txt

# Run in headless mode (no browser window)
python collect_applied_jobs.py --headless

# Resume interrupted collection
python collect_applied_jobs.py --resume data/applied_jobs_links_20250716_164500.txt
```

### Complete Workflow Example
```bash
# Step 1: Collect all applied jobs links
python collect_applied_jobs.py --output data/my_applied_jobs.txt

# Step 2: Scrape detailed information
python main.py --links-file data/my_applied_jobs.txt --output data/applied_jobs_details.csv --debug

# Step 3: View history and statistics
python history_manager.py stats
python history_manager.py search "android"
```

## Authentication Management

The script uses a few strategies to handle LinkedIn authentication:

1. Tries to load authentication data from `linkedin_auth.json` if it exists and is valid
2. Validates saved auth state before using it to ensure it contains essential LinkedIn cookies
3. If authentication fails or `--force-login` is specified, performs a new login
4. Saves authentication state after successful login for future use
5. Properly handles cases when the browser is closed during authentication
