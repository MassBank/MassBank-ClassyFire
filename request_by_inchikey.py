import argparse
import logging
import time
import json
from pathlib import Path
from typing import Dict, List

import pandas as pd
import requests
from pandas.errors import EmptyDataError

url = "http://classyfire.wishartlab.com"


def get_entity_by_inchikey(inchikey):
    r = requests.get(f"{url}/entities/{inchikey}.json", headers={"Content-Type": "application/json"})
    if r.status_code == 200:
        return r.json()
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Query entities by InChIKey and produce mapping files.")
    parser.add_argument("input", type=Path, nargs="?", default=Path("results/query_list.tsv"), help="Input TSV file")
    parser.add_argument("--outdir", "-o", type=Path, default=Path("results"), help="Output directory")
    parser.add_argument("--delay", "-d", type=float, default=5.0, help="Delay between requests in seconds")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    input_tsv = args.input.expanduser().resolve()
    outdir = args.outdir.expanduser().resolve()
    delay = float(args.delay)

    print('\n\n--> Starting request_by_inchikey.py ...\n\n')

    logging.info("Processing input: %s", input_tsv)
    logging.info("Output directory: %s", outdir)
    logging.info("Request delay: %.2f seconds", delay)

    # 1. Read TSV file
    if not input_tsv.exists():
        logging.error("Input file not found: %s", input_tsv)
        return
    if input_tsv.stat().st_size == 0:
        logging.info("Input file is empty: %s", input_tsv)
        outdir.mkdir(parents=True, exist_ok=True)
        mapping_path = outdir / "mapping.json"
        with mapping_path.open("w", encoding="utf-8") as f:
            json.dump({}, f, indent=2, ensure_ascii=False)
        logging.info("Empty mapping saved to %s", mapping_path)
        return
    try:
        df = pd.read_csv(input_tsv, sep="|", header=None, names=["accession", "inchi", "inchikey"], dtype=str)
    except EmptyDataError:
        logging.info("Input file has no parseable rows: %s", input_tsv)
        outdir.mkdir(parents=True, exist_ok=True)
        mapping_path = outdir / "mapping.json"
        with mapping_path.open("w", encoding="utf-8") as f:
            json.dump({}, f, indent=2, ensure_ascii=False)
        logging.info("Empty mapping saved to %s", mapping_path)
        return

    df = df.fillna("")
    if df.empty:
        logging.info("Input table is empty after parsing: %s", input_tsv)
        outdir.mkdir(parents=True, exist_ok=True)
        mapping_path = outdir / "mapping.json"
        with mapping_path.open("w", encoding="utf-8") as f:
            json.dump({}, f, indent=2, ensure_ascii=False)
        logging.info("Empty mapping saved to %s", mapping_path)
        return

    accessions: List[str] = df["accession"].tolist()
    inchikeys: List[str] = df["inchikey"].str.strip().tolist()

    logging.info("Total accessions: %d", len(accessions))
    logging.info("Total InChIKeys: %d", len(inchikeys))

    unique_inchikeys = list(set(x for x in inchikeys if x))
    print(f'Total unique input InChIKeys: {len(unique_inchikeys)}')

    # Ensure output directory exists
    outdir.mkdir(parents=True, exist_ok=True)

    # Query per-inchikey endpoint
    results: Dict[str, dict] = {}
    logging.info("Trying fast /entities/<inchikey> lookups...")
    for ik in unique_inchikeys:
        try:
            entity = get_entity_by_inchikey(ik)
            if entity:
                results[ik] = entity
                logging.info("Found entity for %s", ik)
            else:
                logging.info("Not found (will query): %s", ik)
        except Exception as e:
            logging.warning("Error fetching %s: %s", ik, e)
        time.sleep(delay)

    logging.info("Total results: %d", len(results))

    # Build mapping: accession -> entity
    mapping: Dict[str, dict] = {
        acc: results[ik]
        for acc, ik in zip(accessions, inchikeys)
        if ik and ik in results
    }

    # Save the mapping to a JSON file
    mapping_path = outdir / "mapping.json"
    try:
        with mapping_path.open("w", encoding="utf-8") as f:
            json.dump(mapping, f, indent=2, ensure_ascii=False)
        logging.info("Mapping saved to %s", mapping_path)
    except Exception:
        logging.exception("Failed to write mapping to %s", mapping_path)


if __name__ == "__main__":
    main()