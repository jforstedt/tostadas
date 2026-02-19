import os
import shutil
import logging
import xml.etree.ElementTree as ET

from tostadas_submit.prepare.xml_base import safe_text, init_xml_root, finalize_xml
from tostadas_submit.metadata import MetadataParser


def get_compound_extension(filename):
    """Return compound extension like '.fastq.gz'.
    Port of get_compound_extension from submission_helper.py lines 45-53.
    """
    parts = os.path.basename(filename).split(".")
    if len(parts) >= 3:
        return "." + ".".join(parts[-2:])
    elif len(parts) == 2:
        return "." + parts[-1]
    return ""


def symlink_or_copy(src, dst, copy=False):
    if not os.path.exists(dst):
        if copy:
            shutil.copy(src, dst)
        else:
            os.symlink(os.path.abspath(src), dst)


def add_action_block(submission_root, sample):
    """Add SRA <Action><AddFiles> block for one sample.
    Port of SRASubmission.add_action_block, lines 841-854.
    """
    action = ET.SubElement(submission_root, "Action")
    add_files = ET.SubElement(action, "AddFiles", target_db="SRA")

    ext1 = get_compound_extension(sample.fastq1)
    ext2 = get_compound_extension(sample.fastq2)
    fastq1_name = f"{sample.sample_id}_R1{ext1}"
    fastq2_name = f"{sample.sample_id}_R2{ext2}"

    file1 = ET.SubElement(add_files, "File", file_path=fastq1_name)
    dt1 = ET.SubElement(file1, "DataType")
    dt1.text = "generic-data"

    file2 = ET.SubElement(add_files, "File", file_path=fastq2_name)
    dt2 = ET.SubElement(file2, "DataType")
    dt2.text = "generic-data"

    return add_files


def add_attributes_block(add_files_el, sra_metadata, top_metadata, config_dict):
    """Add SRA attributes, BioProject/BioSample references, and Identifier.
    Port of SRASubmission.add_attributes_block, lines 856-874.
    """
    namespace = safe_text(config_dict["NCBI_Namespace"])

    for attr_name, attr_value in sra_metadata.items():
        attribute = ET.SubElement(add_files_el, "Attribute", {"name": attr_name})
        attribute.text = safe_text(attr_value)

    # BioProject reference
    ref_bioproject = ET.SubElement(add_files_el, "AttributeRefId", name="BioProject")
    refid_bp = ET.SubElement(ref_bioproject, "RefId")
    primary_bp = ET.SubElement(refid_bp, "PrimaryId")
    primary_bp.text = safe_text(top_metadata["ncbi-bioproject"])

    # BioSample reference
    ref_biosample = ET.SubElement(add_files_el, "AttributeRefId", name="BioSample")
    refid_bs = ET.SubElement(ref_biosample, "RefId")
    spuid_bs = ET.SubElement(refid_bs, "SPUID", {"spuid_namespace": namespace})
    spuid_bs.text = safe_text(top_metadata["ncbi-spuid"])

    # Identifier
    identifier = ET.SubElement(add_files_el, "Identifier")
    id_spuid = ET.SubElement(identifier, "SPUID", {"spuid_namespace": namespace})
    id_spuid.text = safe_text(top_metadata["ncbi-spuid-sra"])


def prepare_sra_fastqs(samples, outdir, copy=False):
    """Symlink or copy FASTQ files into submission directory.
    Port of prepare_sra_fastqs from submission_prep.py lines 17-33.
    """
    for sample in samples:
        if sample.fastq1 and sample.fastq2:
            ext1 = get_compound_extension(sample.fastq1)
            ext2 = get_compound_extension(sample.fastq2)
            dest_fq1 = os.path.join(outdir, f"{sample.sample_id}_R1{ext1}")
            dest_fq2 = os.path.join(outdir, f"{sample.sample_id}_R2{ext2}")
            symlink_or_copy(sample.fastq1, dest_fq1, copy=copy)
            symlink_or_copy(sample.fastq2, dest_fq2, copy=copy)


def prepare_sra_xml(samples, metadata_df, config_dict, outdir, custom_metadata_file=None):
    """Generate SRA submission.xml for a batch of samples.
    Handles platform splitting (illumina/nanopore).
    Port of submission_prep.py lines 95-125.
    """
    illumina_samples = [s for s in samples if s.fastq1 and s.fastq2]
    nanopore_samples = [s for s in samples if s.nanopore]

    if illumina_samples and nanopore_samples:
        platforms = [("illumina", illumina_samples), ("nanopore", nanopore_samples)]
    elif illumina_samples:
        platforms = [(None, illumina_samples)]
    elif nanopore_samples:
        platforms = [(None, nanopore_samples)]
    else:
        logging.warning("No samples with FASTQ files for SRA submission.")
        return

    for platform, sample_list in platforms:
        if platform:
            platform_dir = os.path.join(outdir, platform)
        else:
            platform_dir = outdir
        os.makedirs(platform_dir, exist_ok=True)

        submission_root = init_xml_root(config_dict)

        for sample in sample_list:
            sample_md = metadata_df[metadata_df["sample_name"] == sample.sample_id]
            if sample_md.empty:
                logging.warning(f"No metadata row for sample {sample.sample_id}, skipping SRA.")
                continue

            parser = MetadataParser(sample_md, custom_metadata_file=custom_metadata_file)
            top_metadata = parser.extract_top_metadata()
            all_platform_metadata = parser.extract_sra_metadata()

            if platform:
                sra_metadata = dict(all_platform_metadata).get(platform, {})
            else:
                sra_metadata = all_platform_metadata[0][1] if all_platform_metadata else {}

            add_files_el = add_action_block(submission_root, sample)
            add_attributes_block(add_files_el, sra_metadata, top_metadata, config_dict)

        xml_path = os.path.join(platform_dir, "submission.xml")
        finalize_xml(submission_root, xml_path)
        open(os.path.join(platform_dir, "submit.ready"), "w").close()

        prepare_sra_fastqs(sample_list, platform_dir, copy=False)
        logging.info(f"SRA submission prepared at {platform_dir}")
