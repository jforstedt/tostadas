import os
import time
import logging
import xml.etree.ElementTree as ET

import pandas as pd

from tostadas_submit.project import load_project
from tostadas_submit.submit.ftp import get_client


def parse_report_xml_to_df(report_path):
    """Parse NCBI report.xml into a DataFrame.
    Port of parse_report_xml_to_df from submission_helper.py lines 191-293.
    """
    reports = []
    try:
        tree = ET.parse(report_path)
        root = tree.getroot()
        submission_status = root.get("status")
        submission_id = root.get("submission_id")
        tracking_tag = root.find("Tracking/SubmissionLocation")
        tracking_location = tracking_tag.text if tracking_tag is not None else None

        actions = root.findall("Action")
        if not actions:
            return pd.DataFrame()

        for action in actions:
            action_id = action.get("action_id")
            target_db = action.get("target_db", "").lower()
            status = action.get("status")

            response_message = None
            spuid = None
            spuid_namespace = None
            object_id = None
            accession = None

            response = action.find("Response")
            if response is not None:
                msg_tag = response.find("Message")
                if msg_tag is not None:
                    response_message = msg_tag.text.strip()
                else:
                    response_message = response.get("status", "").strip() or (response.text or "").strip()

                object_tag = response.find("Object")
                if object_tag is not None:
                    spuid = object_tag.get("spuid")
                    spuid_namespace = object_tag.get("spuid_namespace")
                    object_id = object_tag.get("object_id")
                    accession = object_tag.get("accession")

            report = {
                "submission_id": submission_id,
                "spuid": spuid,
                "spuid_namespace": spuid_namespace,
                "object_id": object_id,
                "submission_name": action_id,
                "submission_status": submission_status,
                "biosample_status": None,
                "biosample_accession": None,
                "biosample_message": None,
                "sra_status": None,
                "sra_accession": None,
                "sra_message": None,
                "genbank_status": None,
                "genbank_accession": None,
                "genbank_message": None,
                "tracking_location": tracking_location,
            }

            if target_db == "biosample":
                report["biosample_status"] = status
                report["biosample_message"] = response_message
                if accession:
                    report["biosample_accession"] = accession
            elif target_db == "sra":
                report["sra_status"] = status
                report["sra_message"] = response_message
                if accession:
                    report["sra_accession"] = accession
            elif target_db == "genbank":
                report["genbank_status"] = status
                report["genbank_message"] = response_message
                if accession:
                    report["genbank_accession"] = accession

            reports.append(report)

    except FileNotFoundError:
        logging.error(f"Report not found: {report_path}")
    except ET.ParseError:
        logging.error(f"Error parsing XML report: {report_path}")

    df = pd.DataFrame(reports)
    if not df.empty:
        df = df.where(pd.notna(df), None)
    return df


def cmd_status(args):
    """Fetch NCBI submission reports and update state database.
    Port of fetch_submission.py main_fetch, lines 28-90.
    """
    project = load_project(args.project_dir)
    config_dict = project.config_dict_legacy()
    state_db = project.state_db

    submissions = state_db.get_submissions(status="submitted")
    if not submissions:
        logging.info("No submitted entries found in state database.")
        # Print current sample status summary
        _print_summary(state_db)
        project.close()
        return

    transfer_mode = project.config.get("submission", {}).get("mode", "ftp")
    client = get_client(config_dict, mode=transfer_mode)

    timeout = args.timeout
    start_time = time.time()

    for sub in submissions:
        remote_dir = sub["remote_dir"]
        if not remote_dir or remote_dir.startswith("email:"):
            continue

        database = sub["database"]
        batch_id = sub["batch_id"]
        local_report = os.path.join(project.submissions_dir, batch_id, database, "report.xml")
        os.makedirs(os.path.dirname(local_report), exist_ok=True)

        try:
            client.connect()
            client.change_dir(remote_dir)
        except Exception as e:
            logging.warning(f"Could not access {remote_dir}: {e}")
            continue

        success = False
        while time.time() - start_time < timeout:
            try:
                if client.file_exists("report.xml"):
                    client.download_file("report.xml", local_report)
                    success = True
                    break
            except Exception:
                pass
            logging.info(f"Waiting for report.xml at {remote_dir}...")
            time.sleep(3)

        client.close()

        if success:
            logging.info(f"Fetched report.xml for {database} ({batch_id})")
            df = parse_report_xml_to_df(local_report)
            state_db.update_submission(sub["id"], status="complete", report_xml=local_report)

            # Update individual sample statuses
            for _, row in df.iterrows():
                sample_name = row.get("spuid")
                if not sample_name:
                    continue
                for db in ("biosample", "sra", "genbank"):
                    acc = row.get(f"{db}_accession")
                    db_status = row.get(f"{db}_status")
                    if db_status:
                        new_status = "succeeded" if acc else "processing"
                        state_db.update_sample_status(sample_name, db, new_status, accession=acc)
        else:
            logging.warning(f"Timeout fetching report for {database} ({batch_id})")

    _print_summary(state_db)
    project.close()


def _print_summary(state_db):
    samples = state_db.get_all_samples()
    if not samples:
        print("No samples in database.")
        return

    print(f"\n{'Sample':<30} {'BioSample':<15} {'SRA':<15} {'GenBank':<15}")
    print("-" * 75)
    for s in samples:
        bs = f"{s['biosample_status']}"
        if s.get("biosample_acc"):
            bs += f" ({s['biosample_acc']})"
        sra = f"{s['sra_status']}"
        if s.get("sra_acc"):
            sra += f" ({s['sra_acc']})"
        gb = f"{s['genbank_status']}"
        if s.get("genbank_acc"):
            gb += f" ({s['genbank_acc']})"
        print(f"{s['sample_name']:<30} {bs:<15} {sra:<15} {gb:<15}")
