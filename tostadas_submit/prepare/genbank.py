import os
import glob
import shutil
import shlex
import logging
import subprocess
import xml.etree.ElementTree as ET

import pandas as pd
from nameparser import HumanName
from zipfile import ZipFile

from tostadas_submit.prepare.xml_base import safe_text, init_xml_root, finalize_xml


def symlink_or_copy(src, dst, copy=False):
    # Remove broken symlinks left by crashed runs
    if os.path.islink(dst) and not os.path.exists(dst):
        os.remove(dst)
    if not os.path.exists(dst):
        if copy:
            shutil.copy(src, dst)
        else:
            try:
                os.symlink(os.path.abspath(src), dst)
            except OSError:
                shutil.copy(src, dst)


# --- Source, Comment, Authorset file generation ---

def create_source_file(outdir, top_metadata, biosample_metadata):
    """Write source.src TSV for table2asn.
    Port of GenbankSubmission.create_source_file, lines 972-1006.
    """
    seq_id = top_metadata.get("ncbi-spuid-sra")
    if pd.isna(seq_id) if isinstance(seq_id, float) else not seq_id:
        seq_id = top_metadata.get("ncbi-spuid", "")

    country = biosample_metadata.get("geo_loc_name")
    if pd.isna(country) if isinstance(country, float) else not country:
        country = biosample_metadata.get("country", "")
        state = biosample_metadata.get("state", "")
        if country and state:
            country = f"{country}: {state}"

    collection_date = biosample_metadata.get("collection_date")
    if collection_date:
        collection_date = str(collection_date).split(" ")[0]

    bioproject = top_metadata.get("ncbi-bioproject")
    source_data = {
        "Sequence_ID": seq_id,
        "strain": biosample_metadata.get("strain"),
        "organism": biosample_metadata.get("organism"),
        "Collection_date": collection_date,
        "country": country,
        "isolate": biosample_metadata.get("isolate"),
        "host": biosample_metadata.get("host"),
        "isolation_source": biosample_metadata.get("isolation_source"),
        "note": biosample_metadata.get("note"),
    }
    if bioproject and str(bioproject).strip() not in ("", "nan", "Not Provided"):
        source_data["BioProject"] = bioproject

    source_df = pd.DataFrame([source_data])
    source_df.to_csv(os.path.join(outdir, "source.src"), sep="\t", index=False)


def create_comment_file(outdir, top_metadata, biosample_metadata, genbank_metadata):
    """Write comment.cmt TSV for table2asn.
    Port of GenbankSubmission.create_comment_file, lines 1008-1021.
    """
    comment_data = {
        "SeqID": top_metadata.get("sequence_name"),
        "StructuredCommentPrefix": "Assembly-Data",
        "organism": biosample_metadata.get("organism"),
        "collection_date": biosample_metadata.get("collection_date"),
        "Assembly-Protocol": genbank_metadata.get("assembly_protocol"),
        "Assembly-Method": genbank_metadata.get("assembly_method"),
        "Sequencing Technology": genbank_metadata.get("illumina_sequencing_instrument"),
        "Coverage": genbank_metadata.get("mean_coverage"),
        "StructuredCommentSuffix": "Assembly-Data",
    }
    comment_df = pd.DataFrame([comment_data])
    comment_df.to_csv(os.path.join(outdir, "comment.cmt"), sep="\t", index=False)


