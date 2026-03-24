"""
run_all.py
Orchestrates the full pipeline:
  1. Fetch SPC GeoJSON data for days 1-8
  2. Generate PNG maps
  3. Generate interactive HTML maps
  4. Write manifest.json
"""

import os
import sys

# Allow running from repo root
sys.path.insert(0, os.path.dirname(__file__))

from fetch_outlooks import fetch_all, write_manifest
from generate_png   import generate_all as gen_pngs
from generate_html  import generate_all as gen_html


def main():
    output_root = sys.argv[1] if len(sys.argv) > 1 else "output"
    os.makedirs(output_root, exist_ok=True)

    print("=" * 60)
    print("Step 1/4  Fetching SPC outlook GeoJSON …")
    print("=" * 60)
    results = fetch_all(output_root)

    print()
    print("=" * 60)
    print("Step 2/4  Generating PNG maps …")
    print("=" * 60)
    gen_pngs(output_root)

    print()
    print("=" * 60)
    print("Step 3/4  Generating interactive HTML maps …")
    print("=" * 60)
    gen_html(output_root)

    print()
    print("=" * 60)
    print("Step 4/4  Writing manifest.json …")
    print("=" * 60)
    write_manifest(results, output_root)

    print()
    print("All done.")


if __name__ == "__main__":
    main()
