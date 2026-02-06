🔍 Czech Republic Visa Application Tracker
Automated visa application tracking system for Czech Republic consulates using GitHub Actions. Monitors application status changes and discovers new applications automatically.
🌟 Features

✅ Automated Monitoring: Runs every 6 hours on GitHub Actions (completely free)
🔍 Status Tracking: Monitors BEING_PROCESSED applications for status changes
🆕 New Application Discovery: Scans for new visa applications in specified date ranges
📊 Supabase Integration: Stores all data in your Supabase database
🪵 Detailed Logging: Debug mode always on - see every step in GitHub Actions logs
🔄 No Server Required: Runs entirely on GitHub's infrastructure

🏗️ Architecture

Part 1: Checks all BEING_PROCESSED applications for status updates (Approved/Rejected)
Part 2: Scans for new applications in the last 30 days (configurable)
Data Storage: PostgreSQL database via Supabase
Automation: GitHub Actions (scheduled + manual triggers)

📋 Prerequisites

GitHub Account (free)
Supabase Account (free tier is sufficient)
Basic knowledge of Git

🚀 Setup Instructions
Step 1: Create Supabase Database

Go to Supabase and create a free account
Create a new project
Go to SQL Editor and run this schema:

sql-- Applications table
CREATE TABLE applications (
    id TEXT PRIMARY KEY,
    city TEXT NOT NULL,
    submit_date DATE NOT NULL,
    status TEXT NOT NULL,
    last_checked TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Changes/Activity log table
CREATE TABLE changes (
    id BIGSERIAL PRIMARY KEY,
    application_id TEXT NOT NULL,
    old_status TEXT,
    new_status TEXT NOT NULL,
    changed_at TIMESTAMPTZ DEFAULT NOW(),
    is_read BOOLEAN DEFAULT FALSE,
    FOREIGN KEY (application_id) REFERENCES applications(id)
);

-- Indexes for better performance
CREATE INDEX idx_applications_status ON applications(status);
CREATE INDEX idx_applications_submit_date ON applications(submit_date);
CREATE INDEX idx_applications_city ON applications(city);
CREATE INDEX idx_changes_application_id ON changes(application_id);
CREATE INDEX idx_changes_changed_at ON changes(changed_at DESC);

Get your credentials:

Go to Project Settings → API
Copy Project URL (looks like: https://xxxxx.supabase.co)
Copy service_role key (under "Project API keys" → "service_role")
⚠️ Keep these private!



Step 2: Fork/Clone This Repository
Option A: Fork (Recommended)

Click the "Fork" button at the top right of this page
This creates your own copy of the repository

Option B: Create New Repository
bash# Create a new repository on GitHub named "visa-tracker"
# Clone it to your computer
git clone https://github.com/YOUR_USERNAME/visa-tracker.git
cd visa-tracker

# Copy all files from this repository
# Then push to your repository
git add .
git commit -m "Initial setup"
git push origin main
Step 3: Configure GitHub Secrets

Go to your repository on GitHub
Click Settings → Secrets and variables → Actions
Click New repository secret
Add these two secrets:

Secret 1: SUPABASE_URL

Name: SUPABASE_URL
Value: Your Supabase Project URL (from Step 1)
Click "Add secret"

Secret 2: SUPABASE_KEY

Name: SUPABASE_KEY
Value: Your Supabase service_role key (from Step 1)
Click "Add secret"

Step 4: Initial Data Collection
Before the automation starts, you need to populate your database with initial data.

Open github_runner.py in your repository
Find the run_part2() function (around line 280)
Modify the date range for your initial scrape:

python# Change these lines (around line 290):
today = datetime.now(timezone.utc).date()
start_date = today - timedelta(days=30)  # Change 30 to 90 or 180 for more history
end_date = today
Example for 90 days of history:
pythonstart_date = today - timedelta(days=90)  # Scrape last 90 days
Example for specific date range:
pythonstart_date = datetime(2024, 11, 1).date()  # Start: November 1, 2024
end_date = today  # End: Today

Commit and push the changes:

bashgit add github_runner.py
git commit -m "Configure initial scrape period"
git push origin main
Step 5: Run Initial Scrape

Go to your repository on GitHub
Click the Actions tab
Select Visa Tracker Auto Check workflow
Click Run workflow (top right)
Click the green Run workflow button
Wait for it to complete (⚠️ This may take 30-60 minutes depending on date range)

Step 6: Reset to Normal Operations
After the initial scrape completes:

Edit github_runner.py again
Change back to 30 days (for daily maintenance):

pythonstart_date = today - timedelta(days=30)  # Back to 30 days

Commit and push:

bashgit add github_runner.py
git commit -m "Reset to normal 30-day scan"
git push origin main
Step 7: Enable Automatic Scheduling
The workflow is now set to run automatically every 6 hours:

00:00 UTC (3:00 AM Turkey time)
06:00 UTC (9:00 AM Turkey time)
12:00 UTC (3:00 PM Turkey time)
18:00 UTC (9:00 PM Turkey time)

No additional configuration needed!
📊 Monitoring
View Logs

Go to Actions tab in your repository
Click on the latest workflow run
Click on check-visas job
Expand each step to see detailed logs:

Run Visa Tracker → See all application checks
Debug logs show every application ID and its status



Data in Supabase

Go to your Supabase project
Click Table Editor
View tables:

applications: All visa applications and their current status
changes: History of all status changes



Manual Trigger
You can run the workflow anytime:

Actions → Visa Tracker Auto Check
Run workflow → Run workflow

⚙️ Configuration
Adjust Scan Period
Edit github_runner.py, line ~290:
pythonstart_date = today - timedelta(days=30)  # Change this number
Adjust Run Frequency
Edit .github/workflows/visa-checker.yml, line 5:
yaml- cron: '0 */6 * * *'  # Every 6 hours
# - cron: '0 */3 * * *'  # Every 3 hours
# - cron: '0 9,21 * * *'  # 9 AM and 9 PM UTC only
Cities Monitored
Currently monitors:

ANKA: Ankara Consulate
ISTA: Istanbul Consulate

To add more cities, edit github_runner.py, line ~297:
pythoncities = ["ANKA", "ISTA", "XXXX"]  # Add new city codes
🧪 Testing
Test Locally (Optional)
If you want to test before deploying:
bash# Install dependencies
pip install selenium requests

# Set environment variables
export SUPABASE_URL="your_url_here"
export SUPABASE_KEY="your_key_here"

# Run
python github_runner.py
💰 Cost

GitHub Actions: 2,000 free minutes/month (public repos get unlimited)
Supabase: 500 MB database, 2 GB bandwidth (free tier)
Total: $0/month ✅

📝 Notes

First run will take longer (populating database)
Subsequent runs only check for changes (faster)
GitHub Actions logs are kept for 90 days
Weekends are skipped (consulates don't process applications)

🛠️ Troubleshooting
"Error: SUPABASE_URL and SUPABASE_KEY must be set"

Check that you added both secrets in GitHub Settings
Secret names must match exactly: SUPABASE_URL and SUPABASE_KEY

"Error: relation 'applications' does not exist"

Run the SQL schema from Step 1 in Supabase SQL Editor

Workflow not running automatically

Make sure your repository is public (or you have GitHub Actions minutes)
Check Actions tab is enabled in repository settings

ChromeDriver errors

These are automatically handled in the workflow
If persistent, the workflow will retry

🤝 Contributing
Contributions are welcome! Please open an issue or submit a pull request.
📄 License
MIT License - feel free to use and modify.
⚠️ Disclaimer
This tool is for personal use only. Please respect the Czech government website's terms of service and don't abuse their system with excessive requests. The current configuration includes reasonable delays between requests.
