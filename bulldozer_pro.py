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
DEBUG_MODE = True 

# Retry config for Supabase API calls
MAX_API_RETRIES = 3
API_RETRY_DELAY = 5  # seconds between retries
RETRYABLE_STATUS_CODES = {502, 503, 504, 429}

# Stats
stats = {
    "checked": 0,
    "approved": 0,
    "rejected": 0,
    "new_found": 0,
    "errors": 0,
    "api_retries": 0
}

# ==================================================
# LOGGING
# ==================================================
def log(message, level="INFO"):
    timestamp = datetime.now(timezone.utc).strftime("%H:%M:%S")
    prefix = {
        "INFO": "ℹ️",
        "SUCCESS": "✅",
        "ERROR": "❌",
        "WARNING": "⚠️",
        "DEBUG": "🔍",
        "HIGHLIGHT": "📍",
        "DIM": "•"
    }.get(level, "•")
    
    print(f"[{timestamp}] {prefix} {message}")
    sys.stdout.flush()

# ==================================================
# RETRY WRAPPER FOR SUPABASE API CALLS
# ==================================================
def supabase_request_with_retry(method, url, max_retries=MAX_API_RETRIES, **kwargs):
    """
    Generic retry wrapper for Supabase HTTP requests.
    Retries on 502/503/504/429 and connection errors.
    """
    last_exception = None
    
    for attempt in range(max_retries):
        try:
            if method == "GET":
                r = requests.get(url, **kwargs)
            elif method == "POST":
                r = requests.post(url, **kwargs)
            elif method == "PATCH":
                r = requests.patch(url, **kwargs)
            else:
                raise ValueError(f"Unsupported method: {method}")
            
            # If status code is retryable, retry
            if r.status_code in RETRYABLE_STATUS_CODES:
                stats["api_retries"] += 1
                wait_time = API_RETRY_DELAY * (attempt + 1)  # exponential-ish backoff
                log(f"   🔄 Supabase {r.status_code} error, retrying in {wait_time}s... (attempt {attempt + 1}/{max_retries})", "WARNING")
                time.sleep(wait_time)
                continue
            
            # For other errors, raise immediately
            r.raise_for_status()
            return r
            
        except requests.exceptions.ConnectionError as e:
            stats["api_retries"] += 1
            last_exception = e
            wait_time = API_RETRY_DELAY * (attempt + 1)
            log(f"   🔄 Connection error, retrying in {wait_time}s... (attempt {attempt + 1}/{max_retries})", "WARNING")
            time.sleep(wait_time)
        except requests.exceptions.HTTPError as e:
            # Non-retryable HTTP errors — raise immediately
            raise
        except requests.exceptions.Timeout as e:
            stats["api_retries"] += 1
            last_exception = e
            wait_time = API_RETRY_DELAY * (attempt + 1)
            log(f"   🔄 Timeout, retrying in {wait_time}s... (attempt {attempt + 1}/{max_retries})", "WARNING")
            time.sleep(wait_time)
    
    # All retries exhausted
    if last_exception:
        raise last_exception
    raise requests.exceptions.HTTPError(f"Max retries ({max_retries}) exhausted for {url}")

# ==================================================
# SUPABASE HELPERS (with retry)
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
    r = supabase_request_with_retry("GET", url, headers=get_headers(), params=params, timeout=30)
    return r.json()

def supabase_update(table, data, match_column, match_value):
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    params = {match_column: f"eq.{match_value}"}
    supabase_request_with_retry("PATCH", url, headers=get_headers(), json=data, params=params, timeout=30)

def supabase_insert(table, data):
    try:
        url = f"{SUPABASE_URL}/rest/v1/{table}"
        headers = get_headers()
        headers["Prefer"] = "return=representation"
        r = supabase_request_with_retry("POST", url, headers=headers, json=data, timeout=30)
        return True
    except Exception as e:
        log(f"Insert exception ({table}): {e}", "ERROR")
        stats["errors"] += 1
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
    """Sayfa ilk yüklemesi ve cookie popup kapatma"""
    log(f"Loading page...", "DEBUG")
    driver.get(CHECK_URL)
    time.sleep(2)
    try:
        refuse_btn = WebDriverWait(driver, 3).until(
            EC.element_to_be_clickable((By.XPATH, "//button[contains(text(),'Refuse all')]"))
        )
        refuse_btn.click()
        log("🍪 Cookie popup dismissed", "DIM")
        time.sleep(0.5)
    except:
        pass

