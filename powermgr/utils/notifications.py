"""
Notification system for sending email alerts.
"""
import smtplib
import ssl
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Dict, Any, Optional
from datetime import datetime


class NotificationManager:
    """Manages email notifications for different severity levels."""
    
    def __init__(self, smtp_config: Dict[str, Any], recipients: Dict[str, List[str]]):
        """
        Initialize notification manager.
        
        Args:
            smtp_config: SMTP server configuration
            recipients: Dictionary mapping severity levels to recipient lists
        """
        self.smtp_server = smtp_config['server']
        self.smtp_port = smtp_config['port']
        self.smtp_username = smtp_config['username']
        self.smtp_password = smtp_config['password']
        self.recipients = recipients
        self.logger = logging.getLogger(self.__class__.__name__)
    
    def _send_email(self, to_addresses: List[str], subject: str, body: str, html_body: Optional[str] = None) -> bool:
        """
        Send email using SMTP.
        
        Args:
            to_addresses: List of recipient email addresses
            subject: Email subject
            body: Plain text body
            html_body: Optional HTML body
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Create message
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = self.smtp_username
            msg["To"] = ", ".join(to_addresses)
            
            # Add plain text part
            text_part = MIMEText(body, "plain")
            msg.attach(text_part)
            
            # Add HTML part if provided
            if html_body:
                html_part = MIMEText(html_body, "html")
                msg.attach(html_part)
            
            # Create secure connection and send
            context = ssl.create_default_context()
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls(context=context)
                server.login(self.smtp_username, self.smtp_password)
                server.send_message(msg)
            
            self.logger.info(f"Email sent successfully to {len(to_addresses)} recipients")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to send email: {str(e)}")
            return False
    
    def notify(self, level: str, message_type: str, details: Dict[str, Any] = None) -> bool:
        """
        Send notification based on severity level and message type.
        
        Args:
            level: Notification level ('info', 'warning', 'critical')
            message_type: Type of message for template selection
            details: Additional details to include in notification
            
        Returns:
            bool: True if notification sent successfully
        """
        if level not in self.recipients:
            self.logger.error(f"Unknown notification level: {level}")
            return False
        
        recipients = self.recipients[level]
        if not recipients:
            self.logger.warning(f"No recipients configured for level: {level}")
            return False
        
        # Generate message content
        subject, body, html_body = self._generate_message_content(level, message_type, details)
        
        return self._send_email(recipients, subject, body, html_body)
    
    def _generate_message_content(self, level: str, message_type: str, details: Dict[str, Any] = None) -> tuple:
        """
        Generate message content based on type and level.
        
        Args:
            level: Notification level
            message_type: Message type
            details: Additional details
            
        Returns:
            tuple: (subject, plain_text_body, html_body)
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        details = details or {}
        
        # Message templates
        templates = {
            'battery_adjusted': {
                'subject': f"[{level.upper()}] Power Manager: Battery Adjusted",
                'body': f"Battery level adjustment triggered at {timestamp}.\n\nDetails:\n"
            },
            'precool_activated': {
                'subject': f"[{level.upper()}] Power Manager: Precooling Activated",
                'body': f"Precooling activated at {timestamp}.\n\nDetails:\n"
            },
            'eod_battery_low': {
                'subject': f"[{level.upper()}] Power Manager: End of Day Battery Warning",
                'body': f"Battery level is below warning threshold at end of day ({timestamp}).\n\nDetails:\n"
            },
            'api_error': {
                'subject': f"[{level.upper()}] Power Manager: API Error",
                'body': f"API error occurred at {timestamp}.\n\nDetails:\n"
            },
            'system_health': {
                'subject': f"[{level.upper()}] Power Manager: System Health",
                'body': f"System health report at {timestamp}.\n\nDetails:\n"
            },
            'generic': {
                'subject': f"[{level.upper()}] Power Manager: Notification",
                'body': f"Power Manager notification at {timestamp}.\n\nDetails:\n"
            }
        }
        
        # Get template or use generic
        template = templates.get(message_type, templates['generic'])
        
        # Build plain text body
        plain_body = template['body']
        for key, value in details.items():
            plain_body += f"{key}: {value}\n"
        
        # Build HTML body
        html_body = f"""
        <html>
            <body>
                <h2 style="color: {'red' if level == 'critical' else 'orange' if level == 'warning' else 'blue'};">
                    Power Manager {level.capitalize()} Alert
                </h2>
                <p><strong>Time:</strong> {timestamp}</p>
                <p><strong>Type:</strong> {message_type}</p>
                <h3>Details:</h3>
                <ul>
        """
        
        for key, value in details.items():
            html_body += f"<li><strong>{key}:</strong> {value}</li>"
        
        html_body += """
                </ul>
            </body>
        </html>
        """
        
        return template['subject'], plain_body, html_body
    
    def send_daily_report(self, metrics_summary: Dict[str, Any]) -> bool:
        """
        Send daily metrics report.
        
        Args:
            metrics_summary: Daily metrics summary
            
        Returns:
            bool: True if sent successfully
        """
        details = {
            'Date': metrics_summary.get('date', 'Unknown'),
            'Total Actions': metrics_summary.get('total_actions', 0),
            'Battery Measurements': metrics_summary.get('total_battery_measurements', 0),
            'Min Battery %': metrics_summary.get('min_battery_percent', 'N/A'),
            'Max Battery %': metrics_summary.get('max_battery_percent', 'N/A'),
            'Avg Battery %': f"{metrics_summary.get('avg_battery_percent', 0):.1f}" if metrics_summary.get('avg_battery_percent') else 'N/A',
            'End of Day Battery %': metrics_summary.get('current_battery_percent', 'N/A'),
            'Precooling Active': metrics_summary.get('precooling_active', False)
        }
        
        return self.notify('info', 'system_health', details)
    
    def send_eod_battery_warning(self, battery_percent: float, threshold: float) -> bool:
        """
        Send end-of-day battery warning.
        
        Args:
            battery_percent: Current battery percentage
            threshold: Warning threshold
            
        Returns:
            bool: True if sent successfully
        """
        details = {
            'Current Battery Level': f"{battery_percent:.1f}%",
            'Warning Threshold': f"{threshold}%",
            'Action Required': 'Check system performance and battery usage'
        }
        
        return self.notify('warning', 'eod_battery_low', details)

