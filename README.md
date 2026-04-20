# Slack Attendance Tracker

A production-ready FastAPI service that automates attendance tracking by listening to Slack messages and recording check-in/check-out times to Google Sheets. Features intelligent message parsing via LLM (Groq Cloud), supports Jibble bot integration, and handles complex scenarios like overnight shifts and message edits.

## Features

- **Multi-Source Input**: Processes manual Slack messages, Jibble bot messages, and handles Zapier messages appropriately
- **LLM-Powered Parsing**: Uses Groq Cloud API for intelligent natural language understanding with regex fallback
- **Google Sheets Integration**: Automatically creates per-person worksheets with Date, Check-In, Check-Out, and Duration columns
- **Smart Shift Handling**: Detects overnight shifts, auto-closes missed checkouts, and prevents duplicate entries
- **Message Edit Support**: Re-processes edited Slack messages to update attendance records
- **Production-Ready**: Rate limiting, Slack signature verification, event deduplication, and IP-based filtering
- **Flexible Deployment**: Supports both VPS (systemd + nginx) and serverless (Vercel) deployments

## Architecture

```
Slack Events API → main.py → engine.py → (llm_parser/msg_parser) → resolver.py → sheets.py
```

| Component | Purpose |
|-----------|---------|
| `main.py` | FastAPI app with signature verification, rate limiting, event deduplication |
| `engine.py` | Core orchestration logic for check-in/check-out decisions |
| `llm_parser.py` | LLM-based message parsing using Groq Cloud |
| `msg_parser.py` | Regex-based fallback parser |
| `resolver.py` | Slack user ID and Jibble name resolution with caching |
| `sheets.py` | Google Sheets API client with per-person worksheets |
| `duration.py` | Time calculations with overnight shift support |
| `config.py` | Pydantic settings management |

## Prerequisites

- Python 3.11+
- Slack workspace with Bot token and Signing Secret
- Google Cloud project with Service Account and Sheets API enabled
- Groq Cloud API key (optional, for LLM parsing)
- (Optional) Vercel account for serverless deployment

## Installation

### 1. Clone and Install Dependencies

```bash
git clone <repository-url>
cd slack-attendance-tracker
pip install -r requirements.txt
```

### 2. Configure Environment

Copy `.env.example` to `.env` and fill in your credentials:

```bash
cp .env.example .env
```

Required variables:

| Variable | Description |
|----------|-------------|
| `SLACK_BOT_TOKEN` | Slack Bot User OAuth Token (xoxb-...) |
| `SLACK_SIGNING_SECRET` | Slack App Signing Secret for request verification |
| `SLACK_CHANNEL_ID` | Channel ID to monitor (optional but recommended) |
| `GOOGLE_SHEET_ID` | Google Spreadsheet ID from the URL |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | Path to JSON file (EC2) or raw JSON string (Vercel) |
| `GROQ_API_KEY` | Groq Cloud API key for LLM parsing (optional) |
| `PORT` | Server port (default: 8001) |

### 3. Set Up Google Sheets

1. Create a Google Spreadsheet
2. Share it with the service account email (client_email in your service account JSON)
3. Copy the Spreadsheet ID from the URL and set it as `GOOGLE_SHEET_ID`

The app will automatically create worksheets for each person as they check in.

### 4. Configure Slack App

1. Create a Slack App at api.slack.com/apps
2. Enable **Event Subscriptions** and subscribe to `message.channels`
3. Set the Request URL to your deployed endpoint (e.g., `https://your-domain.com/slack/events`)
4. Install the app to your workspace and note the Bot Token and Signing Secret

## Usage

### Local Development

```bash
python main.py
```

The server starts on `http://localhost:8001`.

### Testing

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_parser.py

# Run with verbose output
pytest -v
```

### Deployment

#### Option A: VPS/EC2 with Systemd + Nginx

1. Copy the service file:
   ```bash
   sudo cp genifem-attendance.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable genifem-attendance
   sudo systemctl start genifem-attendance
   ```

2. Configure nginx:
   ```bash
   sudo cp nginx.conf /etc/nginx/sites-available/slack-attendance
   sudo ln -s /etc/nginx/sites-available/slack-attendance /etc/nginx/sites-enabled/
   sudo nginx -t && sudo systemctl reload nginx
   ```

3. Set up HTTPS with certbot:
   ```bash
   sudo apt install certbot python3-certbot-nginx
   sudo certbot --nginx -d attendance.yourdomain.com
   ```

#### Option B: Vercel Serverless

1. Install Vercel CLI: `npm i -g vercel`
2. Run `vercel` and follow prompts
3. Set environment variables in Vercel dashboard
4. Update Slack Request URL to your Vercel deployment URL

## Message Format Support

### Manual Messages
- `check in 10:47 am`
- `checkin: 5:30 PM`
- `checked in`
- `checkout at 6:00 pm`

### Jibble Bot Messages
- `Haseeb jibbled in via Web (Chrome)`
- `Sarah jibbled out via Mobile`

### Ignored Messages
- Messages containing "sent by zapier"
- Random chat without attendance intent

## Google Sheets Structure

Each person gets their own worksheet tab:

| Date | Check-In | Check-Out | Duration |
|------|----------|-----------|----------|
| 2026-04-20 | 10:47 AM | 6:30 PM | 7h 43m |
| 2026-04-21 | N/A | 6:00 PM | N/A |

## Security Features

- **Slack Signature Verification**: All requests cryptographically verified
- **Rate Limiting**: Per-IP sliding window (60 requests/minute)
- **Payload Size Limits**: 64KB maximum body size
- **Timestamp Validation**: Rejects requests older than 5 minutes (replay protection)
- **Event Deduplication**: 5-minute TTL cache for event IDs
- **Channel Filtering**: Optional channel restriction

## Environment Variables Reference

| Variable | Required | Default | Notes |
|----------|----------|---------|-------|
| `SLACK_BOT_TOKEN` | Yes | - | xoxb-... |
| `SLACK_SIGNING_SECRET` | Yes | - | From Slack app settings |
| `SLACK_CHANNEL_ID` | No | - | C0XXXXXXXXX format |
| `GOOGLE_SHEET_ID` | Yes | - | Spreadsheet ID from URL |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | Yes | - | File path or JSON string |
| `GROQ_API_KEY` | No | - | Enables LLM parsing |
| `GROQ_MODEL` | No | `meta-llama/llama-4-scout-17b-16e-instruct` | Model identifier |
| `PORT` | No | 8001 | Server port |

## Troubleshooting

### Logs
```bash
# Systemd service logs
sudo journalctl -u genifem-attendance -f

# Nginx logs
sudo tail -f /var/log/nginx/access.log /var/log/nginx/error.log
```

### Common Issues

**"Invalid signature" errors**: Ensure `SLACK_SIGNING_SECRET` matches your Slack app

**Google Sheets permission errors**: Verify the service account email has Editor access to the spreadsheet

**Missing check-ins**: Check that the bot is invited to the channel and has `message.channels` scope

**Vercel cold starts**: Consider using a Vercel Pro plan for reduced latency

## Development

```bash
# Install dev dependencies
pip install -r requirements.txt

# Run linting (optional)
python -m black .
python -m ruff check .

# Run type checking (optional)
python -m mypy .
```

## License

[MIT License](LICENSE)

## Contributing

Contributions are welcome! Please ensure tests pass and follow the existing code style.
