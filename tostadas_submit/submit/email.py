import os
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication


def send_sqn_email(sample_id, config_dict, mode, submission_dir, dry_run=True):
    """Send .sqn file via email to NCBI.
    Port of sendemail() from submission_helper.py lines 55-106.
    """
    table2asn_email = config_dict.get("table2asn_email")
    submitter_info = config_dict.get("Submitter", {})
    from_email = submitter_info.get("@email")
    alt_email = submitter_info.get("@alt_email")

    to_email = []
    cc_email = []
    if alt_email:
        cc_email.append(alt_email)

    if mode == "Test":
        if from_email:
            to_email.append(from_email)
    else:
        if table2asn_email:
            to_email.append(table2asn_email)

    subject = f"{sample_id} table2asn submission"
    attachment_path = os.path.join(submission_dir, f"{sample_id}.sqn")

    if dry_run:
        logging.info(
            f"[DRY-RUN] Would send email:\n"
            f"  From: {from_email}\n"
            f"  To: {to_email}\n"
            f"  Cc: {cc_email}\n"
            f"  Subject: {subject}\n"
            f"  Attachment: {attachment_path}"
        )
        return

    msg = MIMEMultipart("mixed")
    msg["Subject"] = subject
    msg["From"] = from_email
    msg["To"] = ", ".join(to_email)
    if cc_email:
        msg["Cc"] = ", ".join(cc_email)

    with open(attachment_path, "rb") as fh:
        part = MIMEApplication(fh.read(), Name=f"{sample_id}.sqn")
    part["Content-Disposition"] = f'attachment; filename="{sample_id}.sqn"'
    msg.attach(part)

    s = smtplib.SMTP("localhost")
    s.sendmail(from_email, to_email + cc_email, msg.as_string())
    s.quit()
    logging.info(f"Email sent for {sample_id} to {to_email}")