def create_authorset_file(outdir, config_dict, genbank_metadata, sample_id):
    """Write authorset.sbt in NCBI ASN.1 Submit-block format.
    Port of GenbankSubmission.create_authorset_file, lines 1023-1126.
    """
    submitter_first = config_dict["Submitter"]["Name"]["First"]
    submitter_last = config_dict["Submitter"]["Name"]["Last"]
    submitter_email = config_dict["Submitter"]["@email"]
    alt_submitter_email = config_dict["Submitter"]["@alt_email"]
    affil = config_dict["Submitting_Org"]
    div = config_dict["Submitting_Org_Dept"]
    street = config_dict["Street"]
    city = config_dict["City"]
    sub = config_dict["State"]
    country = config_dict["Country"]
    email = config_dict["Email"]
    phone = config_dict["Phone"]
    zip_code = config_dict["Postal_code"]

    authorset_file = os.path.join(outdir, "authorset.sbt")
    with open(authorset_file, "w+") as f:
        f.write("Submit-block ::= {\n")
        f.write("  contact {\n")
        f.write("    contact {\n")
        f.write("      name name {\n")
        f.write('        last "' + submitter_last + '",\n')
        f.write('        first "' + submitter_first + '",\n')
        f.write('        middle "",\n')
        f.write('        initials "",\n')
        f.write('        suffix "",\n')
        f.write('        title ""\n')
        f.write("      },\n")
        f.write("      affil std {\n")
        f.write('        affil "' + affil + '",\n')
        f.write('        div "' + div + '",\n')
        f.write('        city "' + city + '",\n')
        f.write('        sub "' + sub + '",\n')
        f.write('        country "' + country + '",\n')
        f.write('        street "' + street + '",\n')
        f.write('        email "' + email + '",\n')
        f.write('        phone "' + phone + '",\n')
        f.write('        postal-code "' + zip_code + '"\n')
        f.write("      }\n")
        f.write("    }\n")
        f.write("  },\n")
        f.write("  cit {\n")
        f.write("    authors {\n")
        f.write("      names std {\n")

        authors_list = safe_text(genbank_metadata.get("authors")).split("; ")
        if authors_list[0] not in ["Not Provided", ""]:
            total_names = len(authors_list)
            for index, author in enumerate(authors_list, start=1):
                name = HumanName(author.strip())
                f.write("        {\n")
                f.write("          name name {\n")
                f.write('            last "' + safe_text(name.last) + '",\n')
                f.write('            first "' + safe_text(name.first) + '"')
                middle_name = safe_text(name.middle)
                if middle_name != "Not Provided":
                    f.write(',\n            middle "' + middle_name + '"')
                suffix = safe_text(name.suffix)
                if suffix != "Not Provided":
                    f.write(',\n            suffix "' + suffix + '"')
                title = safe_text(name.title)
                if title != "Not Provided":
                    f.write(',\n            title "' + title + '"')
                f.write("\n          }\n")
                if index == total_names:
                    f.write("        }\n")
                else:
                    f.write("        },\n")

        f.write("      },\n")
        f.write("      affil std {\n")
        f.write('        affil "' + affil + '",\n')
        f.write('        div "' + div + '",\n')
        f.write('        city "' + city + '",\n')
        f.write('        sub "' + sub + '",\n')
        f.write('        country "' + country + '",\n')
        f.write('        street "' + street + '",\n')
        f.write('        postal-code "' + zip_code + '"\n')
        f.write("      }\n")
        f.write("    }\n")
        f.write("  },\n")
        f.write("  subtype new\n")
        f.write("}\n")

        if alt_submitter_email is not None and alt_submitter_email.strip() != "":
            f.write('Seqdesc ::= user {\n')
            f.write('  type str "Submission",\n')
            f.write("  data {\n")
            f.write("    {\n")
            f.write('      label str "AdditionalComment",\n')
            f.write('      data str "ALT EMAIL: ' + alt_submitter_email + '"\n')
            f.write("    }\n")
            f.write("  }\n")
            f.write("}\n")

        f.write('Seqdesc ::= user {\n')
        f.write('  type str "Submission",\n')
        f.write("  data {\n")
        f.write("    {\n")
        f.write('      label str "AdditionalComment",\n')
        f.write('      data str "Submission Title: ' + sample_id + '"\n')
        f.write("    }\n")
        f.write("  }\n")
        f.write("}\n")


# --- table2asn execution ---

def get_gff_locus_tag(annotation_file):
    """Read locus_tag from GFF3 file.
    Port of GenbankSubmission.get_gff_locus_tag, lines 1180-1201.
    """
    locus_tag = None
    if not annotation_file.endswith(".tbl"):
        with open(annotation_file, "r") as fh:
            for line in fh:
                if line.startswith("##FASTA"):
                    break
                if line.startswith("#"):
                    continue
                columns = line.strip().split("\t")
                if len(columns) >= 9 and columns[2] == "CDS":
                    for attribute in columns[8].split(";"):
                        if "=" in attribute:
                            key, value = attribute.split("=", 1)
                            if key == "locus_tag":
                                locus_tag = value.split("_")[0]
                                break
                    if locus_tag:
                        break
    return locus_tag


def is_multicontig_fasta(fasta_file):
    """Detect multiple contigs in a FASTA.
    Port of GenbankSubmission.is_multicontig_fasta, lines 1203-1211.
    """
    headers = set()
    with open(fasta_file, "r") as fh:
        for line in fh:
            if line.startswith(">"):
                headers.add(line.strip())
                if len(headers) > 1:
                    return True
    return False


