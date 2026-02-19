import os
import logging
import yaml

from tostadas_submit.config import load_and_normalize, new_to_legacy, load_config_file, legacy_to_new, detect_config_format
from tostadas_submit.state import StateDB


PROJECT_YAML_TEMPLATE = {
    "ncbi": {
        "username": "",
        "password": "",
        "ftp_host": "ftp-private.ncbi.nlm.nih.gov",
        "sftp_host": "sftp-private.ncbi.nlm.nih.gov",
        "namespace": "",
        "org_id": "",
    },
    "organization": {
        "name": "",
        "department": "",
        "role": "owner",
        "type": "institute",
        "street": "",
        "city": "",
        "state": "",
        "country": "",
        "postal_code": "",
        "email": "",
        "phone": "",
    },
    "submitter": {
        "first_name": "",
        "last_name": "",
        "email": "",
        "alt_email": "",
    },
    "submission": {
        "mode": "ftp",
        "test": True,
        "release_date": "",
        "biosample_package": "Pathogen.cl.1.0",
        "table2asn_email": "",
    },
}


class Project:
    def __init__(self, project_dir):
        self.project_dir = os.path.abspath(project_dir)
        self.config_path = os.path.join(self.project_dir, "project.yaml")
        self.state_db_path = os.path.join(self.project_dir, "state.db")
        self.submissions_dir = os.path.join(self.project_dir, "submissions")
        self._config = None
        self._state_db = None

    @property
    def config(self):
        if self._config is None:
            self._config = load_and_normalize(self.config_path)
        return self._config

    @property
    def state_db(self):
        if self._state_db is None:
            self._state_db = StateDB(self.state_db_path)
        return self._state_db

    def config_dict_legacy(self):
        return new_to_legacy(self.config)

    def close(self):
        if self._state_db:
            self._state_db.close()


def cmd_init(args):
    project_dir = os.path.abspath(args.dir)
    os.makedirs(project_dir, exist_ok=True)
    submissions_dir = os.path.join(project_dir, "submissions")
    os.makedirs(submissions_dir, exist_ok=True)

    config_path = os.path.join(project_dir, "project.yaml")
    if os.path.exists(config_path):
        logging.info(f"project.yaml already exists at {config_path}, skipping.")
    else:
        if args.config:
            raw = load_config_file(args.config)
            fmt = detect_config_format(raw)
            if fmt == "legacy":
                config = legacy_to_new(raw)
                logging.info(f"Imported legacy config from {args.config}")
            else:
                config = raw
        else:
            config = PROJECT_YAML_TEMPLATE
        with open(config_path, "w") as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)
        logging.info(f"Created {config_path}")

    db_path = os.path.join(project_dir, "state.db")
    db = StateDB(db_path)
    db.close()
    logging.info(f"Initialized state database at {db_path}")

    logging.info(f"Project initialized at {project_dir}")


def load_project(project_dir):
    project_dir = os.path.abspath(project_dir)
    config_path = os.path.join(project_dir, "project.yaml")
    if not os.path.exists(config_path):
        logging.error(f"No project.yaml found at {config_path}. Run 'tostadas-submit init' first.")
        raise FileNotFoundError(config_path)
    return Project(project_dir)
