"""Phase 16 controlled molecule expansion command."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT/"src"))
from generation import MoleculeExpansionEngine


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root",type=Path,default=PROJECT)
    parser.add_argument("--stage",choices=["prepare","vina","finalize","all"],default="all")
    parser.add_argument("--workers",type=int,default=8)
    args=parser.parse_args()
    if not 1 <= args.workers <= 12: raise SystemExit("workers must be 1-12")
    engine=MoleculeExpansionEngine(args.project_root); result={}
    if args.stage in {"prepare","all"}: result["prepare"]=engine.prepare()
    if args.stage in {"vina","all"}: result["vina"]=engine.vina(args.workers)
    if args.stage in {"finalize","all"}: result["finalize"]=engine.finalize()
    print(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False))
    return 0


if __name__=="__main__": raise SystemExit(main())
