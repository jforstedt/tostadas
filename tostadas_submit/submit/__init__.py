import os
import fnmatch
import logging

from tostadas_submit.project import load_project
from tostadas_submit.submit.ftp import get_client
from tostadas_submit.submit.email import send_sqn_email


COMMON_ALLOWED = ["submission.xml", "submit.ready"]
EXTRA_ALLOWED = {
    "biosample": [],
    "sra": ["*.fq", "*.fq.gz", "*.fastq", "*.fastq.gz"],
    "genbank": ["*.fasta", "*.sqn"],
}


def is_fastq_file(filename):
    return filename.lower().endswith((".fq", ".fq.gz", ".fastq", ".fastq.gz"))


def cmd_submit(args):
    """Upload prepared submission files to NCBI.
    Port of submission.py main_submit, lines 42-144.
    """
    project = load_project(args.project_dir)
    config_dict = project.config_dict_legacy()
    state_db = project.state_db

    # test mode: CLI flag overrides config
    sub_config = project.config.get("submission", {})
    test_mode = args.test if args.test is not None else sub_config.get("test", True)
    if isinstance(test_mode, str):
        test_mode = test_mode.lower() in ("true", "yes", "1")
    mode_str = "Test" if test_mode else "Production"

    identifier = args.identifier or os.path.basename(project.project_dir)

    transfer_mode = sub_config.get("mode", "ftp")
    client = get_client(config_dict, mode=transfer_mode, dry_run=args.dry_run)

    submissions_dir = project.submissions_dir
    filter_dbs = set(args.databases) if args.databases else None

    for dirpath, _, files in os.walk(submissions_dir):
        if dirpath == submissions_dir:
            continue
        if not files:
            continue

        if "submission.xml" in files and "submit.ready" in files:
            rel = os.path.relpath(dirpath, submissions_dir)
            parts = rel.split(os.sep)
            # parts[0] = batch_id, parts[1] = database, parts[2] = optional platform
            if len(parts) < 2:
                continue
            batch_id = parts[0]
            database = parts[1].lower()
            platform = parts[2] if len(parts) > 2 else None

            if filter_dbs and database not in filter_dbs:
                continue

            allowed_patterns = COMMON_ALLOWED + EXTRA_ALLOWED.get(database, [])
            files_to_upload = [
                f for f in files
                if any(fnmatch.fnmatch(f, p) for p in allowed_patterns)
            ]
            if "submit.ready" in files_to_upload:
                files_to_upload.remove("submit.ready")
                files_to_upload.append("submit.ready")

            if not files_to_upload:
                continue

            # Build remote directory path
            base_folder = f"{identifier}_{batch_id}_{database}"
            if platform:
                base_folder += f"_{platform}"
            remote_dir = f"submit/{mode_str}/{base_folder}"

            if args.dry_run:
                logging.info(f"[DRY-RUN] Would upload to: {remote_dir}")
                for fname in files_to_upload:
                    logging.info(f"[DRY-RUN]   {os.path.join(dirpath, fname)}")
            else:
                client.connect()
                client.make_dir(remote_dir)
                client.change_dir(remote_dir)
                for fname in files_to_upload:
                    local = os.path.join(dirpath, fname)
                    client.upload_file(local, fname)
                    if is_fastq_file(fname):
                        try:
                            if os.path.islink(local):
                                os.remove(local)
                                logging.info(f"Deleted symlinked FASTQ after upload: {local}")
                            else:
                                logging.warning(f"FASTQ {local} is not a symlink, keeping original.")
                        except OSError as e:
                            logging.warning(f"Could not delete FASTQ {local}: {e}")
                client.close()

            state_db.record_submission(database, batch_id, remote_dir)

        elif any(f.endswith(".sqn") for f in files):
            if filter_dbs and "genbank" not in filter_dbs:
                continue
            rel = os.path.relpath(dirpath, submissions_dir)
            parts = rel.split(os.sep)
            batch_id = parts[0] if parts else "unknown"
            sample_id = parts[1] if len(parts) > 1 else os.path.basename(dirpath)

            if args.send_email:
                send_sqn_email(sample_id, config_dict, mode_str, dirpath,
                               dry_run=args.dry_run)
                state_db.record_submission("genbank", batch_id, f"email:{sample_id}")
            else:
                logging.info(f"GenBank .sqn found for {sample_id} but --send-email not set. Skipping upload.")

    project.close()
    logging.info("Submit complete.")
