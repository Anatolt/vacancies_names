# LinkedIn Job Scraper

A Python script that scrapes job titles, locations, and descriptions from LinkedIn and other job posting URLs.

## Features

- Extracts job titles, locations, and descriptions from LinkedIn job postings
- Supports both LinkedIn and generic job posting URLs
- Handles LinkedIn authentication and attempts to reuse sessions using `linkedin_auth.json`
- Exports results to CSV format
- Debug mode to save HTML content and screenshots for troubleshooting
- Graceful handling of browser closure by user
- Improved session authentication and validation

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

3. Create a `.env` file in the project root with your LinkedIn credentials:
```
LINKEDIN_EMAIL=your_email@example.com
LINKEDIN_PASSWORD=your_password
```

## Usage

1. Create a text file (e.g., `links.txt`) containing job URLs, one per line:
```
https://www.linkedin.com/jobs/view/123456789/
https://www.linkedin.com/jobs/view/987654321/
```

2. Run the script:
```bash
python one.py links.txt output.csv
```

3. For debugging issues with extraction, use the debug flag:
```bash
python one.py links.txt output.csv --debug
```

4. To force a new login (ignoring any saved authentication):
```bash
python one.py links.txt output.csv --force-login
```

5. You can combine options:
```bash
python one.py links.txt output.csv --debug --force-login
```

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

## Authentication Management

The script uses a few strategies to handle LinkedIn authentication:

1. Tries to load authentication data from `linkedin_auth.json` if it exists and is valid
2. Validates saved auth state before using it to ensure it contains essential LinkedIn cookies
3. If authentication fails or `--force-login` is specified, performs a new login
4. Saves authentication state after successful login for future use
5. Properly handles cases when the browser is closed during authentication
