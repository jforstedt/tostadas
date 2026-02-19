import sys
import logging
import yaml


def load_config_file(path):
    with open(path, "r") as f:
        config_dict = yaml.load(f, Loader=yaml.BaseLoader)
    if not isinstance(config_dict, dict):
        logging.error("Config file must have a valid YAML format.")
        sys.exit(1)
    return config_dict


def detect_config_format(config_dict):
    if "ncbi" in config_dict and isinstance(config_dict["ncbi"], dict):
        return "new"
    return "legacy"


def legacy_to_new(config_dict):
    submitter = config_dict.get("Submitter", {})
    name = submitter.get("Name", {})
    return {
        "ncbi": {
            "username": config_dict.get("NCBI_username", ""),
            "password": config_dict.get("NCBI_password", ""),
            "ftp_host": config_dict.get("NCBI_ftp_host", "ftp-private.ncbi.nlm.nih.gov"),
            "sftp_host": config_dict.get("NCBI_sftp_host", "sftp-private.ncbi.nlm.nih.gov"),
            "namespace": config_dict.get("NCBI_Namespace", ""),
            "org_id": config_dict.get("Org_ID", ""),
        },
        "organization": {
            "name": config_dict.get("Submitting_Org", ""),
            "department": config_dict.get("Submitting_Org_Dept", ""),
            "role": config_dict.get("Role", "owner"),
            "type": config_dict.get("Type", "institute"),
            "street": config_dict.get("Street", ""),
            "city": config_dict.get("City", ""),
            "state": config_dict.get("State", ""),
            "country": config_dict.get("Country", ""),
            "postal_code": config_dict.get("Postal_code", ""),
            "email": config_dict.get("Email", ""),
            "phone": config_dict.get("Phone", ""),
        },
        "submitter": {
            "first_name": name.get("First", ""),
            "last_name": name.get("Last", ""),
            "email": submitter.get("@email", ""),
            "alt_email": submitter.get("@alt_email", ""),
        },
        "submission": {
            "mode": "ftp",
            "test": True,
            "release_date": config_dict.get("Specified_Release_Date", ""),
            "biosample_package": config_dict.get("BioSample_package", "Pathogen.cl.1.0"),
            "table2asn_email": config_dict.get("table2asn_email", ""),
        },
    }


def new_to_legacy(config):
    ncbi = config.get("ncbi", {})
    org = config.get("organization", {})
    sub = config.get("submitter", {})
    submission = config.get("submission", {})
    return {
        "NCBI_username": ncbi.get("username", ""),
        "NCBI_password": ncbi.get("password", ""),
        "NCBI_ftp_host": ncbi.get("ftp_host", "ftp-private.ncbi.nlm.nih.gov"),
        "NCBI_sftp_host": ncbi.get("sftp_host", "sftp-private.ncbi.nlm.nih.gov"),
        "NCBI_Namespace": ncbi.get("namespace", ""),
        "Org_ID": ncbi.get("org_id", ""),
        "Role": org.get("role", "owner"),
        "Type": org.get("type", "institute"),
        "Submitting_Org": org.get("name", ""),
        "Submitting_Org_Dept": org.get("department", ""),
        "Email": org.get("email", ""),
        "Phone": org.get("phone", ""),
        "Street": org.get("street", ""),
        "City": org.get("city", ""),
        "State": org.get("state", ""),
        "Country": org.get("country", ""),
        "Postal_code": org.get("postal_code", ""),
        "BioSample_package": submission.get("biosample_package", "Pathogen.cl.1.0"),
        "table2asn_email": submission.get("table2asn_email", ""),
        "Specified_Release_Date": submission.get("release_date", ""),
        "Submitter": {
            "@email": sub.get("email", ""),
            "@alt_email": sub.get("alt_email", ""),
            "Name": {
                "First": sub.get("first_name", ""),
                "Last": sub.get("last_name", ""),
            },
        },
    }


def load_and_normalize(path):
    raw = load_config_file(path)
    fmt = detect_config_format(raw)
    if fmt == "legacy":
        return legacy_to_new(raw)
    return raw


def parse_pathogen_config(path):
    """Parse a Nextflow pathogen config file (conf/measles.config, etc.)
    and return a dict of the params block values.
    """
    params = {}
    in_params = False
    with open(path, "r") as f:
        for line in f:
            stripped = line.strip()
            if stripped.startswith("params {") or stripped == "params {":
                in_params = True
                continue
            if in_params and stripped == "}":
                break
            if in_params and "=" in stripped:
                key, _, value = stripped.partition("=")
                key = key.strip()
                value = value.strip().rstrip(",")
                # Unquote strings
                if (value.startswith("'") and value.endswith("'")) or \
                   (value.startswith('"') and value.endswith('"')):
                    value = value[1:-1]
                elif value == "true":
                    value = True
                elif value == "false":
                    value = False
                elif value == "null":
                    value = None
                params[key] = value
    return params


def resolve_species(pathogen_params):
    """Map organism_type + virus_subtype from a pathogen config to
    the species string used by the CLI."""
    org_type = pathogen_params.get("organism_type", "")
    subtype = pathogen_params.get("virus_subtype")
    if org_type == "bacteria":
        return "bacteria"
    if subtype and subtype != "null":
        return subtype
    return org_type or "virus"
