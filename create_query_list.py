import argparse
import logging
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd
from rdkit import Chem
from rdkit.Chem import inchi as rdinchi


def inchikey_from_inchi(inchi: str) -> str:
    """Convert InChI to InChIKey using RDKit; return empty string on error."""
    if not inchi:
        return ""
    try:
        mol = Chem.MolFromInchi(inchi)
        if mol is None:
            return ""
        return rdinchi.MolToInchiKey(mol) or ""
    except Exception:
        return ""


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate query list (accession|inchi|inchikey) from files.")
    parser.add_argument("directory", type=Path, help="Root directory containing files")
    parser.add_argument(
        "--output", "-o", type=Path, default=Path("results/query_list.tsv"), help="Target TSV file"
    )
    args = parser.parse_args()


    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.info('\n\n--> Starting create_query_list.py ...\n\n')
    directory: Path = args.directory.expanduser().resolve()
    output: Path = args.output

    # Find files excluding hidden paths
    files = [p for p in directory.rglob("MSBNK-*.txt") if not any(part.startswith(".") for part in p.parts)]
    logging.info("Processing directory: %s", directory)
    logging.info("Total files found: %d", len(files))

    cache: Dict[str, str] = {}
    rows: List[Tuple[str, str, str]] = []

    for fp in files:
        accession = None
        inchi = None
        skip = False
        try:
            with fp.open("r", encoding="utf-8", errors="ignore") as fh:
                for raw in fh:
                    line = raw.strip()
                    if line.startswith("ACCESSION:"):
                        accession = line.split(":", 1)[1].strip()
                    elif line.startswith("CH$LINK:") and "ChemOnt" in line:
                        skip = True
                        break
                    elif line.startswith("CH$IUPAC:"):
                        inchi = line.split(":", 1)[1].strip()
        except Exception as e:
            logging.debug("Error reading %s: %s", fp, e)
            continue

        if skip:
            continue
        if accession and inchi and inchi.startswith("InChI="):
            if inchi not in cache:
                cache[inchi] = inchikey_from_inchi(inchi)
            rows.append((accession, inchi, cache[inchi]))

    logging.info("Total accessions without ChemOnt classification: %d", len(rows))

    df = pd.DataFrame(rows, columns=["accession", "inchi", "inchikey"])

    output.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output, index=False, header=False, sep="|", encoding="utf-8")
    logging.info("Query list saved to %s", output)


if __name__ == "__main__":
    main()
