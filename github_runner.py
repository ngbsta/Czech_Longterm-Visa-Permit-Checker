import os
import sys
import time
import requests
from datetime import datetime, timedelta, timezone
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.keys import Keys

# ==================================================
# CONFIG
# ==================================================
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
CHECK_URL = "https://ipc.gov.cz/en/status-of-your-application/"
APPLICATION_ID_FIELD = "id"
DELAY_BETWEEN_CHECKS = 1.5
MAX_NOT_FOUND_CONSECUTIVE = 8
DEBUG_MODE = True  # Her zaman açık

# Stats
stats = {
    "checked": 0,
    "approved": 0,
    "rejected": 0,
    "new_found": 0,
    "errors": 0
}

# ==================================================
# LOGGING
# ==================================================
def log(message, level="INFO"):
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    prefix = {
        "INFO": "ℹ️",
        "SUCCESS": "✅",
        "ERROR": "❌",
        "WARNING": "⚠️",
        "DEBUG": "🔍",
        "HIGHLIGHT": "📍"
    }.get(level, "•")
    
    print(f"[{timestamp}] {prefix} {message}")
    sys.stdout.flush()

# ==================================================
# SUPABASE HELPERS
# ==================================================
def get_headers():
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal"
    }

def supabase_select(table, filters=None):
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    params = {"select": "*"}
    if filters:
        params.update(filters)
    r = requests.get(url, headers=get_headers(), params=params, timeout=30)
    r.raise_for_status()
    return r.json()

def supabase_update(table, data, match_column, match_value):
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    params = {match_column: f"eq.{match_value}"}
    r = requests.patch(url, headers=get_headers(), json=data, params=params, timeout=30)
    r.raise_for_status()

def supabase_insert(table, data):
    try:
        url = f"{SUPABASE_URL}/rest/v1/{table}"
        headers = get_headers()
        headers["Prefer"] = "return=representation"
        r = requests.post(url, headers=headers, json=data, timeout=30)
        if r.status_code >= 400:
            log(f"Insert error ({table}): {r.status_code} - {r.text}", "ERROR")
            return False
        return True
    except Exception as e:
        log(f"Insert exception ({table}): {e}", "ERROR")
        return False

def application_exists(application_id):
    try:
        result = supabase_select("applications", {APPLICATION_ID_FIELD: f"eq.{application_id}"})
        exists = len(result) > 0
        return exists, result[0]["status"] if exists else None
    except Exception as e:
        log(f"DB error for {application_id}: {e}", "ERROR")
        stats["errors"] += 1
        return False, None

def is_weekend(date):
    return date.weekday() >= 5

# ==================================================
# SELENIUM SETUP
# ==================================================
def setup_driver():
    log("Setting up Chrome driver...", "DEBUG")
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    driver = webdriver.Chrome(options=options)
    log("Chrome driver ready", "SUCCESS")
    return driver

def init_page(driver):
    log(f"Loading page: {CHECK_URL}", "DEBUG")
    driver.get(CHECK_URL)
    time.sleep(2)
    try:
        refuse_btn = WebDriverWait(driver, 3).until(
            EC.element_to_be_clickable((By.XPATH, "//button[contains(text(),'Refuse all')]"))
        )
        refuse_btn.click()
        log("Cookie popup dismissed", "DEBUG")
        time.sleep(0.5)
    except:
        log("No cookie popup found (or already dismissed)", "DEBUG")
        pass

# ==================================================
# STATUS CHECK
# ==================================================
def check_application_status(driver, application_id, is_first_check=False):
    try:
        if is_first_check:
            init_page(driver)
        
        old_alert_text = ""
        try:
            old_alert = driver.find_element(By.CSS_SELECTOR, "div.alert__content")
            old_alert_text = old_alert.text
        except:
            pass
        
        input_box = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.NAME, "visaApplicationNumber"))
        )
        
        input_box.click()
        input_box.send_keys(Keys.CONTROL + "a")
        input_box.send_keys(Keys.DELETE)
        time.sleep(0.1)
        input_box.send_keys(application_id)
        
        submit_btn = driver.find_element(By.XPATH, "//button[@type='submit' and contains(@class,'button__primary')]")
        submit_btn.click()
        
        def alert_changed(driver):
            try:
                alert = driver.find_element(By.CSS_SELECTOR, "div.alert__content")
                new_text = alert.text
                return new_text != old_alert_text and application_id.lower() in new_text.lower()
            except:
                return False
        
        try:
            WebDriverWait(driver, 8).until(alert_changed)
        except TimeoutException:
            pass
        
        time.sleep(0.3)
        
        try:
            result = driver.find_element(By.CSS_SELECTOR, "div.alert__content")
            result_text = result.text.lower()
        except:
            log(f"Alert not found for {application_id}, refreshing page", "WARNING")
            init_page(driver)
            return "RETRY"
        
        if application_id.lower() not in result_text:
            log(f"Stale response for {application_id}, retrying", "WARNING")
            time.sleep(1)
            try:
                result = driver.find_element(By.CSS_SELECTOR, "div.alert__content")
                result_text = result.text.lower()
                if application_id.lower() not in result_text:
                    return "RETRY"
            except:
                return "RETRY"
        
        if "preliminarily assessed positively" in result_text:
            status = "APPROVED"
        elif "was rejected" in result_text:
            status = "REJECTED"
        elif "being processed" in result_text:
            status = "BEING_PROCESSED"
        elif "was not found" in result_text or "no application" in result_text or "not found" in result_text:
            status = "NOT_FOUND"
        else:
            status = "UNKNOWN"
        
        if DEBUG_MODE:
            emoji = {"APPROVED": "✅", "REJECTED": "❌", "BEING_PROCESSED": "⏳", "NOT_FOUND": "🔍", "UNKNOWN": "❓"}.get(status, "•")
            log(f"  {emoji} {application_id} → {status}", "DEBUG")
        
        return status
            
    except Exception as e:
        stats["errors"] += 1
        log(f"Error checking {application_id}: {str(e)[:100]}", "ERROR")
        return "ERROR"