def recover_browser(driver):
    """Browser recovery: refresh page, dismiss cookies, ready for next check"""
    log("   🔧 Recovering browser session...", "WARNING")
    try:
        init_page(driver)
        log("   🔧 Browser recovered successfully", "SUCCESS")
        return True
    except Exception as e:
        log(f"   🔧 Browser recovery failed: {e}", "ERROR")
        return False

# ==================================================
# FAST STATUS CHECK - NO PAGE REFRESH
# ==================================================
def check_application_status(driver, application_id, is_first_check=False):
    """
    Hızlı kontrol - sayfa yenileme YOK.
    Sadece input temizle, yeni ID gir, submit et, yeni alert bekle.
    """
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
            log(f"   ⚠️ Alert not found, refreshing page...", "WARNING")
            init_page(driver)
            return "RETRY"
        
        if DEBUG_MODE:
            if "preliminarily assessed positively" in result_text:
                log(f"   🔍 [{application_id}]: Approved!", "SUCCESS")
            elif "was rejected" in result_text:
                log(f"   🔍 [{application_id}]: Rejected", "ERROR")
            elif "being processed" in result_text:
                log(f"   🔍 [{application_id}]: Being Processed", "WARNING")
            elif "was not found" in result_text or "no application" in result_text or "not found" in result_text:
                log(f"   🔍 [{application_id}]: Not Found", "DIM")
            else:
                log(f"   🔍 [{application_id}]: Unknown", "DEBUG")
        
        if application_id.lower() not in result_text:
            log(f"   ⚠️ Stale response, retrying...", "WARNING")
            time.sleep(1)
            try:
                result = driver.find_element(By.CSS_SELECTOR, "div.alert__content")
                result_text = result.text.lower()
                if application_id.lower() not in result_text:
                    return "RETRY"
            except:
                return "RETRY"
        
        if "preliminarily assessed positively" in result_text:
            return "APPROVED"
        elif "was rejected" in result_text:
            return "REJECTED"
        elif "being processed" in result_text:
            return "BEING_PROCESSED"
        elif "was not found" in result_text or "no application" in result_text or "not found" in result_text:
            return "NOT_FOUND"
        else:
            return "UNKNOWN"
            
    except Exception as e:
        stats["errors"] += 1
        log(f"❌ Error: {application_id} - {str(e)[:50]}", "ERROR")
        return "ERROR"

def check_with_retry(driver, application_id, is_first=False, max_retries=2):
    """Retry mekanizması ile kontrol"""
    for attempt in range(max_retries):
        status = check_application_status(driver, application_id, is_first and attempt == 0)
        if status != "RETRY":
            return status
        log(f"   🔄 Retry {attempt + 1}/{max_retries} for {application_id}", "DIM")
        init_page(driver) 
        time.sleep(1)
    return "ERROR"

# ==================================================
# PART 1: Check BEING_PROCESSED Applications
# ==================================================
def run_part1(driver, is_first=True):
    log("=" * 60, "DIM")
    log("📋 PART 1: Checking BEING_PROCESSED applications", "INFO")
    log("─" * 60, "DIM")
    
    try:
        log("Fetching BEING_PROCESSED applications from database...", "DEBUG")
        applications = supabase_select("applications", {"status": "eq.BEING_PROCESSED"})
        log(f"   Found {len(applications)} applications to check", "INFO")
    except Exception as e:
        log(f"❌ Database error: {e}", "ERROR")
        return

    if len(applications) == 0:
        log("No BEING_PROCESSED applications found. Skipping Part 1.", "INFO")
        log("", "DIM")
        return

    total = len(applications)
    status_changes = 0
    
    if is_first:
        init_page(driver)
    
    for idx, app in enumerate(applications, 1):
        application_id = app[APPLICATION_ID_FIELD]
        old_status = app["status"]
        
        log(f"[{idx}/{total}] Checking {application_id}...", "INFO")
        
        new_status = check_with_retry(driver, application_id, is_first=False)
        stats["checked"] += 1
        now = datetime.now(timezone.utc).isoformat()
        
        if new_status in ["APPROVED", "REJECTED"]:
            emoji = "✅" if new_status == "APPROVED" else "❌"
            log(f"   {emoji} CHANGE: {application_id} → {new_status}", "SUCCESS")
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
            supabase_update("applications", {"last_checked": now}, APPLICATION_ID_FIELD, application_id)
        elif new_status == "NOT_FOUND":
            log(f"   ⚠️ {application_id} not found on website", "WARNING")
            supabase_update("applications", {"last_checked": now}, APPLICATION_ID_FIELD, application_id)
        
        time.sleep(DELAY_BETWEEN_CHECKS)
    
    log(f"\n   ✓ Part 1 complete: {status_changes} changes found", "SUCCESS" if status_changes else "DIM")
    log("", "DIM")

