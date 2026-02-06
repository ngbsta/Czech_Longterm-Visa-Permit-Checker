 Czech Republic Visa Application Tracker

Automated visa application tracking system for Czech Republic consulates (Ankara & Istanbul) using GitHub Actions.

 Features

 **Part 1**: Monitors BEING_PROCESSED applications for status changes (Approved/Rejected)
 **Part 2**: Scans for new applications in the last 30 days
 **Runs automatically every 6 hours** (00:00, 06:00, 12:00, 18:00 UTC)
 **Debug mode always on** - detailed logs in GitHub Actions
**Supabase storage** - all data stored in PostgreSQL database
**Completely free** - runs on GitHub's infrastructure

##  Architecture

The system consists of two parts:

### Part 1: Status Monitoring
- Fetches all applications with `BEING_PROCESSED` status from database
- Checks each one on the official Czech government website
- Updates database when status changes to `APPROVED` or `REJECTED`
- Records all changes in the `changes` table

### Part 2: New Application Discovery
- Scans the last 30 days for new applications
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
