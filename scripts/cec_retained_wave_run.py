"""Launch one bounded WSL job with terminal identity retained for its callback.

No polling, scheduler or automatic restart. RemainAfterExit keeps even a very
short successful invocation inspectable until its completed unit is stopped.
The caller attaches the existing exact-invocation bridge using launch.json.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess


def command(unit, repo, log, argv, *, runtime_s=540, memory_gib=8):
    if not re.fullmatch(r'[A-Za-z0-9_.@:-]+\.service', unit):
        raise ValueError('an exact service unit name is required')
    if (type(runtime_s) is not int or not 10 <= runtime_s <= 43200
            or type(memory_gib) is not int or not 1 <= memory_gib <= 128
            or not argv or any(not isinstance(arg,str) or not arg for arg in argv)):
        raise ValueError('bounded resource limits and a nonempty argv are required')
    return ['systemd-run','--user','--unit='+unit,
        '--property=RemainAfterExit=yes', '--property=RuntimeMaxSec='+str(runtime_s),
        '--property=MemoryMax='+str(memory_gib)+'G','--property=TimeoutStopSec=10',
        '--property=KillMode=control-group','--property=StandardOutput=append:'+str(log),
        '--property=StandardError=append:'+str(log),'--working-directory='+str(repo),
        '--',*argv]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--unit',required=True)
    parser.add_argument('--output-directory',required=True)
    parser.add_argument('--runtime-s',type=int,default=540)
    parser.add_argument('--memory-gib',type=int,default=8)
    parser.add_argument('command',nargs=argparse.REMAINDER)
    args=parser.parse_args()
    repo=Path(__file__).resolve().parents[1]
    output=Path(args.output_directory).resolve()
    if not output.is_relative_to(repo/'build') or output==repo/'build':
        parser.error('a new job directory beneath this repository build/ is required')
    argv=args.command[1:] if args.command[:1]==['--'] else args.command
    launch=command(args.unit,repo,output/'job.log',argv,
                   runtime_s=args.runtime_s,memory_gib=args.memory_gib)
    output.mkdir(parents=True,exist_ok=False)
    evidence=dict(unit=args.unit,command=launch,retain_after_exit=True,
                  output_directory=str(output),status='launching')
    def save():
        temporary=output/'launch.tmp'
        temporary.write_text(json.dumps(evidence,indent=2)+'\n')
        temporary.replace(output/'launch.json')
    save()
    try:
        subprocess.run(launch,check=True,capture_output=True,text=True,timeout=10)
        invocation=subprocess.run(['systemctl','--user','show',args.unit,
            '--property=InvocationID','--value'],check=True,capture_output=True,
            text=True,timeout=10).stdout.strip()
        if not re.fullmatch(r'[0-9a-f]{32}',invocation):
            raise RuntimeError('launched service did not retain an exact invocation ID')
        evidence.update(status='launched',invocation=invocation)
    except Exception as exc:
        evidence.update(status='launch_requires_review',error=str(exc)[:2000])
        save()
        raise
    save()
    print(json.dumps({k:v for k,v in evidence.items() if k!='command'}),flush=True)


if __name__=='__main__':
    main()
