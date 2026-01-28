"""Email notification module for daily trade summaries."""

import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, Any, List
from datetime import date
from loguru import logger


class EmailNotifier:
    """Send email notifications for trade summaries via Gmail SMTP."""

    def __init__(self):
        """Initialize email notifier with SMTP credentials."""
        self.smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_user = os.getenv("SMTP_USER", "")
        self.smtp_password = os.getenv("SMTP_PASSWORD", "")
        self.from_email = os.getenv("EMAIL_FROM", "trading@samaanai.com")
        self.to_emails = [e.strip() for e in os.getenv("EMAIL_RECIPIENTS", "").split(",") if e.strip()]

        self.enabled = bool(self.smtp_user) and bool(self.smtp_password) and bool(self.to_emails)

        if not self.enabled:
            if not self.smtp_user:
                logger.warning("SMTP_USER not set.")
            elif not self.smtp_password:
                logger.warning("SMTP_PASSWORD not set.")
            elif not self.to_emails:
                logger.warning("EMAIL_RECIPIENTS not set.")
            logger.warning("Email notifications disabled.")

    def send_email(self, subject: str, html_content: str, text_content: str = None) -> bool:
        """Send an email via SMTP.

        Args:
            subject: Email subject
            html_content: HTML body content
            text_content: Plain text fallback (optional)

        Returns:
            True if sent successfully
        """
        if not self.enabled:
            logger.info(f"Email disabled - would send: {subject}")
            return False

        try:
            # Create message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = f"LLM Trading Agent <{self.from_email}>"
            msg['To'] = ", ".join(self.to_emails)

            # Attach text and HTML parts
            if text_content:
                msg.attach(MIMEText(text_content, 'plain'))
            msg.attach(MIMEText(html_content, 'html'))

            # Connect to SMTP server and send
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.sendmail(self.from_email, self.to_emails, msg.as_string())

            logger.info(f"Email sent successfully: {subject}")
            return True

        except Exception as e:
            logger.error(f"Error sending email: {e}")
            return False

    def send_daily_summary(
        self,
        portfolio: Dict[str, Any],
        trades_today: List[Dict[str, Any]],
        analysis_runs: int,
        risk_status: Dict[str, Any]
    ) -> bool:
        """Send daily trading summary email.

        Args:
            portfolio: Current portfolio data
            trades_today: List of trades executed today
            analysis_runs: Number of analysis runs today
            risk_status: Current risk status

        Returns:
            True if sent successfully
        """
        today = date.today().strftime("%B %d, %Y")
        portfolio_value = portfolio.get('portfolio_value', 0)
        cash = portfolio.get('cash', 0)
        daily_change = portfolio.get('daily_change', 0)
        daily_change_pct = portfolio.get('daily_change_pct', 0)
        positions = portfolio.get('positions', [])

        change_color = "#28a745" if daily_change >= 0 else "#dc3545"
        change_icon = "+" if daily_change >= 0 else ""

        # Build trades table
        trades_html = ""
        if trades_today:
            trades_rows = ""
            for trade in trades_today:
                action_color = "#28a745" if trade.get('action') == 'BUY' else "#dc3545"
                trades_rows += f"""
                <tr>
                    <td style="padding: 8px; border-bottom: 1px solid #eee;">{trade.get('created_at', '--')}</td>
                    <td style="padding: 8px; border-bottom: 1px solid #eee; color: {action_color}; font-weight: bold;">{trade.get('action', '--')}</td>
                    <td style="padding: 8px; border-bottom: 1px solid #eee; font-weight: bold;">{trade.get('symbol', '--')}</td>
                    <td style="padding: 8px; border-bottom: 1px solid #eee;">{trade.get('quantity', 0)}</td>
                    <td style="padding: 8px; border-bottom: 1px solid #eee;">${trade.get('filled_price', 0):,.2f}</td>
                    <td style="padding: 8px; border-bottom: 1px solid #eee;">{trade.get('confidence', 0)*100:.0f}%</td>
                </tr>
                """
            trades_html = f"""
            <h2 style="color: #333; margin-top: 30px;">Trades Executed Today ({len(trades_today)})</h2>
            <table style="width: 100%; border-collapse: collapse; margin-top: 10px;">
                <thead>
                    <tr style="background-color: #f8f9fa;">
                        <th style="padding: 10px; text-align: left; border-bottom: 2px solid #dee2e6;">Time</th>
                        <th style="padding: 10px; text-align: left; border-bottom: 2px solid #dee2e6;">Action</th>
                        <th style="padding: 10px; text-align: left; border-bottom: 2px solid #dee2e6;">Symbol</th>
                        <th style="padding: 10px; text-align: left; border-bottom: 2px solid #dee2e6;">Qty</th>
                        <th style="padding: 10px; text-align: left; border-bottom: 2px solid #dee2e6;">Price</th>
                        <th style="padding: 10px; text-align: left; border-bottom: 2px solid #dee2e6;">Confidence</th>
                    </tr>
                </thead>
                <tbody>
                    {trades_rows}
                </tbody>
            </table>
            """
        else:
            trades_html = """
            <h2 style="color: #333; margin-top: 30px;">Trades Executed Today</h2>
            <p style="color: #666;">No trades were executed today. The agent analyzed the market but did not find opportunities meeting confidence thresholds.</p>
            """

        # Build positions table
        positions_html = ""
        if positions:
            positions_rows = ""
            for pos in positions:
                pl_color = "#28a745" if pos.get('unrealized_pl', 0) >= 0 else "#dc3545"
                positions_rows += f"""
                <tr>
                    <td style="padding: 8px; border-bottom: 1px solid #eee; font-weight: bold;">{pos.get('symbol', '--')}</td>
                    <td style="padding: 8px; border-bottom: 1px solid #eee;">{pos.get('qty', 0)}</td>
                    <td style="padding: 8px; border-bottom: 1px solid #eee;">${pos.get('avg_entry_price', 0):,.2f}</td>
                    <td style="padding: 8px; border-bottom: 1px solid #eee;">${pos.get('current_price', 0):,.2f}</td>
                    <td style="padding: 8px; border-bottom: 1px solid #eee;">${pos.get('market_value', 0):,.2f}</td>
                    <td style="padding: 8px; border-bottom: 1px solid #eee; color: {pl_color};">${pos.get('unrealized_pl', 0):+,.2f}</td>
                </tr>
                """
            positions_html = f"""
            <h2 style="color: #333; margin-top: 30px;">Current Positions ({len(positions)})</h2>
            <table style="width: 100%; border-collapse: collapse; margin-top: 10px;">
                <thead>
                    <tr style="background-color: #f8f9fa;">
                        <th style="padding: 10px; text-align: left; border-bottom: 2px solid #dee2e6;">Symbol</th>
                        <th style="padding: 10px; text-align: left; border-bottom: 2px solid #dee2e6;">Qty</th>
                        <th style="padding: 10px; text-align: left; border-bottom: 2px solid #dee2e6;">Avg Cost</th>
                        <th style="padding: 10px; text-align: left; border-bottom: 2px solid #dee2e6;">Current</th>
                        <th style="padding: 10px; text-align: left; border-bottom: 2px solid #dee2e6;">Value</th>
                        <th style="padding: 10px; text-align: left; border-bottom: 2px solid #dee2e6;">P&L</th>
                    </tr>
                </thead>
                <tbody>
                    {positions_rows}
                </tbody>
            </table>
            """
        else:
            positions_html = """
            <h2 style="color: #333; margin-top: 30px;">Current Positions</h2>
            <p style="color: #666;">No open positions. Portfolio is 100% cash.</p>
            """

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #333; max-width: 800px; margin: 0 auto; padding: 20px;">
            <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; border-radius: 10px 10px 0 0;">
                <h1 style="margin: 0; font-size: 24px;">Daily Trading Summary</h1>
                <p style="margin: 5px 0 0 0; opacity: 0.9;">{today}</p>
            </div>

            <div style="background: #fff; padding: 30px; border: 1px solid #e9ecef; border-top: none; border-radius: 0 0 10px 10px;">
                <!-- Portfolio Overview -->
                <div style="display: flex; flex-wrap: wrap; gap: 20px; margin-bottom: 30px;">
                    <div style="flex: 1; min-width: 150px; background: #f8f9fa; padding: 20px; border-radius: 8px; text-align: center;">
                        <p style="margin: 0; color: #666; font-size: 14px;">Portfolio Value</p>
                        <p style="margin: 5px 0 0 0; font-size: 28px; font-weight: bold; color: #333;">${portfolio_value:,.2f}</p>
                    </div>
                    <div style="flex: 1; min-width: 150px; background: #f8f9fa; padding: 20px; border-radius: 8px; text-align: center;">
                        <p style="margin: 0; color: #666; font-size: 14px;">Daily Change</p>
                        <p style="margin: 5px 0 0 0; font-size: 28px; font-weight: bold; color: {change_color};">{change_icon}${abs(daily_change):,.2f}</p>
                        <p style="margin: 0; color: {change_color}; font-size: 14px;">({change_icon}{daily_change_pct:.2f}%)</p>
                    </div>
                    <div style="flex: 1; min-width: 150px; background: #f8f9fa; padding: 20px; border-radius: 8px; text-align: center;">
                        <p style="margin: 0; color: #666; font-size: 14px;">Cash Available</p>
                        <p style="margin: 5px 0 0 0; font-size: 28px; font-weight: bold; color: #333;">${cash:,.2f}</p>
                    </div>
                </div>

                <!-- Agent Activity -->
                <div style="background: #e8f4fd; padding: 15px; border-radius: 8px; margin-bottom: 20px;">
                    <p style="margin: 0;"><strong>Agent Activity:</strong> {analysis_runs} market analysis runs today</p>
                    <p style="margin: 5px 0 0 0;"><strong>Risk Level:</strong> {risk_status.get('risk_level', 'LOW')}</p>
                </div>

                {trades_html}

                {positions_html}

                <!-- Footer -->
                <div style="margin-top: 40px; padding-top: 20px; border-top: 1px solid #eee; text-align: center; color: #666; font-size: 12px;">
                    <p>This is an automated summary from your LLM Trading Agent.</p>
                    <p>Dashboard: <a href="https://trading.samaanai.com" style="color: #667eea;">View Live Dashboard</a></p>
                </div>
            </div>
        </body>
        </html>
        """

        # Plain text version
        text_content = f"""
