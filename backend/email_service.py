import os
import re
import random
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Tuple

# Disposable and Fake Email Blacklist
DISPOSABLE_DOMAINS = {
    "tempmail.com", "10minutemail.com", "mailinator.com", "guerrillamail.com",
    "sharklasers.com", "yopmail.com", "trashmail.com", "dispostable.com",
    "getairmail.com", "crazymailing.com", "mytemp.email", "temp-mail.org",
    "fakeinbox.com", "throwawaymail.com", "nada.ltd", "mohmal.com",
    "generator.email", "fakemailgenerator.com", "emailondeck.com", "tempail.com",
    "tempmailaddress.com", "burnermail.io", "maildrop.cc", "dropmail.me",
    "inboxkitten.com", "minutemail.com", "fastmail.top", "armyspy.com",
    "cuvox.de", "dayrep.com", "einrot.com", "fleckens.hu", "gustr.com",
    "jourrapide.com", "rhyta.com", "superrito.com", "teleworm.us"
}

# Load .env file automatically from backend directory
ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(ENV_PATH):
    with open(ENV_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                os.environ[key.strip()] = val.strip()

import json
import urllib.request
import urllib.error

# SMTP & HTTP API Configuration (Can be customized via Environment Variables or .env)
SENDER_EMAIL = os.getenv("SMTP_EMAIL", "mcocnexusteam@gmail.com")
SENDER_NAME = "MCOC NEXUS Team"
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "").strip()  # Gmail 16-character App Password

# Note: API keys are always read fresh at call time via os.getenv() to support hot env var updates on Render

def has_live_smtp() -> bool:
    """Returns True if a real SMTP password or HTTP API key is configured."""
    return bool(os.getenv("RESEND_API_KEY") or os.getenv("BREVO_API_KEY") or (SMTP_PASSWORD and len(SMTP_PASSWORD) >= 6))

def is_valid_email(email: str) -> Tuple[bool, str]:
    """Validates email format and blocks disposable/fake email domains."""
    if not email or not isinstance(email, str):
        return False, "Email address is required."
    
    email_clean = email.strip().lower()
    
    # Standard email regex pattern
    pattern = r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$'
    if not re.match(pattern, email_clean):
        return False, "Invalid email address format."
        
    domain = email_clean.split('@')[-1]
    
    # Block fake/disposable email services
    if domain in DISPOSABLE_DOMAINS or any(domain.endswith("." + d) for d in DISPOSABLE_DOMAINS):
        return False, "Disposable or temporary fake emails are not allowed. Please use a permanent email."
        
    return True, "Valid"

def generate_otp() -> str:
    """Generates a secure 6-digit numeric OTP."""
    return f"{random.randint(100000, 999999)}"

def send_resend_email(to_email: str, subject: str, html_body: str) -> bool:
    """Sends an email using Resend REST API over HTTPS Port 443 (Render friendly)."""
    global LAST_EMAIL_ERROR
    api_key = os.getenv("RESEND_API_KEY", "").strip()
    if not api_key:
        return False
    from_email = os.getenv("RESEND_FROM_EMAIL", "MCOC NEXUS <onboarding@resend.dev>").strip()
    url = "https://api.resend.com/emails"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "User-Agent": "MCOCNexus/1.0"
    }
    payload = {
        "from": from_email,
        "to": [to_email] if isinstance(to_email, str) else to_email,
        "subject": subject,
        "html": html_body,
        "reply_to": "mcocnexusteam@gmail.com"
    }
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=15) as response:
            if response.status in (200, 201):
                resp_json = json.loads(response.read().decode("utf-8"))
                print(f"[SUCCESS via Resend API] Live email sent to {to_email} (ID: {resp_json.get('id')})")
                return True
    except urllib.error.HTTPError as e:
        err_content = e.read().decode("utf-8", errors="ignore")
        print(f"[ERROR] Resend API HTTP error {e.code}: {err_content}")
        LAST_EMAIL_ERROR = f"Resend API Error: {err_content}"
    except Exception as e:
        print(f"[ERROR] Resend API exception: {e}")
        LAST_EMAIL_ERROR = f"Resend Exception: {str(e)}"
    return False

