import os
import smtplib
import traceback
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from playwright.sync_api import sync_playwright, TimeoutError
import time
from datetime import datetime
import requests
import tempfile
import sys

# Get environment variables
openai_email = os.environ.get('OPENAI_EMAIL')
openai_password = os.environ.get('OPENAI_PASSWORD')
email_recipient = os.environ.get('EMAIL_RECIPIENT')
email_sender = os.environ.get('EMAIL_SENDER')
email_password = os.environ.get('EMAIL_PASSWORD')

# Verbose printing for debugging
def debug_print(message):
    print(f"DEBUG [{datetime.now().strftime('%H:%M:%S')}]: {message}")
    sys.stdout.flush()  # Force output to be written immediately

def login_and_get_invoice():
    debug_print(f"Starting browser automation with email: {openai_email[:3]}...{openai_email[-3:] if len(openai_email) > 6 else openai_email}")
    
    with sync_playwright() as p:
        debug_print("Launching browser")
        # Use slower, more stable settings
        browser = p.chromium.launch(headless=True, slow_mo=100)  # Add slight delay between actions
        context = browser.new_context(
            viewport={"width": 1280, "height": 1024},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        )
        page = context.new_page()
        
        # Increase timeouts
        page.set_default_timeout(120000)  # Increase default timeout to 2 minutes
        
        try:
            # Go to OpenAI login page
            debug_print("Navigating to login page")
            page.goto('https://chat.openai.com/auth/login', wait_until="networkidle")
            page.screenshot(path="login_page.png")
            
            # Wait for login page to load and click Log in button
            debug_print("Waiting for login button")
            try:
                page.wait_for_selector('button:has-text("Log in")', timeout=60000)
                page.click('button:has-text("Log in")')
            except TimeoutError:
                debug_print("Couldn't find 'Log in' button, trying alternative approach")
                page.screenshot(path="no_login_button.png")
                
                # Try alternative selectors or flow
                if page.url.startswith("https://chat.openai.com/"):
                    debug_print("Already on ChatGPT page, may be logged in")
                else:
                    debug_print("Trying different login approach")
                    page.goto('https://platform.openai.com/login', wait_until="networkidle")
                    page.screenshot(path="alt_login_page.png")
            
            # Try to detect if we're already logged in
            if "chat.openai.com/auth/login" not in page.url and "platform.openai.com/login" not in page.url:
                debug_print(f"Possibly already logged in, current URL: {page.url}")
            else:
                # Fill in email
                debug_print("Looking for username field")
                page.screenshot(path="before_username.png")
                
                try:
                    # Wait and try different possible selectors for the email field
                    email_selector = None
                    for selector in ['input[name="username"]', 'input[type="email"]', 'input[placeholder*="email" i]']:
                        if page.query_selector(selector):
                            email_selector = selector
                            break
                    
                    if email_selector:
                        debug_print(f"Found email field with selector: {email_selector}")
                        page.fill(email_selector, openai_email)
                        
                        # Look for continue button
                        continue_button = None
                        for btn_selector in ['button:has-text("Continue")', 'button[type="submit"]', 'button.continue-btn']:
                            if page.query_selector(btn_selector):
                                continue_button = btn_selector
                                break
                        
                        if continue_button:
                            debug_print(f"Clicking continue button: {continue_button}")
                            page.click(continue_button)
                        else:
                            debug_print("No continue button found, trying to press Enter")
                            page.press(email_selector, "Enter")
                    else:
                        debug_print("Could not find email input field")
                        page.screenshot(path="email_field_not_found.png")
                        raise Exception("Email input field not found")
                        
                    # Fill in password
                    debug_print("Waiting for password field")
                    page.wait_for_selector('input[name="password"], input[type="password"]', timeout=60000)
                    page.screenshot(path="password_page.png")
                    
                    password_selector = None
                    for selector in ['input[name="password"]', 'input[type="password"]']:
                        if page.query_selector(selector):
                            password_selector = selector
                            break
                    
                    if password_selector:
                        debug_print("Entering password")
                        page.fill(password_selector, openai_password)
                        
                        # Look for login button
                        login_button = None
                        for btn_selector in ['button[type="submit"]', 'button:has-text("Log in")']:
                            if page.query_selector(btn_selector):
                                login_button = btn_selector
                                break
                        
                        if login_button:
                            debug_print(f"Clicking login button: {login_button}")
                            page.click(login_button)
                        else:
                            debug_print("No login button found, trying to press Enter")
                            page.press(password_selector, "Enter")
                    else:
                        debug_print("Could not find password field")
                        page.screenshot(path="password_field_not_found.png")
                        raise Exception("Password field not found")
                
                except Exception as e:
                    debug_print(f"Error during login attempt: {e}")
                    page.screenshot(path="login_error.png")
                    raise
            
            # Wait for login to complete
            debug_print("Waiting for login to complete")
            try:
                page.wait_for_url('https://chat.openai.com/**', timeout=60000)
                debug_print(f"Login successful, current URL: {page.url}")
            except TimeoutError:
                debug_print(f"Didn't reach expected URL after login, current URL: {page.url}")
                # If we didn't reach the expected URL but we're not on the login page anymore,
                # we might still be logged in
                if "login" not in page.url:
                    debug_print("Not on login page, assuming login successful")
                else:
                    page.screenshot(path="login_timeout.png")
                    raise Exception("Login timeout - couldn't reach expected page")
            
            # Take screenshot after login
            page.screenshot(path="after_login.png")
            
            # Navigate to billing page with retry logic
            debug_print("Navigating to billing page")
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    page.goto('https://platform.openai.com/account/billing/payment-history', wait_until="networkidle", timeout=60000)
                    break
                except TimeoutError:
                    if attempt < max_retries - 1:
                        debug_print(f"Timeout navigating to billing page, attempt {attempt + 1}/{max_retries}, retrying...")
                        time.sleep(5)  # Wait before retry
                    else:
                        debug_print("Maximum retries reached for billing page navigation")
                        raise
            
            # Wait for billing page to load
            debug_print("Waiting for billing page to load")
            page.wait_for_load_state('networkidle', timeout=60000)
            
            # Take screenshot of billing page
            page.screenshot(path="billing_page.png")
            debug_print(f"Current URL after billing page navigation: {page.url}")
            
            # Check if we need to log in to the platform
            if "login" in page.url:
                debug_print("Need to login to the platform")
                # Handle platform login if needed - this might be different from chat login
                try:
                    # Since we're redirected to login, let's try the login process again
                    email_selector = page.query_selector('input[type="email"]')
                    if email_selector:
                        debug_print("Found platform email field")
                        page.fill('input[type="email"]', openai_email)
                        page.click('button[type="submit"]')
                        
                        debug_print("Waiting for password field")
                        page.wait_for_selector('input[type="password"]', timeout=30000)
                        page.fill('input[type="password"]', openai_password)
                        page.click('button[type="submit"]')
                        
                        # Wait for login to complete
                        debug_print("Waiting for platform login to complete")
                        page.wait_for_url('https://platform.openai.com/**', timeout=60000)
                        
                        # Navigate to billing page again
                        debug_print("Navigating to billing page after platform login")
                        page.goto('https://platform.openai.com/account/billing/payment-history', wait_until="networkidle", timeout=60000)
                    else:
                        debug_print("Could not find platform email field")
                        page.screenshot(path="platform_login_error.png")
                except Exception as e:
                    debug_print(f"Error during platform login: {e}")
                    page.screenshot(path="platform_login_exception.png")
                    raise
            
            # Take updated screenshot of billing page
            page.screenshot(path="billing_page_final.png")
            
            # Look for the most recent invoice
            debug_print("Looking for invoice link")
            invoice_link = page.query_selector('a[href*="invoice"]')
            
            if not invoice_link:
                debug_print("No invoice link found on page, trying alternative approach")
                # Try to find any link that might contain an invoice
                all_links = page.query_selector_all('a')
                debug_print(f"Found {len(all_links)} links on the page")
                
                for link in all_links:
                    href = link.get_attribute('href')
                    text = link.inner_text()
                    if href and ('invoice' in href.lower() or 'pdf' in href.lower() or 'download' in text.lower()):
                        debug_print(f"Potential invoice link found: {href} with text: {text}")
                        invoice_link = link
                        break
            
            if not invoice_link:
                debug_print("No invoice link found after checking all links")
                # Print page content for debugging
                content = page.content()
                debug_print(f"Page content length: {len(content)}")
                debug_print(f"Page content preview: {content[:1000]}...")
                
                # Get page title
                title = page.title()
                debug_print(f"Page title: {title}")
                
                browser.close()
                return None
            
            # Get the href attribute
            invoice_url = invoice_link.get_attribute('href')
            debug_print(f"Found invoice URL: {invoice_url}")
            
            # If the URL is relative, make it absolute
            if invoice_url.startswith('/'):
                base_url = 'https://platform.openai.com'
                invoice_url = base_url + invoice_url
                debug_print(f"Converted to absolute URL: {invoice_url}")
            
            # Download the invoice
            debug_print("Downloading invoice")
            try:
                # Try to download via Playwright first
                with page.expect_download() as download_info:
                    page.click(f'a[href="{invoice_url}"]')
                download = download_info.value
                path = download.path()
                debug_print(f"Invoice downloaded via Playwright to: {path}")
                browser.close()
                return path
            except Exception as e:
                debug_print(f"Playwright download failed: {e}, trying requests")
                # If that fails, use requests as fallback
                try:
                    # Use the browser's cookies for authorization
                    cookies = context.cookies()
                    cookie_string = '; '.join([f"{cookie['name']}={cookie['value']}" for cookie in cookies])
                    
                    headers = {
                        'Cookie': cookie_string,
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                    }
                    
                    response = requests.get(invoice_url, headers=headers)
                    
                    if response.status_code != 200:
                        debug_print(f"Failed to download invoice. Status code: {response.status_code}")
                        debug_print(f"Response content: {response.content[:500]}...")
                        browser.close()
                        return None
                        
                    # Create a temporary file to store the PDF
                    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.pdf')
                    temp_file.write(response.content)
                    temp_file_path = temp_file.name
                    temp_file.close()
                    
                    debug_print(f"Invoice saved to temporary file: {temp_file_path}")
                    browser.close()
                    return temp_file_path
                except Exception as download_error:
                    debug_print(f"Failed to download with requests too: {download_error}")
                    browser.close()
                    raise
                
        except Exception as e:
            debug_print(f"Error during browser automation: {e}")
            debug_print(traceback.format_exc())
            try:
                page.screenshot(path="error_screenshot.png")
                debug_print("Error screenshot saved")
            except:
                debug_print("Could not take error screenshot")
            browser.close()
            raise