Daily Trading Summary - {today}

PORTFOLIO OVERVIEW
------------------
Portfolio Value: ${portfolio_value:,.2f}
Daily Change: {change_icon}${abs(daily_change):,.2f} ({change_icon}{daily_change_pct:.2f}%)
Cash Available: ${cash:,.2f}

AGENT ACTIVITY
--------------
Analysis Runs: {analysis_runs}
Risk Level: {risk_status.get('risk_level', 'LOW')}

TRADES TODAY: {len(trades_today)}
{"No trades executed." if not trades_today else chr(10).join([f"- {t.get('action')} {t.get('quantity')} {t.get('symbol')} @ ${t.get('filled_price', 0):,.2f}" for t in trades_today])}

POSITIONS: {len(positions)}
{"No open positions." if not positions else chr(10).join([f"- {p.get('symbol')}: {p.get('qty')} shares @ ${p.get('current_price', 0):,.2f}" for p in positions])}

---
View Dashboard: https://trading.samaanai.com
        """

        subject = f"Trading Summary: ${portfolio_value:,.0f} ({change_icon}{daily_change_pct:.1f}%) - {today}"

        return self.send_email(subject, html_content, text_content)


# Global notifier instance
email_notifier = EmailNotifier()


def send_daily_summary(portfolio: Dict, trades: List, analysis_runs: int, risk_status: Dict) -> bool:
    """Convenience function to send daily summary."""
    return email_notifier.send_daily_summary(portfolio, trades, analysis_runs, risk_status)
