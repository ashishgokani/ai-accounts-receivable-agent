"""
Quick SMTP Verification Script.

Tests sending a live test email through your configured Gmail SMTP settings.
Run this script to verify your Gmail App Password works before your viva demo!
"""

import sys
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from app.core.config import settings

def test_smtp_connection():
    print("=" * 60)
    print("AR AGENT - GMAIL SMTP VERIFICATION TEST")
    print("=" * 60)

    if not settings.smtp_user or not settings.smtp_password:
        print("\n❌ Error: SMTP_USER or SMTP_PASSWORD is not set in backend/.env!")
        print("Please open backend/.env and enter your Gmail address and 16-character App Password.")
        sys.exit(1)

    sender = settings.smtp_user
    recipient = settings.demo_override_email or settings.smtp_user

    print(f"\n1. Connecting to {settings.smtp_host}:{settings.smtp_port}...")
    print(f"2. Sender Account: {sender}")
    print(f"3. Recipient Inbox: {recipient}")

    msg = MIMEMultipart()
    msg["From"] = f"{settings.from_name} <{sender}>"
    msg["To"] = recipient
    msg["Subject"] = "ReceivIQ SMTP Connection Verified"
    
    body = (
        "Hello,\n\n"
        "Congratulations! Your Gmail SMTP configuration for the AI Accounts Receivable Management Agent is working perfectly.\n\n"
        "During your viva demonstration, all customer payment reminders, escalation notices, and payment receipts "
        "will be delivered live to this inbox in real-time.\n\n"
        "Best regards,\n"
        "AI Accounts Receivable Management System"
    )
    msg.attach(MIMEText(body, "plain"))

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
            server.starttls()
            print("4. Authenticating with Google App Password...")
            server.login(settings.smtp_user, settings.smtp_password)
            print("5. Dispatching test email...")
            server.send_message(msg)

        print("\n[SUCCESS] A real test email was dispatched to your inbox!")
        print(f"Please check: {recipient} (check Spam/Junk folder if not in primary inbox).")
        print("=" * 60)
    except Exception as exc:
        print(f"\n[ERROR] SMTP Authentication Failed: {exc}")
        print("\nTroubleshooting tips:")
        print("1. Did you use your normal Gmail password? Google requires an 'App Password', NOT your standard password.")
        print("2. Ensure 2-Step Verification is turned ON in your Google Account.")
        print("3. Ensure the 16-character app password has no extra spaces.")
        sys.exit(1)

if __name__ == "__main__":
    test_smtp_connection()
