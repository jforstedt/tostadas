import math
import logging
import xml.etree.ElementTree as ET
import xml.dom.minidom as minidom

import pandas as pd


def safe_text(value):
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "Not Provided"
    return str(value)


def init_xml_root(config_dict):
    """Create the <Submission> XML root with Description, Organization, Contact.
    Port of XMLSubmission.init_xml_root from submission_helper.py lines 699-724.
    """
    submission_root = ET.Element("Submission")
    description = ET.SubElement(submission_root, "Description")

    if "Specified_Release_Date" in config_dict:
        release_date_value = config_dict["Specified_Release_Date"]
        if release_date_value and release_date_value != "Not Provided":
            hold = ET.SubElement(description, "Hold")
            hold.set("release_date", release_date_value)

    comment = ET.SubElement(description, "Comment")
    comment.text = "Batch submission"

    org_attrs = {
        "role": config_dict["Role"],
        "type": config_dict["Type"],
    }
    org_id = config_dict.get("Org_ID", "").strip()
    if org_id:
        org_attrs["org_id"] = org_id

    organization_el = ET.SubElement(description, "Organization", org_attrs)
    name = ET.SubElement(organization_el, "Name")
    name.text = safe_text(config_dict["Submitting_Org"])

    contact_el = ET.SubElement(organization_el, "Contact", {"email": config_dict["Email"]})
    contact_name = ET.SubElement(contact_el, "Name")
    ET.SubElement(contact_name, "First").text = safe_text(config_dict["Submitter"]["Name"]["First"])
    ET.SubElement(contact_name, "Last").text = safe_text(config_dict["Submitter"]["Name"]["Last"])

    return submission_root


def finalize_xml(root, output_path):
    """Pretty-print XML to file.
    Port of XMLSubmission.finalize_xml from submission_helper.py lines 725-733.
    """
    rough_string = ET.tostring(root, encoding="utf-8")
    reparsed = minidom.parseString(rough_string)
    pretty_xml = reparsed.toprettyxml(indent="  ")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(pretty_xml)
    logging.info(f"XML generated at {output_path}")
