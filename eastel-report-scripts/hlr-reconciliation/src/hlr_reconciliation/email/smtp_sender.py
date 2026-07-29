from __future__ import annotations

import smtplib
from email.message import EmailMessage
from pathlib import Path

from hlr_reconciliation.core.exceptions import EmailError
from hlr_reconciliation.models.config import EmailConfig
from hlr_reconciliation.models.summary import ExecutionSummary


class SmtpEmailSender:
    def __init__(self, config: EmailConfig) -> None:
        self.config = config

    def send_report(self, report_path: Path, summary: ExecutionSummary) -> None:
        if not self.config.enabled:
            return
        message = EmailMessage()
        message["From"] = self.config.sender
        message["To"] = ", ".join(self.config.recipients)
        if self.config.cc:
            message["Cc"] = ", ".join(self.config.cc)
        message["Subject"] = self.config.subject_template.format(**summary.__dict__)
        message.set_content(self.config.body_template.format(**summary.__dict__))
        message.add_attachment(
            report_path.read_bytes(),
            maintype="text",
            subtype="csv",
            filename=report_path.name,
        )
        recipients = list(self.config.recipients + self.config.cc + self.config.bcc)
        try:
            if self.config.use_ssl:
                server = smtplib.SMTP_SSL(self.config.smtp_server, self.config.port)
            else:
                server = smtplib.SMTP(self.config.smtp_server, self.config.port)
            with server:
                if self.config.use_tls and not self.config.use_ssl:
                    server.starttls()
                if self.config.username:
                    server.login(self.config.username, self.config.password)
                server.send_message(message, to_addrs=recipients)
        except Exception as exc:
            raise EmailError("Failed to send HLR reconciliation email") from exc
