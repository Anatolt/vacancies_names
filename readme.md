# LinkedIn Job Scraper

A Python script that scrapes job titles and locations from LinkedIn and other job posting URLs.

## Features

- Extracts job titles and locations from LinkedIn job postings
- Supports both LinkedIn and generic job posting URLs
- Handles LinkedIn authentication and attempts to reuse sessions using `linkedin_auth.json`
- Exports results to CSV format

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

The script will:
- Attempt to log in to LinkedIn if necessary. On the first successful login, it creates a `linkedin_auth.json` file to try and speed up future logins.
- Process each URL in the input file.
- For LinkedIn job URLs, it will first try to get data without a forced re-login. If that fails, it ensures an active login session and tries again.
- Extract job titles and locations.
- Save results to the specified CSV file.

## Output

The script generates a CSV file with the following columns:
- `url`: Original job posting URL
- `title`: Job title
- `location`: Job location
