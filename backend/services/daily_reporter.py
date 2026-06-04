"""
Daily Reporter
Sends a daily email summary at 8 PM IST (14:30 UTC).
Includes: starting fund, trades today, P&L, total fund, locked amount.
"""
import json
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from loguru import logger

from db.database import AsyncSessionLocal
from models.db_models import Trade, TradeStatus, DailyReport, Alert, AlertLevel, FundSnapshot
from config.config_manager import get_config
from sqlalchemy import select, func


async def send_daily_report():
    """Build and send the daily report email."""
    async with AsyncSessionLocal() as db:
        try:
            data = await _build_report_data(db)
            html = _render_email(data)
            sent = await _send_email(
                db      = db,
                subject = f"AutoCrypto Daily Report — {data['date']} | P&L: ₹{data['pnl_day']:+,.2f}",
                html    = html,
            )
            # Save report record
            report = DailyReport(
                report_date   = datetime.now(timezone.utc),
                starting_fund = Decimal(str(data["starting_fund"])),
                ending_fund   = Decimal(str(data["ending_fund"])),
                locked_fund   = Decimal(str(data["locked"])),
                trades_count  = data["trades_total"],
                winning_trades= data["trades_won"],
                losing_trades = data["trades_lost"],
                pnl_day       = Decimal(str(data["pnl_day"])),
                pnl_total     = Decimal(str(data["pnl_total"])),
                email_sent    = sent,
                report_json   = json.dumps(data),
            )
            db.add(report)
            await db.commit()
            logger.info(f"Daily report sent={sent} | pnl={data['pnl_day']:+.2f}")

        except Exception as e:
            logger.error(f"Daily report failed: {e}", exc_info=True)


async def _build_report_data(db) -> dict:
    """Collect all data needed for the report."""
    today_start = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    # Today's closed trades
    result = await db.execute(
        select(Trade)
        .where(Trade.status == TradeStatus.CLOSED)
        .where(Trade.closed_at >= today_start)
    )
    trades = result.scalars().all()

    trades_won  = [t for t in trades if t.pnl and float(t.pnl) > 0]
    trades_lost = [t for t in trades if t.pnl and float(t.pnl) <= 0]
    pnl_day     = sum(float(t.pnl or 0) for t in trades)

    # Fund state
    snap_result = await db.execute(
        select(FundSnapshot).order_by(FundSnapshot.snapshot_at.desc()).limit(1)
    )
    snap = snap_result.scalar_one_or_none()

    starting_capital = float(await get_config(db, "starting_capital") or "0")
    ending_fund      = float(snap.total_balance) if snap else starting_capital
    locked           = float(snap.locked_25pct) if snap else 0.0
    pnl_total        = ending_fund + locked - starting_capital

    # Day start fund from first snapshot today
    day_snap_result = await db.execute(
        select(FundSnapshot)
        .where(FundSnapshot.snapshot_at >= today_start)
        .order_by(FundSnapshot.snapshot_at.asc())
        .limit(1)
    )
    day_snap     = day_snap_result.scalar_one_or_none()
    starting_fund = float(day_snap.total_balance) if day_snap else starting_capital

    # Build trade rows
    trade_rows = []
    for t in sorted(trades, key=lambda x: x.closed_at or datetime.min):
        trade_rows.append({
            "pair":      t.pair,
            "direction": str(t.direction.value).upper(),
            "entry":     float(t.entry_price or 0),
            "exit":      float(t.exit_price or 0),
            "pnl":       float(t.pnl or 0),
            "pnl_pct":   float(t.pnl_pct or 0),
            "time":      t.closed_at.strftime("%H:%M") if t.closed_at else "—",
        })

    return {
        "date":          datetime.now(timezone.utc).strftime("%d %b %Y"),
        "starting_fund": round(starting_fund, 2),
        "ending_fund":   round(ending_fund, 2),
        "locked":        round(locked, 2),
        "available":     round(ending_fund - locked, 2),
        "pnl_day":       round(pnl_day, 2),
        "pnl_total":     round(pnl_total, 2),
        "pnl_total_pct": round((pnl_total / starting_capital * 100) if starting_capital else 0, 2),
        "trades_total":  len(trades),
        "trades_won":    len(trades_won),
        "trades_lost":   len(trades_lost),
        "win_rate":      round(len(trades_won) / len(trades) * 100 if trades else 0, 1),
        "trade_rows":    trade_rows,
    }


