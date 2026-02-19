import os
import json
import logging
import dataclasses
from typing import Optional, List

import pandas as pd


@dataclasses.dataclass
class SampleRecord:
    sample_id: str
    batch_id: str
    species: str
    databases: List[str]
    fastq1: Optional[str] = None
    fastq2: Optional[str] = None
    nanopore: Optional[str] = None
    fasta_file: Optional[str] = None
    annotation_file: Optional[str] = None

    @property
    def ftp_upload(self):
        return self.species in {"flu", "sars", "bacteria"}


def load_metadata(path):
    ext = os.path.splitext(path)[1].lower()
    if ext in (".xlsx", ".xls"):
        df = pd.read_excel(path, header=1, engine="openpyxl")
    elif ext in (".tsv", ".txt"):
        df = pd.read_csv(path, sep="\t")
    elif ext == ".csv":
        df = pd.read_csv(path)
    else:
        raise ValueError(f"Unsupported metadata file type: {ext}")
    return df


def find_file_for_sample(sample_name, search_dir, extensions):
    if not search_dir or not os.path.isdir(search_dir):
        return None
    for ext in extensions:
        candidate = os.path.join(search_dir, f"{sample_name}{ext}")
        if os.path.exists(candidate):
            return os.path.abspath(candidate)
    # Also try without strict name matching — check files that start with sample_name
    for fname in os.listdir(search_dir):
        base = os.path.splitext(fname)[0]
        # Strip compound extensions like .trimmed.fasta
        while "." in base:
            base = os.path.splitext(base)[0]
        if base == sample_name:
            return os.path.abspath(os.path.join(search_dir, fname))
    return None


def build_sample_records(metadata_df, batch_id, species, databases,
                         fasta_dir=None, gff_dir=None, fastq_dir=None):
    fasta_exts = [".fasta", ".fa", ".fsa", ".fna"]
    gff_exts = [".gff", ".gff3"]
    fq_r1_suffixes = ["_R1.fastq.gz", "_R1.fq.gz", "_1.fastq.gz", "_1.fq.gz",
                      "_R1.fastq", "_R1.fq"]
    fq_r2_suffixes = ["_R2.fastq.gz", "_R2.fq.gz", "_2.fastq.gz", "_2.fq.gz",
                      "_R2.fastq", "_R2.fq"]

    samples = []
    for _, row in metadata_df.iterrows():
        sample_name = str(row["sample_name"])

        # FASTA: check metadata column first, then directory discovery
        fasta_path = None
        if "fasta_path" in row and pd.notna(row["fasta_path"]) and str(row["fasta_path"]).strip():
            fasta_path = str(row["fasta_path"])
            if not os.path.isabs(fasta_path) and fasta_dir:
                fasta_path = os.path.join(fasta_dir, fasta_path)
        elif fasta_dir:
            fasta_path = find_file_for_sample(sample_name, fasta_dir, fasta_exts)

        # GFF/TBL annotation file
        annotation_file = None
        if "gff_path" in row and pd.notna(row["gff_path"]) and str(row["gff_path"]).strip():
            annotation_file = str(row["gff_path"])
        elif gff_dir:
            annotation_file = find_file_for_sample(sample_name, gff_dir, gff_exts + [".tbl"])

        # FASTQs
        fq1 = None
        fq2 = None
        if fastq_dir and os.path.isdir(fastq_dir):
            for suffix in fq_r1_suffixes:
                candidate = os.path.join(fastq_dir, f"{sample_name}{suffix}")
                if os.path.exists(candidate):
                    fq1 = os.path.abspath(candidate)
                    break
            for suffix in fq_r2_suffixes:
                candidate = os.path.join(fastq_dir, f"{sample_name}{suffix}")
                if os.path.exists(candidate):
                    fq2 = os.path.abspath(candidate)
                    break

        samples.append(SampleRecord(
            sample_id=sample_name,
            batch_id=batch_id,
            species=species,
            databases=databases,
            fastq1=fq1,
            fastq2=fq2,
            fasta_file=fasta_path,
            annotation_file=annotation_file,
        ))

    return samples


