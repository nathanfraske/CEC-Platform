"""Explicit invocation-local reuse of source-only suite audits.

PCB intake, assembly validation, native DRC and route gates are never cached.
The owner must discard this session after the suite invocation. Content, file
inventory, mode and implementation identity are checked on every access.
"""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path


class SuiteSourceAuditCache:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self._entries = {}
        self.hits = 0
        self.misses = 0
        self._epoch = None

    def _signature(self, mode):
        import cec_beta_manifest
        import cec_beta_electrical_audit as electrical
        import cec_sch_gates
        import cec_full_pipeline as pipeline
        import cec_synth_pipeline as synth
        paths = set((self.root / 'scripts').rglob('*.py'))
        # Discover through the exact same audit domain, not a caller-selected
        # subset: cross-board consistency checks must retain every peer.
        projects = electrical.discover_projects(str(self.root / 'beta'))
        domain = []
        for name, directory, schematic in projects:
            cfg = synth.Config.load(name)
            paths.update(pipeline._source_files(cfg, cfg.pcb or cfg.sch))
            inventory = cec_sch_gates.inventory(schematic)
            _digest, sources = electrical._source_digest(schematic, inventory)
            paths.update(self.root / source for source in sources)
            domain.append((name, str(Path(directory).resolve()), str(Path(schematic).resolve()),
                           str(cfg.dir), str(cfg.sch), str(cfg.pcb), cfg.params, cfg.is_draft))
        # Symbol/feature registries are source authority, not code constants.
        paths.update((self.root / 'lib').rglob('*.kicad_sym'))
        paths.update((self.root / 'lib').rglob('*.json'))
        import cec_toolchain
        paths.add(Path(cec_toolchain.require_kicad_cli('suite source audit identity')))
        rows = [(str(path.resolve()), hashlib.sha256(path.read_bytes()).hexdigest())
                for path in sorted(paths)]
        environment = sorted((key, value) for key, value in os.environ.items()
                             if key.startswith(('CEC_', 'KICAD')) or key == 'PATH')
        payload = [str(self.root), domain, cec_beta_manifest.PROJECTS, rows, environment]
        return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()

    def evidence(self):
        if self._epoch is not None and self._signature('generalization') != self._epoch:
            raise ValueError('suite source/code epoch changed before finalization')
        return {'kind': 'invocation-local-source-only-audit-reuse',
                'source_code_config_tool_epoch': self._epoch,
                'hits': self.hits, 'misses': self.misses,
                'native_pcb_intake_or_route_receiving_cached': False}

    def get(self, mode, producer):
        if mode not in ('electrical-current-beta', 'generalization'):
            raise ValueError('unsupported source-only suite audit mode')
        before = self._signature(mode)
        if self._epoch is not None and before != self._epoch:
            raise ValueError('suite source/code epoch changed; fresh invocation required')
        self._epoch = before
        entry = self._entries.get(mode)
        if entry is not None and entry[0] == before:
            self.hits += 1
            result = deepcopy(entry[1])
        else:
            self.misses += 1
            result = producer()
        if self._signature(mode) != before:
            self._entries.pop(mode, None)
            raise ValueError('suite source/code changed during audit cache access')
        self._entries[mode] = (before, deepcopy(result))
        return deepcopy(result)
