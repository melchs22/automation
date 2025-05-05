import os
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
import git
from datetime import datetime
import shutil
import pandas as pd
import logging
from selenium.webdriver.chrome.options import Options

# Set up logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger()

# Environment variables (set in GitHub Actions secrets)
USERNAME = os.getenv("BODABODA_USERNAME")
PASSWORD = os.getenv("BODABODA_PASSWORD")
TESTAPP_REPO_URL = os.getenv("TESTAPP_REPO_URL")
GIT_TOKEN = os.getenv("GIT_TOKEN")

# Repository details
AUTOMATION_REPO_PATH = os.getenv("GITHUB_WORKSPACE", "/tmp/automation")
TESTAPP_REPO_PATH = os.path.join(os.path.dirname(AUTOMATION_REPO_PATH), "testapp")
REPO_REMOTE = "origin"
REPO_BRANCH = "main"

# Directories
DOWNLOAD_DIR = os.path.join(AUTOMATION_REPO_PATH, "downloads")
DATA_DIR = os.path.join(AUTOMATION_REPO_PATH, "data")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

# Wait time
WAIT_TIME = 15

def setup_driver(headless=True):
    options = Options()
    if headless:
        options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_experimental_option("prefs", {"download.default_directory": DOWNLOAD_DIR})
    return webdriver.Chrome(options=options)

def take_screenshot(driver, filename):
    try:
        driver.save_screenshot(os.path.join(AUTOMATION_REPO_PATH, filename))
        logger.info(f"Screenshot saved: {filename}")
    except Exception as e:
        logger.error(f"Failed to take screenshot: {str(e)}")

def download_rename_and_convert_csv(driver, url, page_name, file_name):
    logger.info(f"Navigating to {page_name} page: {url}")
    try:
        driver.get(url)
        time.sleep(WAIT_TIME)

        logger.info(f"Looking for CSV download button on {page_name} page...")
        csv_elements = WebDriverWait(driver, WAIT_TIME).until(
            EC.presence_of_all_elements_located((By.XPATH, "//*[contains(text(), 'CSV') or contains(@value, 'CSV')]"))
        )

        for element in csv_elements:
            try:
                logger.info(f"Attempting to click element: {element.text or element.get_attribute('value')}")
                driver.execute_script("arguments[0].click();", element)
                logger.info(f"CSV download initiated for {page_name}")
                time.sleep(WAIT_TIME * 2)

                downloaded_files = [f for f in os.listdir(DOWNLOAD_DIR) if f.endswith('.csv')]
                if not downloaded_files:
                    logger.warning(f"No CSV file found in download directory for {page_name}")
                    continue

                downloaded_file = max([os.path.join(DOWNLOAD_DIR, f) for f in downloaded_files], key=os.path.getctime)

                df = pd.read_csv(downloaded_file)
                new_filename = f"{file_name}.xlsx"
                new_filepath = os.path.join(DATA_DIR, new_filename)
                df.to_excel(new_filepath, index=False)

                os.remove(downloaded_file)
                logger.info(f"File converted to XLSX and saved to: {new_filepath}")
                return new_filename
            except Exception as click_error:
                logger.error(f"Failed to click element or process file: {str(click_error)}")
        else:
            logger.warning(f"No clickable CSV element found on {page_name} page")
            return None

    except TimeoutException:
        logger.error(f"CSV button not found within the timeout period on {page_name} page.")
        take_screenshot(driver, f"{page_name}_timeout.png")
    except Exception as e:
        logger.error(f"An error occurred while processing {page_name}: {str(e)}")
        take_screenshot(driver, f"{page_name}_error.png")
    return None

def push_to_git(repo, files, repo_type="automation"):
    try:
        output_dir = os.path.join(repo.working_dir, "data")

        # Discard local changes
        logger.info(f"Discarding local changes in {repo_type} repo...")
        repo.git.reset('--hard')
        repo.git.clean('-fd')

        # Remove existing XLSX files
        logger.info(f"Removing existing XLSX files in {output_dir}...")
        for file in os.listdir(output_dir):
            if file.endswith('.xlsx'):
                os.remove(os.path.join(output_dir, file))
                logger.info(f"Removed: {file}")

        # Ensure new files are in place
        for file in files:
            logger.info(f"Ensuring {file} is in {output_dir}")

        # Stage and commit
        repo.git.add(update=True)
        repo.git.add(os.path.join("data", "*"))
        commit_message = f"Update XLSX files - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        repo.index.commit(commit_message)
        logger.info(f"Committed changes in {repo_type} repo: {commit_message}")

        # Push changes
        repo.remotes[REPO_REMOTE].push()
        logger.info(f"Successfully pushed changes to {repo_type} repository.")

    except Exception as e:
        logger.error(f"Error in {repo_type} repo Git operation: {str(e)}")
        raise

