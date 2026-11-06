"""Native saved-copper before/after; no refill, geometry synthesis or overlays."""
from pathlib import Path
import argparse
import subprocess
import json
import hashlib
import cec_suite_inspection as view


def main(args):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.image as mpimg
    args.output.mkdir(parents=True,exist_ok=True)
    fig,axes=plt.subplots(1,2,figsize=(12,7),facecolor='#101c22')
    hashes=[]
    for ax,(label,board) in zip(axes,[('Before',args.source),('After',args.candidate)]):
        sha=hashlib.sha256(board.read_bytes()).hexdigest();hashes.append(sha)
        svg=args.output/(label.lower()+'.svg');png=svg.with_suffix('.png')
        subprocess.run(view.plot_command(board,svg,[args.layer,'Edge.Cuts']),check=True,timeout=9.5,capture_output=True)
        view.reframe_svg(svg,args.bounds)
        subprocess.run(['rsvg-convert','-w','1100','-b','#101c22','-o',str(png),str(svg)],check=True,timeout=9.5)
        ax.imshow(mpimg.imread(png));ax.set_axis_off()
        ax.set_title(f'{label} | {args.layer} | {sha[:12]}',color='white',fontsize=13)
        assert hashlib.sha256(board.read_bytes()).hexdigest()==sha
    fig.suptitle(args.title,color='white',fontsize=15)
    fig.tight_layout();fig.savefig(args.output/'before-after.png',dpi=150,facecolor=fig.get_facecolor())
    view.write_json(args.output/'sources.json',dict(source=str(args.source),candidate=str(args.candidate),
        source_sha256=hashes[0],candidate_sha256=hashes[1],layer=args.layer,bounds=args.bounds,
        native_saved_copper_only=True,refilled=False))
    print(args.output/'before-after.png')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True)
    p.add_argument('--candidate',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--layer',required=True);p.add_argument('--bounds',type=float,nargs=4,required=True)
    p.add_argument('--title',required=True);main(p.parse_args())