def check_with_retry(driver, application_id, is_first=False, max_retries=2):
    for attempt in range(max_retries):
        status = check_application_status(driver, application_id, is_first and attempt == 0)
        if status != "RETRY":
            return status
        log(f"  Retry {attempt + 1}/{max_retries} for {application_id}", "DEBUG")
        init_page(driver)
        time.sleep(1)
    return "ERROR"

# ==================================================
# PART 1: Check BEING_PROCESSED Applications
# ==================================================
def run_part1(driver, is_first=True):
    log("=" * 60)
    log("PART 1: Checking BEING_PROCESSED applications", "INFO")
    log("=" * 60)
    
    try:
        log("Fetching BEING_PROCESSED applications from database...", "DEBUG")
        applications = supabase_select("applications", {"status": "eq.BEING_PROCESSED"})
        log(f"Found {len(applications)} applications to check", "INFO")
    except Exception as e:
        log(f"Database error: {e}", "ERROR")
        return

    if len(applications) == 0:
        log("No BEING_PROCESSED applications found. Skipping Part 1.", "INFO")
        return

    total = len(applications)
    status_changes = 0
    
    for idx, app in enumerate(applications, 1):
        application_id = app[APPLICATION_ID_FIELD]
        old_status = app["status"]
        
        log(f"[{idx}/{total}] Checking {application_id}...", "INFO")
        
        new_status = check_with_retry(driver, application_id, is_first and idx == 1)
        stats["checked"] += 1
        now = datetime.now(timezone.utc).isoformat()
        
        if new_status in ["APPROVED", "REJECTED"]:
            log(f"  🎯 STATUS CHANGE: {application_id} → {new_status}", "SUCCESS")
            supabase_update("applications", {"status": new_status, "last_checked": now}, 
                          APPLICATION_ID_FIELD, application_id)
            supabase_insert("changes", {
                "application_id": application_id,
                "old_status": old_status,
                "new_status": new_status,
                "changed_at": now,
                "is_read": False
            })
            status_changes += 1
            
            if new_status == "APPROVED":
                stats["approved"] += 1
            else:
                stats["rejected"] += 1
        elif new_status == "BEING_PROCESSED":
            log(f"  Still being processed", "DEBUG")
            supabase_update("applications", {"last_checked": now}, APPLICATION_ID_FIELD, application_id)
        elif new_status == "NOT_FOUND":
            log(f"  Not found on website", "WARNING")
            supabase_update("applications", {"last_checked": now}, APPLICATION_ID_FIELD, application_id)
        
        time.sleep(DELAY_BETWEEN_CHECKS)
    
    log(f"Part 1 complete: {status_changes} status changes found", "SUCCESS")
    log("")