def run_table2asn(outdir, sample, annotation_file, ftp_upload):
    """Execute table2asn with appropriate flags.
    Port of GenbankSubmission.run_table2asn, lines 1212-1256.
    """
    logging.info("Running table2asn...")
    table2asn_path = shutil.which("table2asn")
    if not table2asn_path:
        raise FileNotFoundError("table2asn executable not found in PATH.")

    locus_tag = None
    if annotation_file:
        locus_tag = get_gff_locus_tag(annotation_file)
        gff_dest = os.path.join(outdir, os.path.basename(annotation_file))
        symlink_or_copy(annotation_file, gff_dest)

    cmd = [
        "table2asn",
        "-i", f"{outdir}/sequence.fsa",
        "-o", f"{outdir}/{sample.sample_id}.sqn",
        "-t", f"{outdir}/authorset.sbt",
    ]

    if annotation_file:
        gff_dest = os.path.join(outdir, os.path.basename(annotation_file))
        cmd.extend(["-f", gff_dest])
        if locus_tag:
            cmd.extend(["-locus-tag-prefix", locus_tag])

    if is_multicontig_fasta(f"{outdir}/sequence.fsa"):
        cmd.extend(["-M", "n", "-Z"])

    if os.path.isfile(f"{outdir}/comment.cmt"):
        cmd.extend(["-w", "comment.cmt"])

    if not ftp_upload:
        cmd.extend(["-src-file", f"{outdir}/source.src"])

    logging.info(f"table2asn command: {shlex.join(cmd)}")
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        logging.info(f"table2asn output: {result.stdout}")
    except subprocess.CalledProcessError as e:
        logging.debug(f"Error running table2asn: {e.stderr}")
        raise


# --- .sqn post-processing ---

def strip_sqn_blocks(content):
    """Remove pub citation block from .sqn ASN.1 text.
    Port of GenbankSubmission._strip_sqn_blocks, lines 1127-1144.
    """
    lines = content.split("\n")
    result = []
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        if stripped == "pub {" or stripped == "pub {,":
            depth = 0
            while i < len(lines):
                depth += lines[i].count("{") - lines[i].count("}")
                i += 1
                if depth <= 0:
                    break
            continue
        result.append(lines[i])
        i += 1
    return "\n".join(result)


def postprocess_sqn(sqn_path, mol_type="genomic", strip_pub_block=False):
    """Post-process .sqn file: biomol replacement and pub block stripping.
    Port of GenbankSubmission.prep_table2asn_files post-processing, lines 1162-1177.
    """
    if not os.path.isfile(sqn_path):
        return

    with open(sqn_path, "r") as f:
        content = f.read()

    if mol_type != "genomic":
        content = content.replace("biomol genomic", "biomol cRNA")
        logging.info(f"Updated biomol to cRNA in {sqn_path}")

    if strip_pub_block:
        content = strip_sqn_blocks(content)
        logging.info(f"Stripped pub block from {sqn_path}")

    with open(sqn_path, "w") as f:
        f.write(content)


# --- Zip packaging ---

def prep_zip_folder(outdir, sample_id):
    """Create zip package and clean up intermediate files.
    Port of GenbankSubmission.prep_zip_folder, lines 1258-1272.
    """
    zip_path = os.path.join(outdir, f"{sample_id}.zip")
    filelist = [f"{sample_id}.sqn", "authorset.sbt", "sequence.fsa", "source.src", "comment.cmt"]
    with ZipFile(zip_path, "w") as zf:
        for fname in filelist:
            filepath = os.path.join(outdir, fname)
            if os.path.exists(filepath):
                zf.write(filepath, fname)

    for pattern in ["*.cmt", "*.sbt", "*.src", "*.gff3", "*.gff"]:
        for f in glob.glob(os.path.join(outdir, pattern)):
            if os.path.isfile(f):
                os.remove(f)


# --- GenBank XML for FTP workflows ---