# ==================================================
# PART 2: Discover NEW Applications
# ==================================================
def run_part2(driver, part2_start_date=None, part2_end_date=None, is_first=True):
    log("=" * 60, "DIM")
    log("🔎 PART 2: Discovering NEW applications", "INFO")
    log("─" * 60, "DIM")
    
    today = datetime.now(timezone.utc).date()
    start_date = part2_start_date if part2_start_date else today - timedelta(days=60)
    end_date = part2_end_date if part2_end_date else today
    
    log(f"   Scanning: {start_date.strftime('%d/%m/%Y')} → {end_date.strftime('%d/%m/%Y')}", "INFO")
    
    cities = ["ANKA", "ISTA"]
    total_new = 0
    first_check = is_first

    if first_check:
        init_page(driver)
        first_check = False

    for city in cities:
        city_name = "Ankara" if city == "ANKA" else "Istanbul"
        log("", "DIM")
        log(f"📍 {city_name}", "HIGHLIGHT")
        
        current_date = start_date
        city_new = 0
        
        while current_date <= end_date:
            if is_weekend(current_date):
                current_date += timedelta(days=1)
                continue
            
            date_str = current_date.strftime("%d/%m/%Y")
            log(f"   Checking date: {date_str}", "INFO")
            
            consecutive_not_found = 0
            idx = 1
            day_found = 0
            
            while consecutive_not_found < MAX_NOT_FOUND_CONSECUTIVE:
                app_number = f"{city}{current_date.strftime('%Y%m%d')}{idx:04d}"
                
                exists, existing_status = application_exists(app_number)
                if exists:
                    idx += 1
                    consecutive_not_found = 0
                    continue
                
                status = check_with_retry(driver, app_number, is_first=False)
                stats["checked"] += 1
                now = datetime.now(timezone.utc).isoformat()
                
                if status in ["APPROVED", "REJECTED", "BEING_PROCESSED"]:
                    emoji = "✅" if status == "APPROVED" else "❌" if status == "REJECTED" else "⏳"
                    log(f"      {emoji} {app_number} → {status}", "SUCCESS")
                    
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
                log(f"      {date_str}: +{day_found} new", "DIM")
            
            current_date += timedelta(days=1)
        
        log(f"      {city_name} total: {city_new} new applications", "INFO")
    
    log(f"\n   ✓ Part 2 complete: {total_new} new applications found", "SUCCESS" if total_new else "DIM")
    log("", "DIM")

# ==================================================
# MAIN
# ==================================================
def main():
    if not SUPABASE_URL or not SUPABASE_KEY:
        log("ERROR: SUPABASE_URL and SUPABASE_KEY environment variables must be set!", "ERROR")
        sys.exit(1)
    
    log("=" * 60, "DIM")
    log(" 🚧 CAUTION! 🚧  🚜 BULLDOZER PRO STARTED! ", "SUCCESS")
    log("=" * 60, "DIM")
    log(f"Debug Mode: {'ON' if DEBUG_MODE else 'OFF'}", "INFO")
    log(f"Started at: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}", "INFO")
    log("=" * 60, "DIM")
    log("", "DIM")
    
    driver = None
    start_time = time.time()
    
    try:
        driver = setup_driver()
        log("", "DIM")
        
        run_part1(driver, is_first=True)
        
        run_part2(driver, part2_start_date=None, part2_end_date=None, is_first=False)
        
    except Exception as e:
        log(f"Fatal error: {e}", "ERROR")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        if driver:
            driver.quit()
            log("🌐 Browser closed", "DIM")
    
    elapsed = time.time() - start_time
    log("", "DIM")
    log("=" * 60, "DIM")
    log("📊 RUN SUMMARY", "SUCCESS")
    log("=" * 60, "DIM")
    log(f"Total checked: {stats['checked']}", "INFO")
    log(f"New found: {stats['new_found']}", "INFO")
    log(f"Approved: {stats['approved']}", "INFO")
    log(f"Rejected: {stats['rejected']}", "INFO")
    log(f"Errors: {stats['errors']}", "INFO")
    log(f"API retries: {stats['api_retries']}", "INFO")
    log(f"Duration: {int(elapsed // 60)}m {int(elapsed % 60)}s", "INFO")
    log(f"Finished at: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}", "INFO")
    log("=" * 60, "DIM")

if __name__ == "__main__":
    main()
