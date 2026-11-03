"""SMTP delivery. Works with Gmail (app password) or Resend's SMTP relay.

Env vars (set as GitHub Actions secrets):
  SMTP_HOST      default smtp.gmail.com   (Resend: smtp.resend.com)
  SMTP_PORT      default 465 (implicit TLS)
  SMTP_USER      Gmail address            (Resend: "resend")
  SMTP_PASSWORD  Gmail app password       (Resend: API key)
  DIGEST_TO      recipient
  DIGEST_FROM    sender, defaults to SMTP_USER (Resend: an address on your verified domain)
"""
from __future__ import annotations

import os
import smtplib
import ssl
from email.message import EmailMessage

from .render import Digest


def build_message(d: Digest, sender: str, to: str) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = d.subject
    msg["From"] = sender
    msg["To"] = to
    msg.set_content(d.text)
    msg.add_alternative(d.html, subtype="html")
    return msg


def send(d: Digest) -> None:
    host = os.environ.get("SMTP_HOST") or "smtp.gmail.com"
    port = int(os.environ.get("SMTP_PORT") or "465")
    user = os.environ["SMTP_USER"]
    password = os.environ["SMTP_PASSWORD"]
    to = os.environ["DIGEST_TO"]
    sender = os.environ.get("DIGEST_FROM") or user
    msg = build_message(d, sender, to)
    ctx = ssl.create_default_context()
    if port == 465:
        with smtplib.SMTP_SSL(host, port, context=ctx, timeout=60) as s:
            s.login(user, password)
            s.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=60) as s:
            s.starttls(context=ctx)
            s.login(user, password)
            s.send_message(msg)