def xml_create_bankit(sample, config_dict, top_metadata, outdir):
    """Create GenBank FTP submission XML for SARS/flu.
    Port of GenbankSubmission.xml_create_bankit, lines 890-933.
    """
    submission_root = ET.Element("Submission")
    description = ET.SubElement(submission_root, "Description")

    org_attrs = {
        "type": config_dict["Type"],
        "role": config_dict["Role"],
    }
    org_id = config_dict.get("Org_ID", "").strip()
    if org_id:
        org_attrs["org_id"] = org_id

    organization_el = ET.SubElement(description, "Organization", org_attrs)
    name = ET.SubElement(organization_el, "Name")
    name.text = safe_text(config_dict["Submitting_Org"])

    if "Specified_Release_Date" in config_dict:
        release_date_value = config_dict["Specified_Release_Date"]
        if release_date_value and release_date_value != "Not Provided":
            hold = ET.SubElement(description, "Hold")
            hold.set("release_date", release_date_value)

    action = ET.SubElement(submission_root, "Action")
    add_files = ET.SubElement(action, "AddFiles", {"target_db": "GenBank"})
    file_el = ET.SubElement(add_files, "File", {"file_path": "submission.zip"})
    data_type = ET.SubElement(file_el, "DataType")
    data_type.text = "genbank-submission-package"

    attribute = ET.SubElement(add_files, "Attribute", {"name": "wizard"})
    if sample.species == "sars":
        attribute.text = "BankIt_SARSCoV2_api"
    elif sample.species in ("flu", "influenza"):
        attribute.text = "BankIt_influenza_api"
    else:
        raise ValueError(f"bankit workflow requires species sars or flu, got {sample.species}")

    namespace = safe_text(config_dict["NCBI_Namespace"])
    identifier = ET.SubElement(add_files, "Identifier")
    spuid = ET.SubElement(identifier, "SPUID", {"spuid_namespace": namespace})
    spuid.text = safe_text(f'{top_metadata["ncbi-spuid"]}-GB')

    finalize_xml(submission_root, os.path.join(outdir, "submission.xml"))


def xml_create_wgs(sample, config_dict, top_metadata, genbank_metadata, outdir):
    """Create WGS submission XML for bacteria/eukaryote.
    Port of GenbankSubmission.xml_create_wgs, lines 935-968.
    """
    submission_root = init_xml_root(config_dict)

    action = ET.SubElement(submission_root, "Action")
    add_files = ET.SubElement(action, "AddFiles", target_db="WGS")
    file1 = ET.SubElement(add_files, "File", file_path=f"{sample.sample_id}.sqn")
    ET.SubElement(file1, "DataType").text = "wgs-contigs-sqn"

    meta = ET.SubElement(add_files, "Meta", content_type="XML")
    xml_content = ET.SubElement(meta, "XmlContent")
    genome = ET.SubElement(xml_content, "Genome")
    description = ET.SubElement(genome, "Description")
    assembly_metadata_choice = ET.SubElement(description, "GenomeAssemblyMetadataChoice")
    ET.SubElement(assembly_metadata_choice, "StructuredComment")
    ET.SubElement(description, "GenomeRepresentation").text = "Full"
    ET.SubElement(description, "ExpectedFinalVersion").text = "Yes"

    # BioProject reference
    attr_ref = ET.SubElement(add_files, "AttributeRefId")
    ref_id = ET.SubElement(attr_ref, "RefId")
    primary_id = ET.SubElement(ref_id, "PrimaryId", db="BioProject")
    primary_id.text = safe_text(top_metadata["ncbi-bioproject"])

    # BioSample reference
    attr_ref2 = ET.SubElement(add_files, "AttributeRefId")
    ref_id2 = ET.SubElement(attr_ref2, "RefId")
    primary_id2 = ET.SubElement(ref_id2, "PrimaryId", db="BioSample")
    primary_id2.text = safe_text(genbank_metadata["biosample_accession"])

    # Identifier
    namespace = safe_text(config_dict["NCBI_Namespace"])
    identifier = ET.SubElement(add_files, "Identifier")
    spuid = ET.SubElement(identifier, "SPUID", {"spuid_namespace": namespace})
    spuid.text = safe_text(f'{top_metadata["ncbi-spuid"]}-GB')

    finalize_xml(submission_root, os.path.join(outdir, "submission.xml"))


# --- Workflow variants ---

def _workflow_bankit(sample, config_dict, top_metadata, genbank_metadata,
                     biosample_metadata, outdir, parameters):
    """Prepare a Bank-It FTP submission (SARS/flu).
    Port of GenbankSubmission._workflow_bankit, lines 1275-1282.
    """
    xml_create_bankit(sample, config_dict, top_metadata, outdir)
    _prep_and_run_table2asn(sample, config_dict, top_metadata, biosample_metadata,
                            genbank_metadata, outdir, parameters)
    prep_zip_folder(outdir, sample.sample_id)
    open(os.path.join(outdir, "submit.ready"), "w").close()


