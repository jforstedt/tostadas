import argparse
import logging
import sys


def setup_logging(log_file=None, level=logging.INFO):
    handlers = [logging.StreamHandler()]
    if log_file:
        handlers.append(logging.FileHandler(log_file, mode="a"))
    logging.basicConfig(
        level=level,
        format="[%(levelname)s] %(message)s",
        handlers=handlers,
    )


def build_parser():
    parser = argparse.ArgumentParser(
        prog="tostadas-submit",
        description="Standalone NCBI submission CLI for TOSTADAS",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # --- init ---
    init_p = subparsers.add_parser("init", help="Initialize a submission project")
    init_p.add_argument("--dir", default=".", help="Project directory to create (default: current dir)")
    init_p.add_argument("--config", default=None, help="Path to existing submission_config.yaml to import")

    # --- prepare ---
    prep_p = subparsers.add_parser("prepare", help="Generate submission files from annotation output")
    prep_p.add_argument("--project-dir", default=".", help="Project directory")
    prep_p.add_argument("--metadata", required=True, help="Path to metadata file (TSV or Excel)")
    prep_p.add_argument("--fasta-dir", default=None, help="Directory containing per-sample FASTA files")
    prep_p.add_argument("--gff-dir", default=None, help="Directory containing per-sample GFF/TBL files")
    prep_p.add_argument("--fastq-dir", default=None, help="Directory containing FASTQ files (for SRA)")
    prep_p.add_argument("--databases", nargs="+", required=True,
                        choices=["biosample", "sra", "genbank"],
                        help="Databases to prepare submissions for")
    prep_p.add_argument("--species", required=True,
                        choices=["sars", "flu", "bacteria", "eukaryote", "virus", "rsv", "mpxv", "mev"],
                        help="Organism type")
    prep_p.add_argument("--mol-type", default="genomic", help="Molecule type for table2asn")
    prep_p.add_argument("--strip-pub-block", action="store_true", help="Remove pub citation block from .sqn")
    prep_p.add_argument("--wastewater", action="store_true", help="Use wastewater metadata columns")
    prep_p.add_argument("--batch-size", type=int, default=50, help="Samples per batch")

    # --- submit ---
    sub_p = subparsers.add_parser("submit", help="Upload submission files to NCBI")
    sub_p.add_argument("--project-dir", default=".", help="Project directory")
    sub_p.add_argument("--databases", nargs="+", default=None,
                       choices=["biosample", "sra", "genbank"],
                       help="Databases to submit (default: all pending)")
    sub_p.add_argument("--test", action="store_true", help="Upload to NCBI test server")
    sub_p.add_argument("--dry-run", action="store_true", help="Print actions without connecting")
    sub_p.add_argument("--send-email", action="store_true", help="Email GenBank .sqn files")

    # --- status ---
    stat_p = subparsers.add_parser("status", help="Check submission status and fetch accessions")
    stat_p.add_argument("--project-dir", default=".", help="Project directory")
    stat_p.add_argument("--databases", nargs="+", default=None,
                        choices=["biosample", "sra", "genbank"])
    stat_p.add_argument("--timeout", type=int, default=120, help="Max seconds to poll for reports")

    # --- update ---
    upd_p = subparsers.add_parser("update", help="Update BioSample submissions with new metadata")
    upd_p.add_argument("--project-dir", default=".", help="Project directory")
    upd_p.add_argument("--metadata", required=True, help="Updated metadata TSV")
    upd_p.add_argument("--dry-run", action="store_true")

    # --- export ---
    exp_p = subparsers.add_parser("export", help="Export submission records")
    exp_p.add_argument("--project-dir", default=".", help="Project directory")
    exp_p.add_argument("--output", default=None, help="Output file path (default: stdout)")
    exp_p.add_argument("--format", choices=["tsv", "csv"], default="tsv")

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    setup_logging(level=logging.INFO)

    if args.command == "init":
        from tostadas_submit.project import cmd_init
        cmd_init(args)
    elif args.command == "prepare":
        from tostadas_submit.prepare import cmd_prepare
        cmd_prepare(args)
    elif args.command == "submit":
        from tostadas_submit.submit import cmd_submit
        cmd_submit(args)
    elif args.command == "status":
        from tostadas_submit.status import cmd_status
        cmd_status(args)
    elif args.command == "update":
        from tostadas_submit.update import cmd_update
        cmd_update(args)
    elif args.command == "export":
        from tostadas_submit.export import cmd_export
        cmd_export(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
