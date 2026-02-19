import os
import logging
import math

from tostadas_submit import CONF_DIR
from tostadas_submit.project import load_project
from tostadas_submit.config import parse_pathogen_config, resolve_species
from tostadas_submit.metadata import load_metadata, build_sample_records
from tostadas_submit.prepare.biosample import prepare_biosample_xml
from tostadas_submit.prepare.sra import prepare_sra_xml
from tostadas_submit.prepare.genbank import prepare_genbank_submission


def _load_pathogen_params(args, prep_config):
    """Resolve pathogen name to config file and parse it."""
    pathogen = args.pathogen or prep_config.get("pathogen", "")
    if not pathogen:
        return {}
    config_path = os.path.join(CONF_DIR, f"{pathogen}.config")
    if not os.path.isfile(config_path):
        logging.error(f"Pathogen config not found: {config_path}")
        raise SystemExit(1)
    logging.info(f"Loaded pathogen config: {config_path}")
    return parse_pathogen_config(config_path)


def cmd_prepare(args):
    project = load_project(args.project_dir)
    config_dict = project.config_dict_legacy()
    state_db = project.state_db

    prep_config = project.config.get("prepare", {})
    pathogen_params = _load_pathogen_params(args, prep_config)

    # Species: CLI flag > pathogen config > error
    species = args.species
    if species is None and pathogen_params:
        species = resolve_species(pathogen_params)
    if not species:
        logging.error("No pathogen specified. Pass --pathogen <name> or set prepare.pathogen in project.yaml.")
        raise SystemExit(1)

    # mol_type: CLI flag > pathogen config > default "genomic"
    mol_type = args.mol_type if args.mol_type is not None else pathogen_params.get("mol_type", "genomic")

    # strip_pub_block: CLI flag > pathogen config > default False
    strip_pub = args.strip_pub_block if args.strip_pub_block is not None else pathogen_params.get("strip_pub_block", False)

    metadata_df = load_metadata(args.metadata)
    databases = args.databases
    batch_size = args.batch_size

    parameters = {
        "mol_type": mol_type,
        "strip_pub_block": strip_pub,
    }

    all_sample_names = metadata_df["sample_name"].astype(str).tolist()
    total_samples = len(all_sample_names)
    num_batches = max(1, math.ceil(total_samples / batch_size))

    logging.info(f"Preparing {total_samples} samples in {num_batches} batch(es) for {databases}")

    for batch_num in range(num_batches):
        start = batch_num * batch_size
        end = min(start + batch_size, total_samples)
        batch_names = all_sample_names[start:end]
        batch_id = f"batch_{batch_num + 1}"

        batch_df = metadata_df[metadata_df["sample_name"].astype(str).isin(batch_names)]

        # Register in state DB (idempotent)
        state_db.register_samples(batch_names, batch_id)

        # Skip samples already prepared
        pending = [s["sample_name"] for s in state_db.get_samples(batch_id=batch_id)
                   if any(s.get(f"{db}_status") == "pending" for db in databases)]
        if not pending:
            logging.info(f"Batch {batch_id}: all samples already prepared, skipping.")
            continue

        batch_df = batch_df[batch_df["sample_name"].astype(str).isin(pending)]
        samples = build_sample_records(
            batch_df, batch_id, species, databases,
            fasta_dir=args.fasta_dir, gff_dir=args.gff_dir, fastq_dir=args.fastq_dir,
        )

        batch_dir = os.path.join(project.submissions_dir, batch_id)
        os.makedirs(batch_dir, exist_ok=True)

        # BioSample
        if "biosample" in databases:
            bs_dir = os.path.join(batch_dir, "biosample")
            prepare_biosample_xml(
                samples, batch_df, config_dict, bs_dir,
                wastewater=args.wastewater,
            )

        # SRA
        if "sra" in databases:
            sra_dir = os.path.join(batch_dir, "sra")
            prepare_sra_xml(samples, batch_df, config_dict, sra_dir)

        # GenBank (per-sample)
        if "genbank" in databases:
            for sample in samples:
                gb_dir = os.path.join(batch_dir, sample.sample_id)
                prepare_genbank_submission(
                    sample, batch_df, config_dict, gb_dir, parameters,
                )

        # Update state
        for sample_name in pending:
            for db in databases:
                state_db.update_sample_status(sample_name, db, "prepared")

        logging.info(f"Batch {batch_id}: prepared {len(pending)} samples.")

    project.close()
    logging.info("Prepare complete.")
