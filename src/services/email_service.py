"""Email Service - SMTP Email Sender"""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv("config/.env")


class EmailService:
    """Simple SMTP Email Service for Mailtrap"""
    
    def __init__(self):
        """Initialize with SMTP credentials from .env"""
        self.sender_email = os.getenv("SENDER_EMAIL")
        self.smtp_username = os.getenv("SMTP_USERNAME")
        self.smtp_password = os.getenv("SMTP_PASSWORD")
        self.smtp_server = os.getenv("SMTP_SERVER")
        self.smtp_port = int(os.getenv("SMTP_PORT"))
        
        print(f"\n✓ Email Service Initialized")
        print(f"  From: {self.sender_email}")
        print(f"  Server: {self.smtp_server}:{self.smtp_port}\n")
    
    def send(self, recipient_email, subject, body):
        """
        Send a single email via Mailtrap
        
        Args:
            recipient_email: Email to send to
            subject: Email subject
            body: Email body (HTML)
        
        Returns:
            {"success": True/False, "message": "..."}
        """
        
        try:
            # Create email message
            message = MIMEMultipart()
            message["Subject"] = subject
            message["From"] = self.sender_email
            message["To"] = recipient_email
            
            # Add body as HTML
            message.attach(MIMEText(body, "html"))
            
            # Connect to Mailtrap
            print(f"📧 Sending to {recipient_email}...", end=" ")
            
            server = smtplib.SMTP(self.smtp_server, self.smtp_port)
            server.starttls()
            
            # Login with USERNAME (not email!) and PASSWORD
            server.login(self.smtp_username, self.smtp_password)
            
            # Send email
            server.sendmail(
                self.sender_email,
                recipient_email,
                message.as_string()
            )
            
            server.quit()
            
            print("✅\n")
            
            return {
                "success": True,
                "message": f"Email sent to {recipient_email}"
            }
        
        except smtplib.SMTPAuthenticationError as e:
            print("❌\n")
            return {
                "success": False,
                "message": f"Authentication failed - Check SMTP_USERNAME and SMTP_PASSWORD in .env"
            }
        
        except smtplib.SMTPException as e:
            print("❌\n")
            return {
                "success": False,
                "message": f"SMTP Error: {str(e)}"
            }
        
        except Exception as e:
            print("❌\n")
            return {
                "success": False,
                "message": f"Error: {str(e)}"
            }
    
    def send_batch(self, recipients):
        """
        Send emails to multiple recipients
        
        Args:
            recipients: List of dicts with keys:
                {
                    "email": "john@example.com",
                    "subject": "Welcome",
                    "body": "<html>...</html>"
                }
        
        Returns:
            {"sent": count, "failed": count, "details": [...]}
        """
        
        results = {
            "sent": 0,
            "failed": 0,
            "details": []
        }
        
        print(f"\n📤 Sending {len(recipients)} emails\n")
        
        for idx, recipient in enumerate(recipients, 1):
            print(f"[{idx}/{len(recipients)}] ", end="")
            
            result = self.send(
                recipient["email"],
                recipient["subject"],
                recipient["body"]
            )
            
            if result["success"]:
                results["sent"] += 1
            else:
                results["failed"] += 1
            
            results["details"].append({
                "email": recipient["email"],
                "status": "✅ Sent" if result["success"] else "❌ Failed",
                "subject": recipient["subject"]
            })
        
        print(f"\n📊 Summary: {results['sent']} sent, {results['failed']} failed\n")
        
        return results