def send_email_with_attachment(attachment_path):
    debug_print(f"Preparing to send email to {email_recipient}")
    
    # Create message
    msg = MIMEMultipart()
    msg['From'] = email_sender
    msg['To'] = email_recipient
    
    # Current date for invoice naming
    current_date = datetime.now().strftime("%Y-%m-%d")
    msg['Subject'] = f"ChatGPT Invoice - {current_date}"
    
    # Email body
    body = "Please find attached your ChatGPT invoice."
    msg.attach(MIMEText(body, 'plain'))
    
    # Attach the file
    debug_print(f"Attaching file: {attachment_path}")
    attachment = open(attachment_path, "rb")
    part = MIMEBase('application', 'octet-stream')
    part.set_payload(attachment.read())
    encoders.encode_base64(part)
    part.add_header('Content-Disposition', f"attachment; filename=ChatGPT_Invoice_{current_date}.pdf")
    msg.attach(part)
    attachment.close()
    
    # Connect to email server and send
    try:
        debug_print("Connecting to email server (smtp.gmail.com)")
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.set_debuglevel(1)  # Add detailed SMTP debugging
        
        debug_print("Starting TLS")
        server.starttls()
        
        debug_print(f"Logging in with email: {email_sender[:3]}...{email_sender[-3:] if len(email_sender) > 6 else email_sender}")
        server.login(email_sender, email_password)
        
        debug_print("Sending email")
        text = msg.as_string()
        server.sendmail(email_sender, email_recipient, text)
        
        debug_print("Closing connection")
        server.quit()
        debug_print("Email sent successfully")
        return True
    except Exception as e:
        debug_print(f"Failed to send email: {e}")
        debug_print(traceback.format_exc())
        return False