class MetadataParser:
    """Port of MetadataParser from submission_helper.py.
    Operates on a single-row DataFrame for one sample.
    """

    def __init__(self, metadata_df, custom_metadata_file=None):
        self.metadata_df = metadata_df
        self.custom_columns = self._load_custom_columns(custom_metadata_file)

    @staticmethod
    def _load_custom_columns(json_file_path):
        if not json_file_path:
            return []
        try:
            with open(json_file_path, "r") as f:
                custom_metadata = json.load(f)
            return [
                value.get("new_field_name", key).strip() or key.strip()
                for key, value in custom_metadata.items()
            ]
        except Exception as e:
            logging.info(f"Error loading custom metadata file: {e}")
            return []

    def extract_top_metadata(self):
        columns = [
            "sequence_name", "title", "description", "authors",
            "ncbi-bioproject", "ncbi-spuid", "ncbi-spuid-sra",
        ]
        available = [c for c in columns if c in self.metadata_df.columns]
        if not available:
            return {}
        return self.metadata_df[available].to_dict(orient="records")[0]

    def extract_biosample_metadata(self):
        columns = [
            "strain", "isolate", "host_disease", "host", "collected_by",
            "lat_lon", "geo_loc_name", "country", "state", "organism",
            "sample_type", "collection_date", "isolation_source",
            "host_age", "host_sex", "race", "ethnicity", "note",
        ]
        all_columns = columns + self.custom_columns
        available = [c for c in all_columns if c in self.metadata_df.columns]
        if not available:
            return {}
        return self.metadata_df[available].to_dict(orient="records")[0]

    def extract_wastewater_metadata(self):
        columns = [
            "description", "isolation_source", "organism", "collection_date",
            "collection_time", "country", "state", "collection_site_id",
            "project_name", "collected_by", "purpose_of_ww_sampling",
            "ww_sample_site", "ww_flow", "instantaneous_flow", "ww_population",
            "ww_surv_jurisdiction", "ww_population_source", "ww_sample_matrix",
            "ww_sample_type", "collection_volume", "ww_sample_duration",
            "ww_temperature", "ww_ph", "ww_industrial_effluent_percent",
            "ww_sample_salinity", "ww_total_suspended_solids",
            "ww_surv_system_sample_id", "ww_pre_treatment",
            "ww_primary_sludge_retention_time", "specimen_processing",
            "specimen_processing_id", "specimen_processing_details",
            "ww_processing_protocol", "concentration_method",
            "extraction_method", "extraction_control", "ww_endog_control_1",
            "ww_endog_control_1_conc", "ww_endog_control_1_protocol",
            "ww_endog_control_1_units", "ww_endog_control_2",
            "ww_endog_control_2_conc", "ww_endog_control_2_protocol",
            "ww_endog_control_2_units", "ww_surv_target_1",
            "ww_surv_target_1_known_present", "ww_surv_target_1_protocol",
            "ww_surv_target_1_conc", "ww_surv_target_1_conc_unit",
            "ww_surv_target_1_gene", "ww_surv_target_2",
            "ww_surv_target_2_conc", "ww_surv_target_2_conc_unit",
            "ww_surv_target_2_gene", "ww_surv_target_2_known_present",
            "purpose_of_ww_sequencing", "sequenced_by",
        ]
        all_columns = columns + self.custom_columns
        available = [c for c in all_columns if c in self.metadata_df.columns]
        if not available:
            return {}
        record = self.metadata_df[available].to_dict(orient="records")[0]
        return {k: v for k, v in record.items() if pd.notna(v) and v != ""}

    def extract_sra_metadata(self):
        rename_fields = {
            "sequencing_instrument": "instrument_model",
            "library_protocol": "library_construction_protocol",
        }

        def process_platform(prefix):
            result = {}
            for k, v in self.metadata_df.iloc[0].items():
                if not k.startswith(f"{prefix}_"):
                    continue
                key = k.replace(f"{prefix}_", "")
                key = rename_fields.get(key, key)
                result[key] = v
            all_empty = all(
                pd.isna(v) or str(v).strip() in ("", "Not Provided")
                for v in result.values()
            )
            return {} if all_empty else result

        illumina_fields = process_platform("illumina")
        nanopore_fields = process_platform("nanopore")
        platforms = []
        if illumina_fields:
            platforms.append(("illumina", illumina_fields))
        if nanopore_fields:
            platforms.append(("nanopore", nanopore_fields))
        return platforms

    def extract_genbank_metadata(self):
        columns = [
            "biosample_accession", "submitting_lab", "submitting_lab_division",
            "submitting_lab_address", "publication_status", "publication_title",
            "illumina_sequencing_instrument", "nanopore_sequencing_instrument",
            "assembly_protocol", "assembly_method", "mean_coverage",
        ]
        available = [c for c in columns if c in self.metadata_df.columns]
        if not available:
            return {}
        return self.metadata_df[available].to_dict(orient="records")[0]
