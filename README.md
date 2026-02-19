****# Czech Republic Visa Application Tracker****

Automated visa application tracking system for Czech Republic consulates (Ankara & Istanbul) using GitHub Actions.

##  Features

- **Part 1**: Monitors BEING_PROCESSED applications for status changes (Approved/Rejected)
- **Part 2**: Scans for new applications in the last 30 days
- **Runs automatically every 6 hours** (00:00, 06:00, 12:00, 18:00 UTC)
- **Debug mode always on** - detailed logs in GitHub Actions
- **Supabase storage** - all data stored in PostgreSQL database
- **Completely free** - runs on GitHub's infrastructure

##  Architecture

The system consists of two parts:

### Part 1: Status Monitoring
- Fetches all applications with `BEING_PROCESSED` status from database
- Checks each one on the official Czech government website
- Updates database when status changes to `APPROVED` or `REJECTED`
- Records all changes in the `changes` table

### Part 2: New Application Discovery
- Scans the last 45 days for new applications
- Checks both Ankara (ANKA) and Istanbul (ISTA) consulates
- Skips weekends (no processing on weekends)
- Adds newly discovered applications to database

##  Prerequisites

1. **GitHub Account** (free)
2. **Supabase Account** (free tier sufficient)

##  Setup

### Step 1: Create Supabase Database

1. Go to [Supabase](https://supabase.com) and create a free account
2. Create a new project
3. Go to **SQL Editor** and run:
```sql
-- Applications table
CREATE TABLE applications (
    id TEXT PRIMARY KEY,
    city TEXT NOT NULL,
    submit_date DATE NOT NULL,
    status TEXT NOT NULL,
    last_checked TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Changes log table
CREATE TABLE changes (
    id BIGSERIAL PRIMARY KEY,
    application_id TEXT NOT NULL,
    old_status TEXT,
    new_status TEXT NOT NULL,
    changed_at TIMESTAMPTZ DEFAULT NOW(),
    is_read BOOLEAN DEFAULT FALSE,
    FOREIGN KEY (application_id) REFERENCES applications(id)
);

-- Indexes
CREATE INDEX idx_applications_status ON applications(status);
CREATE INDEX idx_applications_submit_date ON applications(submit_date);
CREATE INDEX idx_applications_city ON applications(city);
CREATE INDEX idx_changes_application_id ON changes(application_id);
CREATE INDEX idx_changes_changed_at ON changes(changed_at DESC);
```

4. Get your credentials:
   - **Settings** → **API** → Copy **Project URL**
   - Copy **service_role key** (under "Project API keys")

### Step 2: Fork This Repository

1. Click **Fork** button (top right)
2. This creates your own copy

### Step 3: Add GitHub Secrets

1. Go to your forked repository
2. **Settings** → **Secrets and variables** → **Actions**
3. Click **New repository secret**

Add two secrets:

- **Name**: `SUPABASE_URL`  
  **Value**: Your Supabase Project URL

- **Name**: `SUPABASE_KEY`  
  **Value**: Your Supabase service_role key

### Step 4: Populate Initial Data (Optional)

If starting fresh, you can run the local GUI application to scrape historical data, or manually trigger the workflow to start collecting data.

For historical data collection:
1. Edit `bolldozer_pro.py` line 293:
```python
   start_date = part2_start_date if part2_start_date else today - timedelta(days=90)  # 90 days
```
2. Commit and push
3. Manually trigger workflow once
4. Revert back to 30 days

### Step 5: Enable Workflow

The workflow is now active! It will run automatically every 6 hours.

##  How It Works?

### Automatic Runs (Every 6 Hours)
- **00:00 UTC** - Night check
- **06:00 UTC** - Morning check
- **12:00 UTC** - Afternoon check
- **18:00 UTC** - Evening check

Each run:
1. Checks all BEING_PROCESSED applications
2. Scans last 30 days for new applications
3. Updates database
4. Logs everything for debugging


### View Logs
1. **Actions** tab → Latest run
2. Click **check-visas** job
3. Expand **▶️ Run Visa Tracker** step
4. See detailed logs with emojis:
   - ✅ Approved
   - ❌ Rejected
   - ⏳ Being Processed
   - 🔍 Not Found

### View Data in Supabase
1. Supabase Dashboard → **Table Editor**
2. **applications** table - all visa applications
3. **changes** table - status change history

## ⚙️ Configuration

### Change Scan Period (Part 2)
Edit `github_runner.py` line 293:
```python
start_date = part2_start_date if part2_start_date else today - timedelta(days=30)
# Change 30 to 60, 90, etc.
```

### Change Schedule
Edit `.github/workflows/visa-checker.yml` line 5:
```yaml
- cron: '0 */6 * * *'  # Every 6 hours
# Examples:
# - cron: '0 */3 * * *'  # Every 3 hours
# - cron: '0 9,21 * * *'  # Only 9 AM and 9 PM UTC
# - cron: '0 */12 * * *'  # Every 12 hours
```

### Add More Cities
Edit `github_runner.py` line 305:
```python
cities = ["ANKA", "ISTA"]  # Add more city codes here
```

## 💰 Cost

- **GitHub Actions**: Free (public repos have unlimited minutes)
- **Supabase**: Free tier (500MB database, 2GB bandwidth)
- **Total**: $0/month


##  Notes

- Weekends are automatically skipped (no processing on weekends)
- Debug mode is always on for transparency
- Logs are retained for 90 days in GitHub
- Each run takes 5-15 minutes depending on data volume

##  Contributing

Feel free to fork and modify for your needs. Pull requests welcome!


##  Disclaimer

This tool is for personal use. Respect the Czech government website's terms of service. The default configuration includes reasonable delays (1.5s) between requests to avoid server overload.

---
