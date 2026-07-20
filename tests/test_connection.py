"""Test Email Service Connection"""

import sys
import os

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

print("\n" + "="*50)
print("TESTING EMAIL SERVICE")
print("="*50)

# Test 1: Import
print("\n[1/4] Importing EmailService...", end=" ")
try:
    from src.services.email_service import EmailService
    print("✅")
except Exception as e:
    print(f"❌ {e}")
    sys.exit(1)

# Test 2: Initialize
print("[2/4] Initializing service...", end=" ")
try:
    service = EmailService()
    print("✅")
except Exception as e:
    print(f"❌ {e}")
    sys.exit(1)

# Test 3: Send test email
print("[3/4] Sending test email...", end=" ")
result = service.send(
    recipient_email="test@example.com",
    subject="Test Email from SMTP Service",
    body="<html><body><h1>Hello!</h1><p>This is a test email from the SMTP service.</p></body></html>"
)

if result["success"]:
    print("✅")
else:
    print(f"❌ {result['message']}")

# Test 4: Show result
print("[4/4] Displaying result...", end=" ")
print("✅")

print("\n" + "="*50)
print("TEST COMPLETE")
print("="*50)

if result["success"]:
    print("\n✅ SUCCESS!")
    print("   Email sent successfully!")
    print("   Check your Mailtrap Sandbox inbox to see the email")
else:
    print(f"\n❌ FAILED")
    print(f"   Error: {result['message']}")
    print("\n   Troubleshooting:")
    print("   1. Check SMTP_USERNAME in config/.env (should be numeric like 1234567)")
    print("   2. Check SMTP_PASSWORD in config/.env")
    print("   3. Make sure SMTP_SERVER=smtp.mailtrap.io")
    print("   4. Make sure SMTP_PORT=2525")

print()