import os
import datetime
import logging
import xml.etree.ElementTree as ET

import pandas as pd

from tostadas_submit.project import load_project
from tostadas_submit.submit.ftp import get_client


FORBIDDEN_UPDATE_FIELDS = {
    ".//BioProject/PrimaryId": "bioproject",
    ".//Organism/OrganismName": "organism",
    ".//Attributes/Attribute[@attribute_name='strain']": "strain",
    ".//Attributes/Attribute[@attribute_name='isolate']": "isolate",
    ".//Attributes/Attribute[@attribute_name='serovar']": "serovar",
    ".//Attributes/Attribute[@attribute_name='serotype']": "serotype",
}


def find_biosample_by_spuid(root, spuid_value):
    for sample_elem in root.findall(".//BioSample"):
        spuid_elem = sample_elem.find("./SampleId/SPUID")
        if spuid_elem is not None and spuid_elem.text and spuid_elem.text.strip().lower() == spuid_value.lower():
            return sample_elem
    return None


def validate_immutable_fields(matches, metadata_df):
    errors = []
    for _, md_row in metadata_df.iterrows():
        sample_id = md_row["ncbi-spuid"]
        sample_elem = matches.get(sample_id)
        if sample_elem is None:
            continue
        for xpath, col_name in FORBIDDEN_UPDATE_FIELDS.items():
            orig_elem = sample_elem.find(xpath)
            if orig_elem is None:
                continue
            orig_val = orig_elem.text.strip() if orig_elem.text else ""
            if col_name in md_row and pd.notna(md_row[col_name]):
                new_val = str(md_row[col_name])
                if new_val != orig_val:
                    errors.append(
                        f"Immutable field mismatch for {sample_id} ({col_name}): "
                        f"original='{orig_val}' vs new='{new_val}'"
                    )
    if errors:
        raise ValueError("\n".join(errors))


def add_primary_id(sample_elem, biosample_accession):
    sample_id_elem = sample_elem.find("SampleId")
    if sample_id_elem is None:
        raise ValueError("No <SampleId> element found")

    existing = sample_id_elem.find("PrimaryId[@db='BioSample']")
    if existing is None:
        spuid_elem = sample_id_elem.find("SPUID")
        primary_elem = ET.Element("PrimaryId", db="BioSample")
        primary_elem.text = biosample_accession
        if spuid_elem is not None:
            idx = list(sample_id_elem).index(spuid_elem)
            sample_id_elem.insert(idx + 1, primary_elem)
        else:
            sample_id_elem.append(primary_elem)
    else:
        existing.text = biosample_accession


def update_submission_xml(tree, root, matches, metadata_df, updated_xml_path):
    updated = 0
    for _, md_row in metadata_df.iterrows():
        sample_id = md_row["ncbi-spuid"]
        biosample_acc = md_row.get("biosample_accession", "")
        sample_elem = matches.get(sample_id)
        if sample_elem is None:
            continue

        updated += 1
        if biosample_acc and pd.notna(biosample_acc):
            add_primary_id(sample_elem, str(biosample_acc))

        attributes_elem = sample_elem.find("Attributes")
        if attributes_elem is None:
            attributes_elem = ET.SubElement(sample_elem, "Attributes")
        existing_attrs = {a.get("attribute_name"): a for a in attributes_elem.findall("Attribute")}
        for col_name, value in md_row.items():
            if pd.isna(value) or col_name in FORBIDDEN_UPDATE_FIELDS.values():
                continue
            if col_name in existing_attrs:
                existing_attrs[col_name].text = str(value)
            else:
                ET.SubElement(attributes_elem, "Attribute", {"attribute_name": col_name}).text = str(value)

    if updated == 0:
        logging.error("No matching BioSample elements found.")
        return False

    tree.write(updated_xml_path, encoding="utf-8", xml_declaration=True)
    return True


def cmd_update(args):
    """Update BioSample submissions with new metadata.
    Port of submission_update.py.
    """
    project = load_project(args.project_dir)
    config_dict = project.config_dict_legacy()

    metadata_df = pd.read_csv(args.metadata, sep="\t")

    # Find the most recent batch with a biosample submission.xml
    submissions_dir = project.submissions_dir
    biosample_xml = None
    batch_id = None
    for d in sorted(os.listdir(submissions_dir), reverse=True):
        candidate = os.path.join(submissions_dir, d, "biosample", "submission.xml")
        if os.path.exists(candidate):
            biosample_xml = candidate
            batch_id = d
            break

    if not biosample_xml:
        logging.error("No biosample/submission.xml found in submissions directory.")
        project.close()
        return

    tree = ET.parse(biosample_xml)
    root = tree.getroot()

    matches = {}
    for _, md_row in metadata_df.iterrows():
        sample_id = md_row["ncbi-spuid"]
        matches[sample_id] = find_biosample_by_spuid(root, sample_id)

    try:
        validate_immutable_fields(matches, metadata_df)
    except ValueError as e:
        logging.error(f"Validation failed: {e}")
        project.close()
        return

    stamp = datetime.datetime.now().strftime("%Y%m%d")
    updated_folder = os.path.join(submissions_dir, f"{batch_id}_update_{stamp}")
    os.makedirs(updated_folder, exist_ok=True)
    updated_xml = os.path.join(updated_folder, "submission.xml")

    success = update_submission_xml(tree, root, matches, metadata_df, updated_xml)
    if not success:
        project.close()
        return

    open(os.path.join(updated_folder, "submit.ready"), "w").close()
    logging.info(f"Updated submission ready at {updated_folder}")

    if args.dry_run:
        logging.info("[DRY-RUN] Would upload updated submission.")
    else:
        mode_str = "Test" if project.config.get("submission", {}).get("test", True) else "Production"
        transfer_mode = project.config.get("submission", {}).get("mode", "ftp")
        client = get_client(config_dict, mode=transfer_mode)
        remote_dir = f"submit/{mode_str}/{os.path.basename(updated_folder)}"
        client.connect()
        client.make_dir(remote_dir)
        client.change_dir(remote_dir)
        for fname in os.listdir(updated_folder):
            client.upload_file(os.path.join(updated_folder, fname), fname)
        client.close()
        logging.info(f"Uploaded update to {remote_dir}")

    project.close()