def send_brevo_email(to_email: str, subject: str, html_body: str) -> bool:
    """Sends an email using Brevo REST API over HTTPS Port 443."""
    global LAST_EMAIL_ERROR
    api_key = os.getenv("BREVO_API_KEY", "").strip()
    if not api_key:
        return False
    from_email = os.getenv("BREVO_FROM_EMAIL", SENDER_EMAIL).strip()
    url = "https://api.brevo.com/v3/smtp/email"
    headers = {
        "api-key": api_key,
        "Content-Type": "application/json"
    }
    payload = {
        "sender": {"name": SENDER_NAME, "email": from_email},
        "to": [{"email": to_email}],
        "subject": subject,
        "htmlContent": html_body
    }
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=15) as response:
            if response.status in (200, 201):
                print(f"[SUCCESS via Brevo API] Live email sent to {to_email}")
                return True
    except urllib.error.HTTPError as e:
        err_content = e.read().decode("utf-8", errors="ignore")
        print(f"[ERROR] Brevo API HTTP error {e.code}: {err_content}")
        LAST_EMAIL_ERROR = f"Brevo API Error: {err_content}"
    except Exception as e:
        print(f"[ERROR] Brevo API exception: {e}")
        LAST_EMAIL_ERROR = f"Brevo Exception: {str(e)}"
    return False

def send_smtp_email(to_email: str, subject: str, html_body: str) -> bool:
    """
    Sends an HTML email.
    Attempts in order:
    1. Resend HTTP REST API (Port 443 - Recommended for Render)
    2. Brevo HTTP REST API (Port 443)
    3. Direct Gmail SMTP (Ports 465 SSL and 587 TLS - Recommended for local dev)
    """
    # 1. Resend API
    if os.getenv("RESEND_API_KEY"):
        if send_resend_email(to_email, subject, html_body):
            return True
        print("[WARN] Resend API failed, trying SMTP fallback...")

    # 2. Brevo API
    if os.getenv("BREVO_API_KEY"):
        if send_brevo_email(to_email, subject, html_body):
            return True
        print("[WARN] Brevo API failed, trying SMTP fallback...")

    # 3. SMTP (Local or Paid Server)
    if not SMTP_PASSWORD:
        print("\n" + "="*70)
        print(f"[EMAIL SERVICE (CONSOLE MODE) - SENDER: {SENDER_EMAIL}]")
        print(f"To: {to_email}")
        print(f"Subject: {subject}")
        print("Note: To send live emails on Render, set RESEND_API_KEY in Render Environment Variables.")
        print("="*70 + "\n")
        return True

    msg = MIMEMultipart("alternative")
    msg["From"] = f"{SENDER_NAME} <{SENDER_EMAIL}>"
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(html_body, "html"))

    # Attempt 1: Direct SSL on Port 465
    try:
        server = smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=4)
        server.login(SENDER_EMAIL, SMTP_PASSWORD)
        server.sendmail(SENDER_EMAIL, to_email, msg.as_string())
        server.quit()
        print(f"[SUCCESS via SSL 465] Live email sent to {to_email}")
        return True
    except Exception as e1:
        print(f"[WARN] SSL 465 failed ({e1}), attempting STARTTLS on 587...")

    # Attempt 2: STARTTLS on Port 587
    try:
        server = smtplib.SMTP("smtp.gmail.com", 587, timeout=4)
        server.starttls()
        server.login(SENDER_EMAIL, SMTP_PASSWORD)
        server.sendmail(SENDER_EMAIL, to_email, msg.as_string())
        server.quit()
        print(f"[SUCCESS via TLS 587] Live email sent to {to_email}")
        return True
    except Exception as e2:
        print(f"[ERROR] Both SSL 465 and TLS 587 failed: {e2}")
        return False

