import os
import logging
import xml.etree.ElementTree as ET

import pandas as pd

from tostadas_submit.prepare.xml_base import safe_text, init_xml_root, finalize_xml
from tostadas_submit.metadata import MetadataParser


# Fields to skip when writing BioSample attributes
IGNORED_FIELDS = {"organism", "test_field_1", "test_field_2", "test_field_3", "new_field_name", "new_field_name2"}


def add_action_block(submission_root, top_metadata, biosample_metadata, config_dict, accession_id=None):
    """Add a BioSample <Action><AddData> block for one sample.
    Port of BiosampleSubmission.add_action_block, lines 778-816.
    """
    namespace = safe_text(config_dict["NCBI_Namespace"])

    action = ET.SubElement(submission_root, "Action")
    add_data = ET.SubElement(action, "AddData", {"target_db": "BioSample"})
    data = ET.SubElement(add_data, "Data", {"content_type": "xml"})
    xml_content = ET.SubElement(data, "XmlContent")

    biosample = ET.SubElement(xml_content, "BioSample", {"schema_version": "2.0"})

    # SampleId with SPUID
    sample_id_el = ET.SubElement(biosample, "SampleId")
    spuid = ET.SubElement(sample_id_el, "SPUID", {"spuid_namespace": namespace})
    spuid.text = safe_text(top_metadata["ncbi-spuid"])

    # Descriptor with optional Title
    descriptor = ET.SubElement(biosample, "Descriptor")
    title_val = top_metadata.get("title")
    if pd.notna(title_val) and str(title_val).strip():
        title = ET.SubElement(descriptor, "Title")
        title.text = safe_text(title_val)

    # Organism
    organism_el = ET.SubElement(biosample, "Organism")
    organism_name = ET.SubElement(organism_el, "OrganismName")
    organism_name.text = safe_text(biosample_metadata["organism"])

    # BioProject reference
    bioproject = ET.SubElement(biosample, "BioProject")
    primary_id = ET.SubElement(bioproject, "PrimaryId", {"db": "BioProject"})
    primary_id.text = safe_text(top_metadata["ncbi-bioproject"])

    # Package
    bs_package = ET.SubElement(biosample, "Package")
    bs_package.text = safe_text(config_dict["BioSample_package"])

    # Identifier
    identifier = ET.SubElement(add_data, "Identifier")
    if not accession_id:
        id_spuid = ET.SubElement(identifier, "SPUID", {"spuid_namespace": namespace})
        id_spuid.text = safe_text(top_metadata["ncbi-spuid"])
    else:
        id_primary = ET.SubElement(identifier, "PrimaryId", {"db": "BioSample"})
        id_primary.text = accession_id

    return biosample


def _clean_date(value):
    """Strip time portion from datetime values (e.g. '2025-03-05 00:00:00' -> '2025-03-05')."""
    text = str(value).split(" ")[0]
    return text


def add_attributes_block(biosample_el, metadata, wastewater=False):
    """Add <Attributes> to a BioSample element.
    Port of BiosampleSubmission.add_attributes_block, lines 818-829.
    """
    date_fields = {"collection_date", "collection_time"}
    attributes = ET.SubElement(biosample_el, "Attributes")
    for attr_name, attr_value in metadata.items():
        if attr_name not in IGNORED_FIELDS:
            attribute = ET.SubElement(attributes, "Attribute", {"attribute_name": attr_name})
            if attr_name in date_fields:
                attribute.text = _clean_date(attr_value)
            else:
                attribute.text = safe_text(attr_value)


def prepare_biosample_xml(samples, metadata_df, config_dict, outdir, wastewater=False,
                          custom_metadata_file=None):
    """Generate BioSample submission.xml for a batch of samples.
    Port of submission_prep.py lines 70-92.
    """
    os.makedirs(outdir, exist_ok=True)
    submission_root = init_xml_root(config_dict)

    for sample in samples:
        sample_md = metadata_df[metadata_df["sample_name"] == sample.sample_id]
        if sample_md.empty:
            logging.warning(f"No metadata row for sample {sample.sample_id}, skipping BioSample.")
            continue

        parser = MetadataParser(sample_md, custom_metadata_file=custom_metadata_file)
        top_metadata = parser.extract_top_metadata()
        biosample_metadata = parser.extract_biosample_metadata()
        ww_metadata = parser.extract_wastewater_metadata()

        metadata_source = ww_metadata if wastewater else biosample_metadata
        biosample_el = add_action_block(submission_root, top_metadata, biosample_metadata, config_dict)
        add_attributes_block(biosample_el, metadata_source, wastewater=wastewater)

    xml_path = os.path.join(outdir, "submission.xml")
    finalize_xml(submission_root, xml_path)

    # Write submit.ready
    open(os.path.join(outdir, "submit.ready"), "w").close()
    logging.info(f"BioSample submission prepared at {outdir}")
