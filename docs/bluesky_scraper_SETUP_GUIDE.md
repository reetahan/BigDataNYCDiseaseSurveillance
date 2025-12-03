# Setup Guide - Bluesky Scraper

Quick reference for setting up and running the Bluesky scraper.

## 1. Initial Setup (One-time)

### Create Bluesky Account

1. Go to [https://bsky.app](https://bsky.app)
2. Sign up for a free account
3. Complete email verification

### Generate App Password

1. Log in to Bluesky
2. Go to **Settings** → **Privacy and Security** → **App Passwords**
3. Click **"Add App Password"**
4. Name it: `NYC Disease Scraper`
5. **Copy the password** (you won't see it again!)

### Setup Project

```bash
# Navigate to project directory
cd BigDataNYCDiseaseSurveillance

# Create virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate  # Mac/Linux
# OR
venv\Scripts\activate     # Windows

# Install dependencies
pip install -r requirements.txt

# Create .env file from template
cp .env.example .env
```

### Configure Credentials

Edit `.env` file:

```bash
nano .env  # or use your preferred editor
```

Update these lines:
```env
BLUESKY_HANDLE=yourname.bsky.social
BLUESKY_PASSWORD=xxxx-xxxx-xxxx-xxxx  # The app password you copied
```

Save and close the file.

## 2. Running the Scraper

### Single Search (Test Mode)

Good for testing and quick searches:

```bash
python run_bluesky_scraper.py --mode single --query "sick NYC" --limit 50
```

### Continuous Streaming

For production monitoring:

```bash
python run_bluesky_scraper.py --mode stream --interval 300
```

This runs continuously, searching every 5 minutes. Press `Ctrl+C` to stop.

### Limited Iterations

Run for a specific number of iterations:

```bash
python run_bluesky_scraper.py --mode stream --interval 60 --iterations 10
```

This will run 10 times with 60-second intervals, then stop.

## 3. Checking Output

View collected posts:

```bash
# See all collected posts
cat data/bluesky_posts.jsonl

# Count total posts
wc -l data/bluesky_posts.jsonl

# View last 5 posts (formatted)
tail -5 data/bluesky_posts.jsonl | python -m json.tool
```

## 4. Common Issues

### Issue: "Authentication Required" Error

**Solution:** Check your `.env` file:
- Handle must include `.bsky.social`
- Password must be an **app password**, not your account password
- No spaces or quotes around values

### Issue: "No Posts Found"

**Possible reasons:**
- Posts must contain BOTH health keywords AND NYC keywords
- Try broader search terms: `--query "NYC"`
- Bluesky's search may be limited

### Issue: "Module not found"

**Solution:**
```bash
# Make sure virtual environment is activated
source venv/bin/activate

# Reinstall dependencies
pip install -r requirements.txt
```

## 5. Integration with Kafka (Optional)

If you have Kafka running:

```bash
# Update .env
ENABLE_KAFKA=true
KAFKA_BOOTSTRAP_SERVERS=localhost:9092

# Run with Kafka enabled
python run_bluesky_scraper.py --mode stream --kafka
```

## 6. Customization

### Add Custom Keywords

Edit `.env`:

```env
CUSTOM_HEALTH_KEYWORDS=monkeypox,measles,rsv
CUSTOM_NYC_KEYWORDS=williamsburg,astoria,harlem
```

### Change Output Location

```bash
python run_bluesky_scraper.py --output my_data/posts.jsonl
```

### Adjust Search Frequency

```bash
# Search every 10 minutes (600 seconds)
python run_bluesky_scraper.py --mode stream --interval 600
```

## 7. Tips for Production Use

1. **Use screen/tmux** for long-running processes:
   ```bash
   screen -S bluesky_scraper
   python run_bluesky_scraper.py --mode stream
   # Press Ctrl+A, then D to detach
   ```

2. **Monitor logs** in real-time:
   ```bash
   tail -f scraper.log  # if you redirect output
   ```

3. **Rotate output files** daily:
   ```bash
   OUTPUT_FILE=data/bluesky_$(date +%Y%m%d).jsonl
   ```

4. **Set up cron job** for scheduled runs:
   ```cron
   0 */6 * * * cd /path/to/project && ./venv/bin/python run_bluesky_scraper.py --mode single >> logs/cron.log 2>&1
   ```

## Next Steps

After collecting data:
1. Feed into Kafka topic `social-media`
2. Process with Spark Streaming (Layer 3)
3. Extract features with GPT-4 LLM
4. Store in PostgreSQL/TimescaleDB
5. Visualize on Plotly dashboard

## Support

For issues specific to:
- **Bluesky API**: Check [AT Protocol docs](https://docs.bsky.app/)
- **Project architecture**: See main README.md
- **Scraper details**: See scrapers/bluesky/README.md