def main():
    debug_print("=======================================")
    debug_print("Starting invoice fetch process...")
    debug_print(f"Current time: {datetime.now().isoformat()}")
    
    # Validate environment variables
    if not all([openai_email, openai_password, email_recipient, email_sender, email_password]):
        missing = []
        if not openai_email: missing.append("OPENAI_EMAIL")
        if not openai_password: missing.append("OPENAI_PASSWORD")
        if not email_recipient: missing.append("EMAIL_RECIPIENT")
        if not email_sender: missing.append("EMAIL_SENDER")
        if not email_password: missing.append("EMAIL_PASSWORD")
        debug_print(f"Missing environment variables: {', '.join(missing)}")
        return
    
    try:
        invoice_path = login_and_get_invoice()
        if invoice_path:
            debug_print(f"Invoice downloaded to {invoice_path}")
            success = send_email_with_attachment(invoice_path)
            # Clean up
            os.unlink(invoice_path)
            debug_print(f"Temporary file removed: {invoice_path}")
            if success:
                debug_print("Process completed successfully")
            else:
                debug_print("Process completed but email sending failed")
        else:
            debug_print("No invoice available, process completed")
    except Exception as e:
        debug_print(f"Error in main process: {e}")
        debug_print(traceback.format_exc())

if __name__ == "__main__":
    main()
