"""Bounded, crash-safe placement work checkpoints. Never a release certificate.

The producer owns one store and alternates two slots. A reader follows only
the atomic pointer, after verifying the complete artifact family and sources.
Native repair, source intake, exact copper guards and final admission run again.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import time

ROOT = Path(__file__).resolve().parents[1]
PHASES = {'seed': 0, 'preflight': 1, 'selected': 2, 'craft': 3, 'placement': 4,
          'priority': 5}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def atomic_json(path, data):
    temporary = path.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(data, indent=2, allow_nan=False) + '\n')
    temporary.replace(path)


def source_valid(rows):
    return bool(rows) and all(Path(row['path']).is_file()
                              and sha(row['path']) == row['sha256'] for row in rows)


def read_board(board, *, expected_family=None, check_sources=True):
    """Strict checkpoint certificate validation, independent of nearby journals."""
    if Path(board).is_symlink():
        raise ValueError('checkpoint board cannot be a symlink')
    board = Path(board).resolve()
    path = board.with_suffix('.placement-checkpoint.json')
    data = json.loads(path.read_text())
    if (data.get('schema') != 1 or data.get('kind') != 'unadmitted-placement-work'
            or data.get('routing_admitted') is not False
            or data.get('release_accepted') is not False
            or data.get('source_intake_ok') is not True
            or data.get('phase') not in PHASES
            or Path(data['board']).resolve() != board
            or (expected_family is not None and data.get('family') != expected_family)):
        raise ValueError('invalid placement checkpoint identity or role')
    files = data.get('artifacts') or []
    if (not files or sum(row['name'] == board.name for row in files) != 1
            or len({row['name'] for row in files}) != len(files)):
        raise ValueError('checkpoint lacks its unique board artifact')
    context = data.get('context') or {}
    outline = context.get('outline_mm') or []
    if (not isinstance(context.get('pins'), dict) or len(outline) != 2
            or any(not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0
                   for v in outline)):
        raise ValueError('invalid checkpoint geometric context')
    for row in files:
        artifact = board.parent / row['name']
        if (Path(row['name']).name != row['name'] or artifact.is_symlink()
                or not artifact.is_file() or sha(artifact) != row['sha256']):
            raise ValueError('checkpoint artifact missing or changed: ' + row['name'])
    if data.get('sha256') != sha(board):
        raise ValueError('checkpoint board digest mismatch')
    if check_sources and not source_valid(data.get('sources') or []):
        raise ValueError('checkpoint source authority changed or disappeared')
    return data


def read_current(root, *, expected_family=None, check_sources=True):
    root = Path(root).resolve()
    pointer = json.loads((root / 'current.json').read_text())
    slot = pointer.get('slot')
    if slot not in ('slot-0', 'slot-1'):
        raise ValueError('invalid checkpoint slot')
    board = root / slot / 'board.kicad_pcb'
    if (root / slot).is_symlink() or not board.resolve().is_relative_to(root):
        raise ValueError('checkpoint path escapes store')
    certificate = board.with_suffix('.placement-checkpoint.json')
    if sha(certificate) != pointer.get('certificate_sha256'):
        raise ValueError('checkpoint pointer and certificate disagree')
    data = read_board(board, expected_family=expected_family, check_sources=check_sources)
    return data


class Store:
    """Single coordinator writer; at most two complete artifact families."""
    def __init__(self, root, *, family, sources, max_family_bytes=64 * 1024**2):
        if Path(root).is_symlink():
            raise ValueError('checkpoint store cannot be a symlink')
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        owner = self.root / '.store-owner.json'
        identity = {'schema': 1, 'kind': 'placement-checkpoint-store', 'family': family}
        if owner.exists():
            if owner.is_symlink() or json.loads(owner.read_text()) != identity:
                raise ValueError('checkpoint store ownership mismatch')
        elif any(self.root.iterdir()):
            raise ValueError('refusing to adopt a nonempty unowned checkpoint directory')
        else:
            atomic_json(owner, identity)
        self.family = family
        self.sources = [{'path':str(Path(p).resolve()), 'sha256':sha(p)} for p in sources]
        self.max_family_bytes = max_family_bytes

    def publish(self, source, *, phase, rank, context, copier, validate, observation=None):
        if phase not in PHASES:
            raise ValueError('unknown checkpoint phase')
        rank = list(rank)
        if not rank or any(not isinstance(x, (int,float)) or not math.isfinite(x) for x in rank):
            raise ValueError('checkpoint rank must be finite numeric evidence')
        previous = read_current(self.root, expected_family=self.family) if (self.root/'current.json').exists() else None
        if previous and (PHASES[phase] < PHASES[previous['phase']]
                         or (phase == previous['phase'] and rank >= previous['rank'])):
            return {'published':False, 'reason':'incumbent_not_worse', 'board':previous['board']}
        if not source_valid(self.sources):
            raise ValueError('source changed before checkpoint')
        source = Path(source).resolve()
        if source.stat().st_size > self.max_family_bytes:
            raise ValueError('checkpoint board exceeds bounded storage policy')
        original = sha(source)
        # Validation happens before touching even the inactive slot.
        intake = validate(source)
        if intake.get('ok') is not True:
            raise ValueError('checkpoint source intake refused')
        active = Path(previous['board']).parent.name if previous else 'slot-1'
        slot = self.root / ('slot-1' if active == 'slot-0' else 'slot-0')
        if slot.is_symlink():
            raise ValueError('checkpoint slot cannot be a symlink')
        slot.mkdir(exist_ok=True)
        # Only this store's two flat scratch slots are ever cleared. No
        # recursive deletion, parent traversal or source mutation is used.
        if not slot.resolve().is_relative_to(self.root):
            raise ValueError('checkpoint slot escapes owner')
        if source.is_relative_to(slot):
            raise ValueError('checkpoint source cannot be its inactive scratch slot')
        for old in slot.iterdir():
            if not old.is_file() or old.is_symlink():
                raise ValueError('unexpected entry in owned checkpoint slot')
        for old in slot.iterdir():
            old.unlink()
        destination = slot / 'board.kicad_pcb'
        copied = [Path(p).resolve() for p in copier(source, destination)]
        files = sorted(set([destination] + copied))
        if any(p.parent != slot or p.is_symlink() or not p.is_file() for p in files):
            raise ValueError('checkpoint copier returned invalid artifact family')
        if sum(p.stat().st_size for p in files) > self.max_family_bytes:
            for path in files:
                path.unlink()  # validated inactive owned flat slot only
            raise ValueError('checkpoint family exceeds bounded storage policy')
        if sha(destination) != original or sha(source) != original:
            raise ValueError('board changed during checkpoint copy')
        record = {'schema':1, 'kind':'unadmitted-placement-work', 'family':self.family,
                  'board':str(destination), 'sha256':original, 'phase':phase, 'rank':rank,
                  'context':context, 'observation':observation or {}, 'source_intake_ok':True,
                  'sources':self.sources, 'created_epoch':time.time(),
                  'routing_admitted':False, 'release_accepted':False,
                  'artifacts':[{'name':p.name,'sha256':sha(p),'size':p.stat().st_size} for p in files]}
        certificate = destination.with_suffix('.placement-checkpoint.json')
        atomic_json(certificate, record)
        # Verify a second time after copying, before the atomic pointer flip.
        read_board(destination, expected_family=self.family)
        atomic_json(self.root/'current.json', {'schema':1,'slot':slot.name,
                    'certificate_sha256':sha(certificate)})
        return {'published':True, **record}
