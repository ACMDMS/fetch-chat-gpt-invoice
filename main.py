import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from playwright.sync_api import sync_playwright
import time
from datetime import datetime
import requests
import tempfile

# Get environment variables
openai_email = os.environ.get('OPENAI_EMAIL')
openai_password = os.environ.get('OPENAI_PASSWORD')
email_recipient = os.environ.get('EMAIL_RECIPIENT')
email_sender = os.environ.get('EMAIL_SENDER')
email_password = os.environ.get('EMAIL_PASSWORD')

def login_and_get_invoice():
    with sync_playwright() as p:
        # Launch browser
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        
        # Go to OpenAI login page
        page.goto('https://chat.openai.com/auth/login')
        
        # Wait for login page to load and click Log in button
        page.wait_for_selector('button:has-text("Log in")')
        page.click('button:has-text("Log in")')
        
        # Fill in email
        page.wait_for_selector('input[name="username"]')
        page.fill('input[name="username"]', openai_email)
        page.click('button:has-text("Continue")')
        
        # Fill in password
        page.wait_for_selector('input[name="password"]')
        page.fill('input[name="password"]', openai_password)
        page.click('button[type="submit"]')
        
        # Wait for login to complete
        page.wait_for_url('https://chat.openai.com/**')
        
        # Navigate to billing page
        page.goto('https://platform.openai.com/account/billing/payment-history')
        
        # Wait for billing page to load
        page.wait_for_load_state('networkidle')
        
        # Look for the most recent invoice
        invoice_link = page.query_selector('a[href*="invoice"]')
        
        if not invoice_link:
            print("No invoice found")
            browser.close()
            return None
        
        # Get the href attribute
        invoice_url = invoice_link.get_attribute('href')
        
        # Download the invoice
        response = requests.get(invoice_url)
        
        # Create a temporary file to store the PDF
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.pdf')
        temp_file.write(response.content)
        temp_file_path = temp_file.name
        temp_file.close()
        
        browser.close()
        return temp_file_path

def send_email_with_attachment(attachment_path):
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
    attachment = open(attachment_path, "rb")
    part = MIMEBase('application', 'octet-stream')
    part.set_payload(attachment.read())
    encoders.encode_base64(part)
    part.add_header('Content-Disposition', f"attachment; filename=ChatGPT_Invoice_{current_date}.pdf")
    msg.attach(part)
    attachment.close()
    
    # Connect to email server and send
    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(email_sender, email_password)
        text = msg.as_string()
        server.sendmail(email_sender, email_recipient, text)
        server.quit()
        print("Email sent successfully")
    except Exception as e:
        print(f"Failed to send email: {e}")

def main():
    print("Starting invoice fetch process...")
    try:
        invoice_path = login_and_get_invoice()
        if invoice_path:
            print(f"Invoice downloaded to {invoice_path}")
            send_email_with_attachment(invoice_path)
            # Clean up
            os.unlink(invoice_path)
        else:
            print("No invoice available")
    except Exception as e:
        print(f"Error in main process: {e}")

if __name__ == "__main__":
    main()
