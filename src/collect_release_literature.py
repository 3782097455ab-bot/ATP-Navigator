"""Archive the five requested primary papers as JATS XML/text with provenance.

Full text is local-only under the existing ignored papers directory. Public
metadata, licensing text and source hashes are registered separately.
"""
import argparse
import json
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from workspace.state import write_json,file_hash,now

PAPERS={
    'PMC12509006':'10.1021/acsomega.5c06380',
    'PMC12091843':'10.1002/cmdc.202400952',
    'PMC10714390':'10.1021/acsinfecdis.3c00317',
    'PMC10789121':'10.1021/acsmedchemlett.3c00480',
    'PMC9386795':'10.1021/acsomega.2c03127',
}


def collect(project):
    project=Path(project)
    folder=project/'data/literature/papers/atp_release_v1'
    folder.mkdir(parents=True,exist_ok=True)
    records=[]
    for pmc,doi in PAPERS.items():
        path=folder/(pmc+'.xml')
        url=f'https://www.ebi.ac.uk/europepmc/webservices/rest/{pmc}/fullTextXML'
        row={'pmcid':pmc,'doi':doi,'source_url':f'https://pmc.ncbi.nlm.nih.gov/articles/{pmc}/',
             'download_url':url,'retrieved_at':now(),'status':'not_downloaded'}
        try:
            if not path.exists():
                request=urllib.request.Request(url,headers={'User-Agent':'ATP-Navigator-research-archive/1.0'})
                with urllib.request.urlopen(request,timeout=35) as response:
                    content=response.read(20_000_001)
                if len(content)>20_000_000:
                    raise ValueError('Unexpected response size')
                tree=ET.fromstring(content)
                article_ids={e.attrib.get('pub-id-type'):e.text for e in tree.findall('.//article-id')}
                if article_ids.get('doi','').lower()!=doi.lower():
                    raise ValueError('Article identity mismatch')
                path.write_bytes(content)
            tree=ET.parse(path).getroot()
            text_path=path.with_suffix('.txt')
            if not text_path.exists() or text_path.stat().st_size==0:
                body=tree.find('.//body')
                if body is None:
                    raise ValueError('Article body unavailable')
                text_path.write_text('\n'.join(' '.join(e.itertext()) for e in body),encoding='utf-8')
            row.update(status='archived',xml_path=str(path.relative_to(project)),text_path=str(text_path.relative_to(project)),
                       sha256=file_hash(path),title=' '.join(tree.find('.//article-title').itertext()),
                       license_text=' '.join(e for node in tree.findall('.//license') for e in node.itertext()),
                       table_count=len(tree.findall('.//table-wrap')),
                       supplement_links=[node.attrib.get('{http://www.w3.org/1999/xlink}href','') for node in tree.findall('.//supplementary-material')],
                       redistribution='full_text_kept_local_review_license_before_redistribution')
        except Exception as error:
            row.update(status='download_failed',error=type(error).__name__+': '+str(error))
        records.append(row)
        print(json.dumps({'pmcid':pmc,'status':row['status']},ensure_ascii=False),flush=True)
    output=project/'data/literature/release_v1_papers.json'
    if output.exists():
        output=output.with_name('release_v1_papers_'+now().replace(':','').replace('.','')+'.json')
    write_json(output,records)
    return records


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--project-root',type=Path,default=Path(__file__).resolve().parents[1])
    args=parser.parse_args()
    collect(args.project_root)