def send_otp_email(to_email: str, username: str, otp: str) -> bool:
    """Sends a branded 6-digit OTP verification email to the user."""
    subject = f"{otp} is your MCOC NEXUS Verification Code"
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #0b0b0e; color: #ffffff; margin: 0; padding: 20px; }}
            .container {{ max-width: 540px; margin: 0 auto; background-color: #141418; border: 1px solid #2b2b36; border-radius: 8px; overflow: hidden; }}
            .header {{ background-color: #09090b; padding: 24px; text-align: center; border-bottom: 2px solid #e1ff00; }}
            .header h1 {{ margin: 0; font-size: 26px; color: #ffffff; letter-spacing: 2px; }}
            .header span {{ color: #e1ff00; }}
            .content {{ padding: 30px 24px; text-align: center; }}
            .otp-box {{ background-color: #1a1a22; border: 1px dashed #e1ff00; border-radius: 6px; padding: 18px; margin: 24px auto; font-size: 32px; font-weight: 900; letter-spacing: 8px; color: #e1ff00; width: fit-content; min-width: 200px; }}
            .footer {{ background-color: #0d0d10; padding: 16px; text-align: center; font-size: 11px; color: #71717a; border-top: 1px solid #222228; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>MCOC<span>NEXUS</span></h1>
                <p style="margin: 4px 0 0; font-size: 11px; color: #a1a1aa; text-transform: uppercase; letter-spacing: 1.5px;">Apex Contest Database & Strategist Suite</p>
            </div>
            <div class="content">
                <h2 style="color: #ffffff; margin-top: 0; font-size: 20px;">Email Verification Code</h2>
                <p style="color: #d4d4d8; font-size: 14px; line-height: 1.6;">
                    Hello <strong style="color: #e1ff00;">{username}</strong>,<br>
                    Thank you for joining MCOC NEXUS. Use the verification code below to confirm your email and activate your Summoner account:
                </p>
                <div class="otp-box">{otp}</div>
                <p style="color: #a1a1aa; font-size: 12px; margin-bottom: 0;">
                    ⏳ This code is valid for <strong>10 minutes</strong>. Do not share this code with anyone.
                </p>
            </div>
            <div class="footer">
                Sent by <strong>mcocnexusteam@gmail.com</strong> • MCOC NEXUS Official Team<br>
                If you did not request this code, please safely ignore this email.
            </div>
        </div>
    </body>
    </html>
    """
    return send_smtp_email(to_email, subject, html_content)

def send_welcome_email(to_email: str, username: str) -> bool:
    """Sends a styled welcoming email from mcocnexusteam@gmail.com upon successful registration."""
    subject = "Welcome to MCOC NEXUS — Your Contest Companion!"
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #0b0b0e; color: #ffffff; margin: 0; padding: 20px; }}
            .container {{ max-width: 560px; margin: 0 auto; background-color: #141418; border: 1px solid #2b2b36; border-radius: 8px; overflow: hidden; }}
            .header {{ background-color: #09090b; padding: 28px 24px; text-align: center; border-bottom: 2px solid #e1ff00; }}
            .header h1 {{ margin: 0; font-size: 28px; color: #ffffff; letter-spacing: 2px; }}
            .header span {{ color: #e1ff00; }}
            .content {{ padding: 30px 26px; }}
            .feature-card {{ background-color: #1a1a22; border-left: 3px solid #e1ff00; padding: 14px 16px; margin: 12px 0; border-radius: 0 4px 4px 0; }}
            .feature-title {{ color: #ffffff; font-weight: bold; font-size: 14px; margin-bottom: 4px; }}
            .feature-desc {{ color: #a1a1aa; font-size: 12px; margin: 0; line-height: 1.5; }}
            .footer {{ background-color: #0d0d10; padding: 20px; text-align: center; font-size: 11px; color: #71717a; border-top: 1px solid #222228; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>MCOC<span>NEXUS</span></h1>
                <p style="margin: 6px 0 0; font-size: 12px; color: #e1ff00; text-transform: uppercase; font-weight: bold; letter-spacing: 2px;">★ WELCOME TO THE CONTEST ★</p>
            </div>
            <div class="content">
                <h2 style="color: #ffffff; margin-top: 0; font-size: 20px;">Welcome aboard, Summoner {username}! 🛡️</h2>
                <p style="color: #d4d4d8; font-size: 14px; line-height: 1.6;">
                    Your account has been successfully verified and created. You now have full access to our comprehensive Marvel Contest of Champions tools and coach strategist workflows:
                </p>

                <div class="feature-card">
                    <div class="feature-title">📋 Personal Owned Roster</div>
                    <p class="feature-desc">Add your owned 7★, 6★ & 5★ champions, track awakened statuses, signature levels, and personal combat notes.</p>
                </div>

                <div class="feature-card">
                    <div class="feature-title">🎯 Customized Rankup Cart</div>
                    <p class="feature-desc">Receive customized rankup priorities and catalyst cost calculations (T6B, T3A, T5CC, Gold) tailored for your account by coach admin.</p>
                </div>

                <div class="feature-card">
                    <div class="feature-title">🛡️ Story & War Node Solver</div>
                    <p class="feature-desc">Instantly calculate the best counter champions across 43+ immunity types for difficult Act 8 story and Alliance War nodes.</p>
                </div>

                <div class="feature-card">
                    <div class="feature-title">🏆 Meta Tier Lists & Duel Targets</div>
                    <p class="feature-desc">Stay ahead of the Battlegrounds meta and practice fights against meta defenders using live duel codes.</p>
                </div>

                <p style="color: #d4d4d8; font-size: 13px; margin-top: 24px; line-height: 1.6;">
                    If you have questions or need alliance advice, reach out anytime to <strong style="color: #e1ff00;">mcocnexusteam@gmail.com</strong>.
                </p>
            </div>
            <div class="footer">
                © 2026 MCOC NEXUS Team • <a href="mailto:mcocnexusteam@gmail.com" style="color: #e1ff00; text-decoration: none;">mcocnexusteam@gmail.com</a><br>
                Be Strategic. Be Unstoppable.
            </div>
        </div>
    </body>
    </html>
    """
    return send_smtp_email(to_email, subject, html_content)

def validate_password_rules(password: str) -> Tuple[bool, str]:
    """
    Enforces strict password rules:
    1. Minimum 6 characters
    2. At least 1 Uppercase letter (A-Z)
    3. At least 1 Lowercase letter (a-z)
    4. At least 1 Numeric digit (0-9)
    5. At least 1 Special character (#, @, $, !, %, &, etc.)
    6. No sequential patterns like '123', 'abc', 'cba', '321', or repeated 'aaa', '111'.
    """
    if not password or len(password) < 6:
        return False, "Password must be at least 6 characters long."
        
    if not re.search(r'[A-Z]', password):
        return False, "Password must contain at least 1 uppercase letter (A-Z)."
        
    if not re.search(r'[a-z]', password):
        return False, "Password must contain at least 1 lowercase letter (a-z)."
        
    if not re.search(r'[0-9]', password):
        return False, "Password must contain at least 1 numeric digit (0-9)."
        
    if not re.search(r'[!@#$%^&*()_+\-=\[\]{};\':"\\|,.<>\/?~`]', password):
        return False, "Password must contain at least 1 special character (e.g. #, @, $, !, %, &)."
        
    # Check for 3+ consecutive sequential numeric patterns (e.g. 123, 234, 321, 987)
    lower_pw = password.lower()
    for i in range(len(lower_pw) - 2):
        chunk = lower_pw[i:i+3]
        if chunk.isdigit():
            d1, d2, d3 = int(chunk[0]), int(chunk[1]), int(chunk[2])
            if (d2 == d1 + 1 and d3 == d2 + 1) or (d2 == d1 - 1 and d3 == d2 - 1):
                return False, f"Password cannot contain sequential number patterns like '{chunk}'."
        # Check for 3+ consecutive sequential alphabetical patterns (e.g. abc, bcd, cba)
        if chunk.isalpha():
            c1, c2, c3 = ord(chunk[0]), ord(chunk[1]), ord(chunk[2])
            if (c2 == c1 + 1 and c3 == c2 + 1) or (c2 == c1 - 1 and c3 == c2 - 1):
                return False, f"Password cannot contain sequential letter patterns like '{chunk}'."
        # Check for 3+ identical repeated characters (e.g. aaa, 111, ###)
        if chunk[0] == chunk[1] == chunk[2]:
            return False, f"Password cannot contain repeated character sequences like '{chunk}'."
            
    # Check common predictable words
    common_words = ["password", "admin", "mcoc", "nexus", "contest", "qwerty"]
    for w in common_words:
        if w in lower_pw:
            return False, f"Password cannot contain common words like '{w}'."
            
    return True, "Valid"

def send_password_reset_otp_email(to_email: str, username: str, otp: str) -> bool:
    """Sends a branded 6-digit OTP verification email for password reset."""
    subject = f"{otp} is your MCOC NEXUS Password Reset Code"
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #0b0b0e; color: #ffffff; margin: 0; padding: 20px; }}
            .container {{ max-width: 540px; margin: 0 auto; background-color: #141418; border: 1px solid #2b2b36; border-radius: 8px; overflow: hidden; }}
            .header {{ background-color: #09090b; padding: 24px; text-align: center; border-bottom: 2px solid #e1ff00; }}
            .header h1 {{ margin: 0; font-size: 26px; color: #ffffff; letter-spacing: 2px; }}
            .header span {{ color: #e1ff00; }}
            .content {{ padding: 30px 24px; text-align: center; }}
            .otp-box {{ background-color: #1a1a22; border: 1px dashed #e1ff00; border-radius: 6px; padding: 18px; margin: 24px auto; font-size: 32px; font-weight: 900; letter-spacing: 8px; color: #e1ff00; width: fit-content; min-width: 200px; }}
            .footer {{ background-color: #0d0d10; padding: 16px; text-align: center; font-size: 11px; color: #71717a; border-top: 1px solid #222228; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>MCOC<span>NEXUS</span></h1>
                <p style="margin: 4px 0 0; font-size: 11px; color: #a1a1aa; text-transform: uppercase; letter-spacing: 1.5px;">Apex Contest Database & Security</p>
            </div>
            <div class="content">
                <h2 style="color: #ffffff; margin-top: 0; font-size: 20px;">Password Reset Verification</h2>
                <p style="color: #d4d4d8; font-size: 14px; line-height: 1.6;">
                    Hello <strong style="color: #e1ff00;">{username}</strong>,<br>
                    We received a request to change the password for your MCOC NEXUS account. Enter the 6-digit verification code below to authorize this password change:
                </p>
                <div class="otp-box">{otp}</div>
                <p style="color: #a1a1aa; font-size: 12px; margin-bottom: 0;">
                    ⏳ This code is valid for <strong>10 minutes</strong>. If you did not request a password reset, please ignore this email and your password will remain unchanged.
                </p>
            </div>
            <div class="footer">
                Sent by <strong>mcocnexusteam@gmail.com</strong> • MCOC NEXUS Security Team<br>
                Security notice: Never share your OTP code with anyone.
            </div>
        </div>
    </body>
    </html>
    """
    return send_smtp_email(to_email, subject, html_content)

def send_password_changed_email(to_email: str, username: str) -> bool:
    """Sends a security alert confirming password has been updated successfully."""
    subject = "Security Alert — Your MCOC NEXUS Password Was Changed"
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #0b0b0e; color: #ffffff; margin: 0; padding: 20px; }}
            .container {{ max-width: 540px; margin: 0 auto; background-color: #141418; border: 1px solid #2b2b36; border-radius: 8px; overflow: hidden; }}
            .header {{ background-color: #09090b; padding: 24px; text-align: center; border-bottom: 2px solid #22c55e; }}
            .header h1 {{ margin: 0; font-size: 26px; color: #ffffff; letter-spacing: 2px; }}
            .header span {{ color: #e1ff00; }}
            .content {{ padding: 30px 24px; text-align: center; }}
            .badge {{ background-color: #14532d; color: #86efac; border: 1px solid #22c55e; border-radius: 4px; padding: 8px 16px; display: inline-block; font-weight: bold; font-size: 13px; margin: 16px 0; }}
            .footer {{ background-color: #0d0d10; padding: 16px; text-align: center; font-size: 11px; color: #71717a; border-top: 1px solid #222228; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>MCOC<span>NEXUS</span></h1>
                <p style="margin: 4px 0 0; font-size: 11px; color: #22c55e; text-transform: uppercase; letter-spacing: 1.5px;">✓ SECURITY ALERT</p>
            </div>
            <div class="content">
                <h2 style="color: #ffffff; margin-top: 0; font-size: 20px;">Password Changed Successfully</h2>
                <div class="badge">✓ PASSWORD UPDATED</div>
                <p style="color: #d4d4d8; font-size: 14px; line-height: 1.6;">
                    Hello <strong style="color: #e1ff00;">{username}</strong>,<br>
                    The password for your MCOC NEXUS account (<strong>{to_email}</strong>) was just changed successfully. You can now sign in with your new password.
                </p>
                <p style="color: #a1a1aa; font-size: 12px; margin-top: 20px;">
                    If you did not make this change, please immediately contact our team at <strong style="color: #e1ff00;">mcocnexusteam@gmail.com</strong>.
                </p>
            </div>
            <div class="footer">
                Sent by <strong>mcocnexusteam@gmail.com</strong> • MCOC NEXUS Team
            </div>
        </div>
    </body>
    </html>
    """
    return send_smtp_email(to_email, subject, html_content)