def _workflow_bacteria_euk(sample, config_dict, top_metadata, genbank_metadata,
                           biosample_metadata, outdir, parameters):
    """Prepare a WGS FTP submission (bacteria/eukaryote).
    Port of GenbankSubmission._workflow_bacteria_euk, lines 1284-1296.
    """
    xml_create_wgs(sample, config_dict, top_metadata, genbank_metadata, outdir)
    _prep_and_run_table2asn(sample, config_dict, top_metadata, biosample_metadata,
                            genbank_metadata, outdir, parameters)
    # Clean up intermediate files, keep only .sqn
    for pattern in ["*.cmt", "*.sbt", "*.src", "*.gff3", "*.gff", "*.fsa"]:
        for f in glob.glob(os.path.join(outdir, pattern)):
            if os.path.isfile(f):
                os.remove(f)
    open(os.path.join(outdir, "submit.ready"), "w").close()


def _workflow_virus(sample, config_dict, top_metadata, genbank_metadata,
                    biosample_metadata, outdir, parameters):
    """Prepare a manual submission (generic virus/rsv/mpxv/mev).
    Port of GenbankSubmission._workflow_virus, lines 1298-1301.
    """
    _prep_and_run_table2asn(sample, config_dict, top_metadata, biosample_metadata,
                            genbank_metadata, outdir, parameters)
    prep_zip_folder(outdir, sample.sample_id)


def _prep_and_run_table2asn(sample, config_dict, top_metadata, biosample_metadata,
                            genbank_metadata, outdir, parameters):
    """Orchestrate table2asn file preparation and execution.
    Port of GenbankSubmission.prep_table2asn_files, lines 1146-1177.
    """
    create_source_file(outdir, top_metadata, biosample_metadata)
    create_comment_file(outdir, top_metadata, biosample_metadata, genbank_metadata)
    create_authorset_file(outdir, config_dict, genbank_metadata, sample.sample_id)

    renamed_fasta = os.path.join(outdir, "sequence.fsa")
    symlink_or_copy(sample.fasta_file, renamed_fasta)

    run_table2asn(outdir, sample, sample.annotation_file, sample.ftp_upload)

    sqn_file = os.path.join(outdir, f"{sample.sample_id}.sqn")
    mol_type = parameters.get("mol_type", "genomic")
    strip_pub = parameters.get("strip_pub_block", False)
    postprocess_sqn(sqn_file, mol_type=mol_type, strip_pub_block=strip_pub)

    logging.info(f"GenBank files prepared for {sample.sample_id}")


# --- Main entry point ---

def prepare_genbank_submission(sample, metadata_df, config_dict, outdir, parameters):
    """Prepare GenBank submission for one sample.
    Port of GenbankSubmission.genbank_submission_driver, lines 1303-1314.
    """
    os.makedirs(outdir, exist_ok=True)

    sample_md = metadata_df[metadata_df["sample_name"] == sample.sample_id]
    if sample_md.empty:
        logging.warning(f"No metadata row for sample {sample.sample_id}, skipping GenBank.")
        return

    from tostadas_submit.metadata import MetadataParser
    parser = MetadataParser(sample_md)
    top_metadata = parser.extract_top_metadata()
    biosample_metadata = parser.extract_biosample_metadata()
    genbank_metadata = parser.extract_genbank_metadata()

    # Add authors from top_metadata into genbank_metadata for authorset generation
    if "authors" not in genbank_metadata:
        genbank_metadata["authors"] = top_metadata.get("authors")

    logging.info(f"Preparing GenBank submission of type: {sample.species}")

    if sample.species in ("sars", "flu"):
        _workflow_bankit(sample, config_dict, top_metadata, genbank_metadata,
                         biosample_metadata, outdir, parameters)
    elif sample.species in ("bacteria", "eukaryote"):
        _workflow_bacteria_euk(sample, config_dict, top_metadata, genbank_metadata,
                               biosample_metadata, outdir, parameters)
    elif sample.species in ("virus", "rsv", "mpxv", "mev"):
        _workflow_virus(sample, config_dict, top_metadata, genbank_metadata,
                        biosample_metadata, outdir, parameters)
    else:
        logging.error(f"Unknown species: {sample.species}")
