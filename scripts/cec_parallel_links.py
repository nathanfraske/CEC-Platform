"""Source-connectivity ownership of populated two-link bypass groups."""
from itertools import combinations
import re


def is_zero_link(value):
    """Only exact zero-resistance values; never parse a prefix of a value."""
    return bool(re.fullmatch(r"\s*0+(?:\.0+)?\s*(?:r|[Ωω]|ohms?)?\s*",
                             str(value or ""), flags=re.I))


def source_dnp(properties):
    """KiCad netlist exports DNP as either a bare property or a true flag."""
    for key, value in (properties or {}).items():
        if str(key).lower() in {"dnp", "__dnp__"}:
            normalized = "" if value is None else str(value).strip().lower()
            if value is True or normalized in {"", "yes", "true", "1"}:
                return True
    return False


def derive(pin_nets, link_refs, *, max_pairs=4096):
    """Find unique four-terminal owners whose two windings are bypassed.

    The caller supplies only source-populated zero-resistance links. Each
    link must have two physical pins on two distinct nets; two links must
    cover the four distinct one-pin nets of one device. A second possible
    owner is an explicit ambiguity, never a closest-package tie-break.
    No reference, part number, net spelling or placement coordinates qualify
    the relationship. The optional device stays physically present.
    """
    links = {ref: dict(pin_nets[ref]) for ref in sorted(set(link_refs))
             if ref in pin_nets and len(pin_nets[ref]) == 2
             and all(pin_nets[ref].values())
             and len(set(pin_nets[ref].values())) == 2}
    if len(links) * (len(links) - 1) // 2 > max_pairs:
        raise ValueError("parallel-link discovery pair budget exceeded")
    owners = {ref: {net: pin for pin, net in pins.items()}
              for ref, pins in pin_nets.items()
              if ref not in links and len(pins) == 4
              and all(pins.values()) and len(set(pins.values())) == 4}
    groups, ambiguous = [], []
    for a, b in combinations(links, 2):
        nets = set(links[a].values()) | set(links[b].values())
        if len(nets) != 4:
            continue
        matches = sorted(ref for ref, pins in owners.items() if set(pins) == nets)
        if len(matches) > 1:
            ambiguous.append({"refs": [a, b], "owners": matches,
                              "reason": "parallel_link_owner_ambiguous"})
        elif len(matches) == 1:
            owner = matches[0]
            groups.append({"owner_ref": owner, "members": [{
                "ref": ref, "pins": [{"follower_pin": pin,
                    "owner_pin": owners[owner][net], "net": net}
                    for pin, net in sorted(links[ref].items())]}
                for ref in (a, b)]})
    # A link appearing in two otherwise unique groups still lacks ownership.
    repeated = {ref for ref in links if sum(
        ref in {m["ref"] for m in group["members"]} for group in groups) > 1}
    if repeated:
        ambiguous.append({"refs": sorted(repeated),
                          "reason": "parallel_link_group_ambiguous"})
        groups = [group for group in groups
                  if not repeated.intersection(m["ref"] for m in group["members"])]
    return groups, ambiguous