def _render_email(d: dict) -> str:
    """Render HTML email from data dict."""
    pnl_color   = "#48bb78" if d["pnl_day"] >= 0 else "#fc8181"
    pnl_sign    = "+" if d["pnl_day"] >= 0 else ""
    trade_rows  = ""

    for t in d["trade_rows"]:
        color = "#48bb78" if t["pnl"] >= 0 else "#fc8181"
        sign  = "+" if t["pnl"] >= 0 else ""
        trade_rows += f"""
        <tr>
          <td style="padding:8px 12px;border-bottom:1px solid #1a2235">{t['pair']}</td>
          <td style="padding:8px 12px;border-bottom:1px solid #1a2235;color:{'#48bb78' if t['direction']=='BUY' else '#fc8181'}">{t['direction']}</td>
          <td style="padding:8px 12px;border-bottom:1px solid #1a2235;font-family:monospace">₹{t['entry']:,.2f}</td>
          <td style="padding:8px 12px;border-bottom:1px solid #1a2235;font-family:monospace">₹{t['exit']:,.2f}</td>
          <td style="padding:8px 12px;border-bottom:1px solid #1a2235;color:{color};font-weight:600">{sign}₹{t['pnl']:,.2f}</td>
          <td style="padding:8px 12px;border-bottom:1px solid #1a2235;color:{color}">{sign}{t['pnl_pct']:.2f}%</td>
          <td style="padding:8px 12px;border-bottom:1px solid #1a2235;color:#718096">{t['time']}</td>
        </tr>"""

    if not trade_rows:
        trade_rows = '<tr><td colspan="7" style="padding:16px;text-align:center;color:#718096">No trades today</td></tr>'

    return f"""
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#0a0e1a;font-family:'Segoe UI',Arial,sans-serif;color:#e2e8f0">
<div style="max-width:600px;margin:0 auto;padding:24px">

  <!-- Header -->
  <div style="background:linear-gradient(135deg,#1a2235,#141c2e);border:1px solid rgba(255,255,255,0.08);border-radius:12px;padding:24px;margin-bottom:16px">
    <div style="display:flex;align-items:center;gap:12px;margin-bottom:4px">
      <div style="background:linear-gradient(135deg,#63b3ed,#48bb78);border-radius:8px;width:36px;height:36px;display:flex;align-items:center;justify-content:center;font-weight:700;color:#0a0e1a;font-size:14px">AC</div>
      <span style="font-family:monospace;color:#63b3ed;letter-spacing:0.05em">AutoCrypto Trader</span>
    </div>
    <h1 style="margin:12px 0 4px;font-size:20px">Daily Report — {d['date']}</h1>
    <div style="color:#718096;font-size:14px">Automated summary of today's trading activity</div>
  </div>

  <!-- Stats -->
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:16px">
    <div style="background:#141c2e;border:1px solid rgba(255,255,255,0.08);border-radius:10px;padding:16px">
      <div style="font-size:11px;text-transform:uppercase;letter-spacing:0.06em;color:#718096;margin-bottom:6px">Today's P&L</div>
      <div style="font-size:24px;font-weight:700;font-family:monospace;color:{pnl_color}">{pnl_sign}₹{d['pnl_day']:,.2f}</div>
    </div>
    <div style="background:#141c2e;border:1px solid rgba(255,255,255,0.08);border-radius:10px;padding:16px">
      <div style="font-size:11px;text-transform:uppercase;letter-spacing:0.06em;color:#718096;margin-bottom:6px">Total Fund</div>
      <div style="font-size:24px;font-weight:700;font-family:monospace;color:#63b3ed">₹{d['ending_fund']:,.2f}</div>
    </div>
    <div style="background:#141c2e;border:1px solid rgba(255,255,255,0.08);border-radius:10px;padding:16px">
      <div style="font-size:11px;text-transform:uppercase;letter-spacing:0.06em;color:#718096;margin-bottom:6px">Locked (Protected)</div>
      <div style="font-size:24px;font-weight:700;font-family:monospace;color:#48bb78">₹{d['locked']:,.2f}</div>
    </div>
    <div style="background:#141c2e;border:1px solid rgba(255,255,255,0.08);border-radius:10px;padding:16px">
      <div style="font-size:11px;text-transform:uppercase;letter-spacing:0.06em;color:#718096;margin-bottom:6px">Win Rate</div>
      <div style="font-size:24px;font-weight:700;font-family:monospace;color:#f6ad55">{d['win_rate']}%</div>
      <div style="font-size:12px;color:#718096;margin-top:4px">{d['trades_won']}W / {d['trades_lost']}L of {d['trades_total']} trades</div>
    </div>
  </div>

  <!-- Summary row -->
  <div style="background:#141c2e;border:1px solid rgba(255,255,255,0.08);border-radius:10px;padding:16px;margin-bottom:16px;font-size:14px">
    <div style="display:flex;justify-content:space-between;margin-bottom:8px">
      <span style="color:#718096">Day started with</span>
      <span style="font-family:monospace">₹{d['starting_fund']:,.2f}</span>
    </div>
    <div style="display:flex;justify-content:space-between;margin-bottom:8px">
      <span style="color:#718096">Available to trade</span>
      <span style="font-family:monospace">₹{d['available']:,.2f}</span>
    </div>
    <div style="display:flex;justify-content:space-between;border-top:1px solid rgba(255,255,255,0.06);padding-top:8px">
      <span style="color:#718096">All-time P&L</span>
      <span style="font-family:monospace;color:{'#48bb78' if d['pnl_total']>=0 else '#fc8181'};font-weight:600">
        {'+'if d['pnl_total']>=0 else ''}₹{d['pnl_total']:,.2f} ({d['pnl_total_pct']:+.2f}%)
      </span>
    </div>
  </div>

  <!-- Trades table -->
  <div style="background:#141c2e;border:1px solid rgba(255,255,255,0.08);border-radius:10px;overflow:hidden;margin-bottom:16px">
    <div style="padding:14px 16px;border-bottom:1px solid rgba(255,255,255,0.08);font-weight:500">Today's Trades</div>
    <table style="width:100%;border-collapse:collapse;font-size:13px">
      <thead>
        <tr style="background:rgba(255,255,255,0.03)">
          <th style="padding:8px 12px;text-align:left;color:#718096;font-weight:500;font-size:11px;text-transform:uppercase">Pair</th>
          <th style="padding:8px 12px;text-align:left;color:#718096;font-weight:500;font-size:11px;text-transform:uppercase">Dir</th>
          <th style="padding:8px 12px;text-align:left;color:#718096;font-weight:500;font-size:11px;text-transform:uppercase">Entry</th>
          <th style="padding:8px 12px;text-align:left;color:#718096;font-weight:500;font-size:11px;text-transform:uppercase">Exit</th>
          <th style="padding:8px 12px;text-align:left;color:#718096;font-weight:500;font-size:11px;text-transform:uppercase">P&L</th>
          <th style="padding:8px 12px;text-align:left;color:#718096;font-weight:500;font-size:11px;text-transform:uppercase">%</th>
          <th style="padding:8px 12px;text-align:left;color:#718096;font-weight:500;font-size:11px;text-transform:uppercase">Time</th>
        </tr>
      </thead>
      <tbody>{trade_rows}</tbody>
    </table>
  </div>

  <div style="text-align:center;color:#4a5568;font-size:12px">
    AutoCrypto Trader · This is an automated report · Do not reply
  </div>
</div>
</body>
</html>"""


async def _send_email(db, subject: str, html: str) -> bool:
    """Send email via SMTP. Returns True if sent successfully."""
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
            logger.warning("Email not configured — skipping report send")
            return False

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = smtp_user
        msg["To"]      = to_email
        msg.attach(MIMEText(html, "html"))

        await aiosmtplib.send(
            msg,
            hostname  = smtp_host,
            port      = smtp_port,
            username  = smtp_user,
            password  = smtp_pass,
            use_tls   = smtp_tls,
            start_tls = not smtp_tls,
        )
        logger.info(f"Daily report emailed to {to_email}")
        return True

    except Exception as e:
        logger.error(f"Email send failed: {e}")
        return False
