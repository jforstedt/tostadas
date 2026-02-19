import sys
import logging

import pandas as pd

from tostadas_submit.project import load_project


def cmd_export(args):
    """Export submission records from state database."""
    project = load_project(args.project_dir)
    samples = project.state_db.get_all_samples()

    if not samples:
        logging.info("No samples in database.")
        project.close()
        return

    df = pd.DataFrame(samples)

    sep = "\t" if args.format == "tsv" else ","

    if args.output:
        df.to_csv(args.output, sep=sep, index=False)
        logging.info(f"Exported {len(samples)} samples to {args.output}")
    else:
        df.to_csv(sys.stdout, sep=sep, index=False)

    project.close()
