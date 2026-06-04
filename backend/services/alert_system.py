"""
Alert System — sends email for unnotified WARNING/CRITICAL alerts.
Exposes process_pending_alerts() as a single-tick function for the scheduler.
"""
from datetime import datetime, timezone
from loguru import logger

from db.database import AsyncSessionLocal
from models.db_models import Alert, AlertLevel
from config.config_manager import get_config
from sqlalchemy import select


async def process_pending_alerts():
    """Single tick — find unnotified alerts and email them."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Alert).where(
                Alert.notified == False,
                Alert.level.in_([AlertLevel.CRITICAL, AlertLevel.WARNING]),
            ).order_by(Alert.created_at.asc()).limit(10)
        )
        alerts = result.scalars().all()
        for alert in alerts:
            sent = await _send_alert_email(db, alert)
            alert.notified = True
            if sent:
                logger.info(f"Alert emailed: [{alert.level.value}] {alert.category}")
        if alerts:
            await db.commit()


async def create_alert(category: str, message: str, level: AlertLevel = AlertLevel.WARNING):
    """Create an alert from anywhere in the codebase."""
    async with AsyncSessionLocal() as db:
        db.add(Alert(level=level, category=category, message=message))
        await db.commit()


async def _send_alert_email(db, alert: Alert) -> bool:
    try:
        import aiosmtplib
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText

        smtp_host = await get_config(db, "smtp_host") or ""
        smtp_port = int(await get_config(db, "smtp_port") or "587")
        smtp_user = await get_config(db, "smtp_user") or ""
        smtp_pass = await get_config(db, "smtp_password") or ""
        smtp_tls  = (await get_config(db, "smtp_use_tls") or "true") == "true"
        to_email  = await get_config(db, "email_address") or ""

        if not all([smtp_host, smtp_user, smtp_pass, to_email]):
            return False

        level_color = "#fc8181" if alert.level == AlertLevel.CRITICAL else "#f6ad55"
        time_str    = alert.created_at.strftime("%d %b %Y %H:%M UTC") if alert.created_at else "—"

        html = f"""<html><body style="background:#0a0e1a;color:#e2e8f0;font-family:Arial,sans-serif;padding:24px">
<div style="max-width:500px;margin:0 auto;background:#141c2e;border:1px solid {level_color}44;border-radius:10px;padding:20px">
  <div style="color:{level_color};font-size:12px;text-transform:uppercase;margin-bottom:8px">
    ⚠ AutoCrypto — {alert.level.value.upper()} Alert
  </div>
  <div style="font-size:16px;font-weight:600;margin-bottom:12px">{alert.category.upper()}</div>
  <div style="background:#0a0e1a;border-radius:8px;padding:14px;font-size:14px;line-height:1.6;color:#a0aec0">{alert.message}</div>
  <div style="margin-top:12px;font-size:12px;color:#4a5568">{time_str}</div>
</div></body></html>"""

        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"[AutoCrypto {alert.level.value.upper()}] {alert.category}: {alert.message[:60]}"
        msg["From"]    = smtp_user
        msg["To"]      = to_email
        msg.attach(MIMEText(html, "html"))

        await aiosmtplib.send(
            msg, hostname=smtp_host, port=smtp_port,
            username=smtp_user, password=smtp_pass,
            use_tls=smtp_tls, start_tls=not smtp_tls,
        )
        return True
    except Exception as e:
        logger.error(f"Alert email failed: {e}")
        return False
