import os
import time
import logging
import traceback
import undetected_chromedriver as uc
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.common.exceptions import TimeoutException, NoSuchElementException

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def setup_driver():
    """Set up and return an undetected ChromeDriver instance."""
    try:
        logger.info("Setting up undetected ChromeDriver...")
        options = uc.ChromeOptions()
        options.add_argument('--no-sandbox')
        options.add_argument('--window-size=1920,1080')
        
        # Configure download behavior
        prefs = {
            'download.default_directory': os.path.join(os.getcwd(), "invoices"),
            'download.prompt_for_download': False,
            'download.directory_upgrade': True,
            'safebrowsing.enabled': True
        }
        options.add_experimental_option('prefs', prefs)
        
        # Create driver instance
        driver = uc.Chrome(options=options)
        logger.info("ChromeDriver setup completed successfully")
        return driver
        
    except Exception as e:
        logger.error(f"Error setting up ChromeDriver: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise

def login(driver, email, password):
    logger.info("Attempting to log in...")
    try:
        driver.get("https://dev.runwayml.com/")
        wait = WebDriverWait(driver, 20)
        
        # Click the initial login button using JavaScript
        logger.info("Clicking initial login button...")
        login_button = wait.until(EC.presence_of_element_located((By.XPATH, "//button[.//span[text()='Login']]")))
        driver.execute_script("arguments[0].scrollIntoView(true);", login_button)
        time.sleep(1)  # Wait for scroll to complete
        driver.execute_script("arguments[0].click();", login_button)
        
        # Wait for URL to change after login button click
        logger.info("Waiting for login page to load...")
        wait.until(lambda driver: "auth" in driver.current_url.lower())
        
        # Wait for login form and input fields with more specific selectors
        logger.info("Waiting for login form...")
        email_field = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='email']")))
        password_field = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='password']")))
        
        # Input credentials
        logger.info("Entering credentials...")
        email_field.clear()
        email_field.send_keys(email)
        password_field.clear()
        password_field.send_keys(password)
        
        # Find and click login button
        logger.info("Attempting to click login button...")
        login_button = wait.until(EC.element_to_be_clickable(
            (By.XPATH, "//button[contains(text(), 'Log in')]")
        ))
        login_button.click()
        
        # Wait for successful login
        logger.info("Waiting for login completion...")
        wait.until(EC.url_changes("https://dev.runwayml.com/"))
        logger.info("Login successful!")
        
    except TimeoutException as e:
        logger.error(f"Timeout during login: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Error during login: {str(e)}")
        raise

def download_invoices(driver):
    logger.info("Starting invoice download process...")
    try:
        # Create invoices directory if it doesn't exist
        invoice_dir = os.path.join(os.getcwd(), "invoices")
        os.makedirs(invoice_dir, exist_ok=True)
        logger.info(f"Created/verified invoices directory at: {invoice_dir}")
        
        # Navigate to billing/invoices page
        logger.info("Navigating to invoices page...")
        driver.get("https://dev.runwayml.com/billing/invoices")
        
        # Wait for invoice links to be present
        wait = WebDriverWait(driver, 20)
        logger.info("Waiting for invoice links to load...")
        invoice_links = wait.until(EC.presence_of_all_elements_located(
            (By.XPATH, "//a[contains(@href, '/invoice')]")
        ))
        
        logger.info(f"Found {len(invoice_links)} invoice links")
        
        # Download each invoice
        for i, link in enumerate(invoice_links, 1):
            try:
                logger.info(f"Downloading invoice {i}/{len(invoice_links)}...")
                wait.until(EC.element_to_be_clickable(link))
                link.click()
                time.sleep(3)  # Wait for download to start and complete
            except Exception as e:
                logger.error(f"Error downloading invoice {i}: {str(e)}")
                continue
        
        logger.info("Invoice download process completed!")
        
    except TimeoutException as e:
        logger.error(f"Timeout while downloading invoices: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Error during invoice download: {str(e)}")
        raise

def check_for_captcha(driver):
    """Check if a captcha is present on the page"""
    try:
        # Common captcha iframe identifiers
        captcha_elements = driver.find_elements(By.CSS_SELECTOR, 
            "iframe[src*='recaptcha'], iframe[src*='hcaptcha'], div.g-recaptcha, div.h-captcha")
        return len(captcha_elements) > 0
    except:
        return False

def cleanup_temp_dir(temp_dir):
    """Clean up temporary Chrome data directory."""
    try:
        if os.path.exists(temp_dir):
            import shutil
            shutil.rmtree(temp_dir)
            logger.info(f"Cleaned up temporary directory: {temp_dir}")
    except Exception as e:
        logger.warning(f"Failed to clean up temporary directory: {str(e)}")

def main():
    # Get credentials from environment variables
    email = os.getenv('RUNWAY_EMAIL')
    password = os.getenv('RUNWAY_PASSWORD')
    
    if not email or not password:
        raise ValueError("RUNWAY_EMAIL and RUNWAY_PASSWORD environment variables must be set")
    
    logger.info("Starting invoice download script...")
    driver = None
    temp_dir = None
    try:
        # Kill any existing Chrome processes
        os.system("pkill -f chrome")
        os.system("pkill -f chromium")
        time.sleep(2)  # Wait for processes to be killed
        
        # Create temp directory
        temp_dir = f"/tmp/chrome_data_{int(time.time())}"
        os.makedirs(temp_dir, exist_ok=True)
        
        driver = setup_driver()
        
        # Attempt login
        login(driver, email, password)
        
        # Check for captcha after login attempt
        if check_for_captcha(driver):
            logger.warning("Captcha detected! User assistance required.")
            raise Exception("Captcha detected - Please solve the captcha manually.")
        
        # Proceed with invoice download
        download_invoices(driver)
        logger.info("Script completed successfully!")
        
    except Exception as e:
        logger.error(f"An error occurred during script execution: {str(e)}")
        raise
    finally:
        if driver:
            try:
                driver.quit()
                logger.info("Browser session closed.")
            except Exception as e:
                logger.warning(f"Error closing browser: {str(e)}")
        
        if temp_dir:
            cleanup_temp_dir(temp_dir)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.error(f"Script failed: {str(e)}")
        exit(1)