# ==================================================
# PART 2: Discover NEW Applications
# ==================================================
def run_part2(driver, part2_start_date=None, part2_end_date=None, is_first=True):
    log("=" * 60)
    log("PART 2: Discovering NEW applications", "INFO")
    log("=" * 60)
    
    today = datetime.now(timezone.utc).date()
    start_date = part2_start_date if part2_start_date else today - timedelta(days=30)
    end_date = part2_end_date if part2_end_date else today
    
    log(f"Scanning period: {start_date.strftime('%d/%m/%Y')} → {end_date.strftime('%d/%m/%Y')}", "INFO")
    
    cities = ["ANKA", "ISTA"]
    total_new = 0
    first_check = is_first

    for city in cities:
        city_name = "Ankara" if city == "ANKA" else "Istanbul"
        log(f"{'='*60}", "HIGHLIGHT")
        log(f"Scanning {city_name}...", "HIGHLIGHT")
        log(f"{'='*60}", "HIGHLIGHT")
        
        current_date = start_date
        city_new = 0
        
        while current_date <= end_date:
            if is_weekend(current_date):
                log(f"  Skipping weekend: {current_date.strftime('%d/%m/%Y')}", "DEBUG")
                current_date += timedelta(days=1)
                continue
            
            date_str = current_date.strftime("%d/%m/%Y")
            log(f"Checking date: {date_str}", "INFO")
            
            consecutive_not_found = 0
            idx = 1
            day_found = 0
            
            while consecutive_not_found < MAX_NOT_FOUND_CONSECUTIVE:
                app_number = f"{city}{current_date.strftime('%Y%m%d')}{idx:04d}"
                
                exists, existing_status = application_exists(app_number)
                if exists:
                    if DEBUG_MODE:
                        log(f"  ⏭️  {app_number} already in DB ({existing_status})", "DEBUG")
                    idx += 1
                    consecutive_not_found = 0
                    continue
                
                status = check_with_retry(driver, app_number, first_check)
                first_check = False
                stats["checked"] += 1
                now = datetime.now(timezone.utc).isoformat()
                
                if status in ["APPROVED", "REJECTED", "BEING_PROCESSED"]:
                    emoji = "✅" if status == "APPROVED" else "❌" if status == "REJECTED" else "⏳"
                    log(f"  {emoji} NEW: {app_number} → {status}", "SUCCESS")
                    
                    city_code = app_number[:4]
                    city_name_db = "ankara" if city_code == "ANKA" else "istanbul"
                    submit_date_str = app_number[4:12]
                    submit_date = f"{submit_date_str[:4]}-{submit_date_str[4:6]}-{submit_date_str[6:8]}"
                    
                    supabase_insert("applications", {
                        "id": app_number,
                        "city": city_name_db,
                        "submit_date": submit_date,
                        "status": status,
                        "last_checked": now
                    })
                    supabase_insert("changes", {
                        "application_id": app_number,
                        "old_status": None,
                        "new_status": status,
                        "changed_at": now,
                        "is_read": False
                    })
                    
                    stats["new_found"] += 1
                    day_found += 1
                    city_new += 1
                    total_new += 1
                    consecutive_not_found = 0
                elif status == "NOT_FOUND":
                    consecutive_not_found += 1
                else:
                    consecutive_not_found += 1
                
                idx += 1
                time.sleep(DELAY_BETWEEN_CHECKS)
            
            if day_found > 0:
                log(f"  📊 {date_str}: +{day_found} new applications", "INFO")
            else:
                log(f"  📊 {date_str}: No new applications", "DEBUG")
            
            current_date += timedelta(days=1)
        
        log(f"{city_name} total: {city_new} new applications", "SUCCESS")
        log("")
    
    log(f"Part 2 complete: {total_new} total new applications found", "SUCCESS")

# ==================================================
# MAIN
# ==================================================
def main():
    if not SUPABASE_URL or not SUPABASE_KEY:
        log("ERROR: SUPABASE_URL and SUPABASE_KEY environment variables must be set!", "ERROR")
        sys.exit(1)
    
    log("=" * 60)
    log("🚀 VISA TRACKER PRO - GitHub Actions Runner", "SUCCESS")
    log("=" * 60)
    log(f"Debug Mode: {'ON' if DEBUG_MODE else 'OFF'}", "INFO")
    log(f"Started at: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}", "INFO")
    log("=" * 60)
    log("")
    
    driver = None
    start_time = time.time()
    
    try:
        driver = setup_driver()
        log("")
        
        # Part 1: BEING_PROCESSED kontrolü
        run_part1(driver, is_first=True)
        
        # Part 2: Son 30 gün taraması
        run_part2(driver, part2_start_date=None, part2_end_date=None, is_first=False)
        
    except Exception as e:
        log(f"Fatal error: {e}", "ERROR")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        if driver:
            driver.quit()
            log("Browser closed", "DEBUG")
    
    # Summary
    elapsed = time.time() - start_time
    log("")
    log("=" * 60)
    log("📊 RUN SUMMARY", "SUCCESS")
    log("=" * 60)
    log(f"Total checked: {stats['checked']}", "INFO")
    log(f"New found: {stats['new_found']}", "INFO")
    log(f"Approved: {stats['approved']}", "INFO")
    log(f"Rejected: {stats['rejected']}", "INFO")
    log(f"Errors: {stats['errors']}", "INFO")
    log(f"Duration: {int(elapsed // 60)}m {int(elapsed % 60)}s", "INFO")
    log(f"Finished at: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}", "INFO")
    log("=" * 60)

if __name__ == "__main__":
    main()
