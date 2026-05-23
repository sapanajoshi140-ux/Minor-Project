import html
import os
from dotenv import load_dotenv
from fastapi_mail import FastMail, MessageSchema, ConnectionConfig

load_dotenv()

conf = ConnectionConfig(
    MAIL_USERNAME=os.getenv("MAIL_USERNAME"),
    MAIL_PASSWORD=os.getenv("MAIL_PASSWORD"),
    MAIL_FROM=os.getenv("MAIL_FROM"),
    MAIL_SERVER=os.getenv("MAIL_SERVER"),
    # Falls back to 587 (STARTTLS) if MAIL_PORT is missing rather than
    # crashing with TypeError: int() argument must be a string, not 'NoneType'.
    MAIL_PORT=int(os.getenv("MAIL_PORT", 587)),
    MAIL_STARTTLS=True,
    MAIL_SSL_TLS=False,
    USE_CREDENTIALS=True,
)


def verify_email_html(name: str, link: str) -> str:
    # Escape both values to prevent HTML injection if either comes from
    # untrusted input (e.g. a Google display name or a crafted redirect URL).
    safe_name = html.escape(name)
    safe_link = html.escape(link)
    return f"""
    <html>
      <body style="font-family:Arial">
        <p>Hello {safe_name},</p>
        <p>Click below to verify your email:</p>
        <a href="{safe_link}"
           style="padding:10px 16px;
                  background:#2563eb;
                  color:white;
                  text-decoration:none;
                  border-radius:5px;">
           Verify Email
        </a>
        <p style="font-size:12px;color:#777;">
          This is an automated email. Please do not reply.
        </p>
      </body>
    </html>
    """


def reset_email_html(name: str, link: str) -> str:
    safe_name = html.escape(name)
    safe_link = html.escape(link)
    return f"""
    <html>
      <body style="font-family:Arial">
        <p>Hello {safe_name},</p>
        <p>Click below to reset your password:</p>
        <a href="{safe_link}"
           style="padding:10px 16px;
                  background:#dc2626;
                  color:white;
                  text-decoration:none;
                  border-radius:5px;">
           Reset Password
        </a>
        <p style="font-size:12px;color:#777;">
          This is an automated email. Please do not reply.
        </p>
      </body>
    </html>
    """


async def send_email(to: str, subject: str, html_body: str):
    message = MessageSchema(
        subject=subject,
        recipients=[to],
        body=html_body,
        subtype="html",
        headers={"Reply-To": "no-reply@localhost"},
    )
    fm = FastMail(conf)
    await fm.send_message(message)