def sync_to_testapp_repo():
    try:
        # Clone or update testapp repo
        if not os.path.exists(TESTAPP_REPO_PATH):
            auth_url = TESTAPP_REPO_URL.replace("https://", f"https://{GIT_TOKEN}@")
            logger.info(f"Cloning testapp repo from {TESTAPP_REPO_URL}...")
            git.Repo.clone_from(auth_url, TESTAPP_REPO_PATH)
        else:
            testapp_repo = git.Repo(TESTAPP_REPO_PATH)
            testapp_repo.remotes[REPO_REMOTE].pull()
            logger.info("Pulled latest changes in testapp repo.")

        testapp_repo = git.Repo(TESTAPP_REPO_PATH)
        testapp_data_dir = os.path.join(TESTAPP_REPO_PATH, "data")
        os.makedirs(testapp_data_dir, exist_ok=True)

        # Remove existing XLSX files
        logger.info("Removing existing XLSX files in testapp repo...")
        for file in os.listdir(testapp_data_dir):
            if file.endswith('.xlsx'):
                os.remove(os.path.join(testapp_data_dir, file))
                logger.info(f"Removed from testapp: {file}")

        # Copy new XLSX files
        for file in os.listdir(DATA_DIR):
            if file.endswith('.xlsx'):
                shutil.copy2(
                    os.path.join(DATA_DIR, file),
                    os.path.join(testapp_data_dir, file)
                )
                logger.info(f"Copied to testapp: {file}")

        # Stage, commit, and push
        testapp_repo.git.add(update=True)
        testapp_repo.git.add(os.path.join("data", "*"))
        commit_message = f"Sync XLSX files from automation repo - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        testapp_repo.index.commit(commit_message)
        testapp_repo.remotes[REPO_REMOTE].push()
        logger.info("Successfully synced XLSX files to testapp repository.")

    except Exception as e:
        logger.error(f"Error syncing to testapp repo: {str(e)}")
        raise

def main_job():
    driver = None
    try:
        driver = setup_driver(headless=True)

        # Login
        logger.info("Opening login page...")
        driver.get("https://backend.bodabodaunion.ug/admin")
        WebDriverWait(driver, WAIT_TIME).until(EC.presence_of_element_located((By.TAG_NAME, "body")))

        logger.info("Filling in username...")
        username_field = WebDriverWait(driver, WAIT_TIME).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "input[name='data[User][username]']"))
        )
        username_field.send_keys(USERNAME)

        logger.info("Filling in password...")
        password_field = WebDriverWait(driver, WAIT_TIME).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "input[name='data[User][password]']"))
        )
        password_field.send_keys(PASSWORD)

        logger.info("Clicking login button...")
        login_button = WebDriverWait(driver, WAIT_TIME).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "button[type='submit']"))
        )
        login_button.click()

        logger.info("Waiting for login to complete...")
        WebDriverWait(driver, WAIT_TIME).until(EC.url_changes("https://backend.bodabodaunion.ug/admin"))

        # Download CSVs
        pages = [
            ("https://backend.bodabodaunion.ug/admin/drivers", "Drivers", "DRIVERS"),
            ("https://backend.bodabodaunion.ug/admin/users/storeindex", "Active Passengers", "PASSENGERS"),
            ("https://backend.bodabodaunion.ug/admin/trips", "Trips", "BEER"),
            ("https://backend.bodabodaunion.ug/admin/transactions", "Transaction Manager", "TRANSACTIONS")
        ]

        xlsx_files = []
        for url, page_name, file_name in pages:
            file_path = download_rename_and_convert_csv(driver, url, page_name, file_name)
            if file_path:
                xlsx_files.append(file_path)
                logger.info(f"CSV downloaded and converted to XLSX for {page_name}")
            else:
                logger.warning(f"Failed to download and process CSV for {page_name}")

        if xlsx_files:
            logger.info("\nDownloaded and converted XLSX files:")
            for file in xlsx_files:
                logger.info(f"- {os.path.join(DATA_DIR, file)}")

            # Push to automation repo
            automation_repo = git.Repo(AUTOMATION_REPO_PATH)
            push_to_git(automation_repo, xlsx_files, repo_type="automation")

            # Sync to testapp repo
            sync_to_testapp_repo()
        else:
            logger.warning("\nNo files were successfully downloaded and converted.")

    except WebDriverException as e:
        logger.error(f"WebDriver error: {str(e)}")
        take_screenshot(driver, "webdriver_error.png")
    except Exception as e:
        logger.error(f"Error in main job: {str(e)}")
        take_screenshot(driver, "general_error.png")
    finally:
        if driver:
            driver.quit()
            logger.info("Browser closed.")

if __name__ == "__main__":
    main_job()
