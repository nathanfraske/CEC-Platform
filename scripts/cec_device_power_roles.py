"""Manufacturer electrical pin roles, separate from bypass-cap requirements.

Only the listed package families are covered. Unknown packages/pins remain
unresolved; this catalog neither changes a schematic nor rates its copper.
Sources are pin-function tables, not a board/net/reference heuristic.
"""
import math
import re


# Espressif ESP32-C6-MINI-1 / MINI-1U v1.5, table3-1 and figure11-1.
# GPIO peripheral selection is Source intent, not a manufacturer direction
# or load rating. Only the exact selected MINI-1-N4 package is covered here.
_C6_GROUND = {'1', '2', '11', '14'} | {str(n) for n in range(36, 54)}
_C6_NC = {'4', '7', '21', '32', '33', '34', '35'}
_C6_FUNCTIONS = {
    **{n: 'GND' for n in _C6_GROUND}, **{n: 'NC' for n in _C6_NC},
    '3': '3V3', '8': 'EN', '5': 'IO2', '6': 'IO3', '9': 'IO4', '10': 'IO5',
    '12': 'IO0', '13': 'IO1', '15': 'IO6', '16': 'IO7', '17': 'IO12',
    '18': 'IO13', '19': 'IO14', '20': 'IO15', '22': 'IO8', '23': 'IO9',
    '24': 'IO18', '25': 'IO19', '26': 'IO20', '27': 'IO21', '28': 'IO22',
    '29': 'IO23', '30': 'RXD0', '31': 'TXD0'}
_C6_ROLES = {str(n): ('ground' if str(n) in _C6_GROUND else
    'no_connect' if str(n) in _C6_NC else 'power_input' if n == 3 else
    'signal_input' if n == 8 else 'signal_io') for n in range(1, 54)}


CATALOG = (
    (r'^ESP32-C6-MINI-1-N4(?:\s|$)', 'ESP32-C6-MINI-1',
     'https://documentation.espressif.com/esp32-c6-mini-1_mini-1u_datasheet_en.html',
     _C6_ROLES),
    (r'^TLV7011DBV[RT](?:\s|$)', 'TLV7011 DBV',
     'https://www.ti.com/lit/ds/symlink/tlv7011.pdf',
     {'1': 'signal_output', '2': 'power_return', '3': 'signal_input',
      '4': 'signal_input', '5': 'power_input'}),
    (r'^INA181A[1-4]I?DBV[A-Z]*(?:\s|$)', 'INA181 DBV',
     'https://www.ti.com/lit/ds/symlink/ina181.pdf',
     {'1': 'signal_output', '2': 'ground', '3': 'measurement',
      '4': 'measurement', '5': 'reference', '6': 'power_input'}),
    (r'^INA181A[1-4]I?DCK[A-Z]*(?:\s|$)', 'INA181 DCK',
     'https://www.ti.com/lit/ds/symlink/ina181.pdf',
     {'1': 'reference', '2': 'ground', '3': 'power_input',
      '4': 'measurement', '5': 'measurement', '6': 'signal_output'}),
    (r'^INA240A[1-4]D[A-Z]*(?:\s|$)', 'INA240 D',
     'https://www.ti.com/lit/ds/symlink/ina240.pdf',
     {'1': 'measurement', '2': 'ground', '3': 'reference',
      '4': 'no_connect', '5': 'signal_output', '6': 'power_input',
      '7': 'reference', '8': 'measurement'}),
    (r'^INA240A[1-4]PW[A-Z]*(?:\s|$)', 'INA240 PW',
     'https://www.ti.com/lit/ds/symlink/ina240.pdf',
     {'1': 'no_connect', '2': 'measurement', '3': 'measurement',
      '4': 'ground', '5': 'power_input', '6': 'reference',
      '7': 'reference', '8': 'signal_output'}),
    # NXP orderable suffixes do not change the /3 SO8 pin table. Keep
    # package/functional variants distinct; unknown suffixes are not aliases.
    (r'^TJA1051T/3(?:(?:,|-)(?:112|118)|/(?:1J|2Z)|/CM,118)?(?:\s|$)', 'TJA1051T/3 SO8',
     'https://www.nxp.com/docs/en/data-sheet/TJA1051.pdf',
     {'1': 'signal_input', '2': 'ground', '3': 'power_input',
      '4': 'signal_output', '5': 'power_input', '6': 'signal_io',
      '7': 'signal_io', '8': 'control'}),
    (r'^TPS2121(?:RUX[A-Z]*|$)', 'TPS2121 RUX',
     'https://www.ti.com/lit/ds/symlink/tps2121.pdf',
     {'1': 'power_output', '2': 'power_input', '3': 'control',
      '4': 'control', '5': 'control', '6': 'control', '7': 'power_input',
      '8': 'power_output', '9': 'signal_output', '10': 'control',
      '11': 'control', '12': 'ground'}),
    (r'^INA238(?:[A-Z0-9]*)(?:\s|$)', 'INA238 DGS',
     'https://www.ti.com/lit/ds/symlink/ina238.pdf',
     {'1': 'address', '2': 'address', '3': 'signal_output',
      '4': 'signal_io', '5': 'signal_input', '6': 'power_input',
      '7': 'ground', '8': 'measurement', '9': 'measurement', '10': 'measurement'}),
    (r'^LP5907MF(?:X)?(?:-|\s|$)', 'LP5907 SOT-23 DBV',
     'https://www.ti.com/lit/ds/symlink/lp5907.pdf',
     {'1': 'power_input', '2': 'ground', '3': 'control',
      '4': 'no_connect', '5': 'power_output'}),
    (r'^TLV62569DBV[A-Z]*(?:\s|$)', 'TLV62569 DBV',
     'https://www.ti.com/lit/ds/symlink/tlv62569.pdf',
     {'1': 'control', '2': 'ground', '3': 'switch',
      '4': 'power_input', '5': 'feedback'}),
    (r'^TLV75533PDRV[A-Z]*(?:\s|$)', 'TLV75533P DRV',
     'https://www.ti.com/lit/ds/symlink/tlv755p.pdf',
     {'1': 'power_output', '2': 'no_connect', '3': 'ground',
      '4': 'control', '5': 'no_connect', '6': 'power_input', '7': 'ground'}),
    (r'^TLV75533PDBV[A-Z]*(?:\s|$)', 'TLV75533P DBV',
     'https://www.ti.com/lit/ds/symlink/tlv755p.pdf',
     {'1': 'power_input', '2': 'ground', '3': 'control',
      '4': 'no_connect', '5': 'power_output'}),
)


_PACKAGE_FOOTPRINTS = {
    'ESP32-C6-MINI-1': r'(?:^|:)ESP32-C6-MINI-1$',
    'TLV7011 DBV': r'(?:^|:)SOT-23-5(?:_|$)',
    'INA181 DBV': r'(?:^|:)SOT-23-6(?:_|$)',
    'INA181 DCK': r'(?:^|:)(?:SC-70-6|SOT-363)(?:_|$)',
    'INA240 D': r'(?:^|:)SOIC-8(?:_|$)',
    'INA240 PW': r'(?:^|:)TSSOP-8(?:_|$)',
    'TJA1051T/3 SO8': r'(?:^|:)SOIC-8(?:_|$)',
    'INA238 DGS': r'(?:^|:)VSSOP-10_3x3mm_P0\.5mm(?:_|$)',
}


def contract(value, *, mpn=None, footprint=None):
    """Select actual package metadata, refusing contradictory identities.

    A displayed family alone cannot choose INA181 DBV vs DCK or INA240 D
    vs PW. Exact selected MPN wins; absent it, an unambiguous selected
    package footprint may qualify that family's pin table. No geometry,
    reference designator or board-specific inference is used.
    """
    selected = str(mpn or value or '').strip().upper()
    displayed = str(value or '').strip().upper()
    families = ('INA181', 'INA240', 'TJA1051', 'TLV7011')
    family = next((f for f in families if displayed.startswith(f)), None)
    if mpn and family and not selected.startswith(family):
        raise ValueError('manufacturer_mpn_displayed_family_mismatch')
    matches = [(name, source, pins) for pattern, name, source, pins in CATALOG
        if re.match(pattern, selected)]
    if (not matches and not mpn and footprint and family in ('INA181', 'INA240')
            and re.fullmatch(family + r'(?:A[1-4])?', selected)):
        matches = [(name, source, pins) for _, name, source, pins in CATALOG
            if name.startswith(family+' ') and re.search(
                _PACKAGE_FOOTPRINTS[name], str(footprint), re.I)]
    if not matches:
        return None
    if len(matches) != 1:
        raise ValueError('ambiguous_manufacturer_power_pin_contract')
    name, source, pins = matches[0]
    if name == 'ESP32-C6-MINI-1' and displayed not in ('ESP32-C6-MINI-1', selected):
        raise ValueError('manufacturer_mpn_displayed_family_mismatch')
    if (footprint and name in _PACKAGE_FOOTPRINTS
            and not re.search(_PACKAGE_FOOTPRINTS[name], str(footprint), re.I)):
        raise ValueError('manufacturer_selected_package_footprint_mismatch')
    result = dict(device_package=name, source=source, pins=dict(pins),
        common_domains=[dict(name='OUT', pins=['1', '8'])]
            if name == 'TPS2121 RUX' else [])
    if name == 'ESP32-C6-MINI-1':
        result.update(revision='1.5', pin_table='3-1', land_pattern='11-1',
            selected_mpn='ESP32-C6-MINI-1-N4',
            physical_ground_land_counts={'49': 9},
            native_pin_functions=dict(_C6_FUNCTIONS),
            pin_roles_do_not_supply_current_or_routing_authority=True)
    return result


def footprint_contract(fp):
    from cec_footprint_fields import footprint_properties
    properties = footprint_properties(fp)
    result = contract(fp.GetValue(), mpn=properties.get('MPN'),
                    footprint=getattr(fp, 'GetFPIDAsString', lambda: '')())
    if result and result['device_package'] == 'ESP32-C6-MINI-1':
        if (not re.search(_PACKAGE_FOOTPRINTS[result['device_package']],
                          str(getattr(fp, 'GetFPIDAsString', lambda: '')()), re.I)
                or str(properties.get('MPN') or '').strip().upper() != 'ESP32-C6-MINI-1-N4'
                or ' '.join(str(properties.get('Manufacturer') or '').upper().split()) != 'ESPRESSIF SYSTEMS'):
            return None
    return result


def physical_pinmap(fp, model, *, board_hint=None, timeout_s=8.):
    """Validate a full manufacturer map without collapsing physical lands.

    Ordinary packages retain the unique-number rule. The explicitly covered
    C6 land pattern has exactly nine Ground49 lands, all separate UUIDs and
    native contacts. This grants no package-internal PCB graph edge, Source
    intent, copper cut, current budget, or automatic pose permission.
    """
    if type(timeout_s)not in(int,float)or not math.isfinite(timeout_s)or not 0<timeout_s<=10:
        raise ValueError('bounded_manufacturer_physical_pinmap_lease_required')
    pads = list(fp.Pads())
    if (not model or model != footprint_contract(fp) or not 1 <= len(pads) <= 256
            or {p.GetNumber() for p in pads} != set(model['pins'])):
        raise ValueError('complete_manufacturer_physical_pinmap_required')
    by_pin = {number: tuple(p for p in pads if p.GetNumber() == number)
              for number in model['pins']}
    split = model.get('physical_ground_land_counts')
    if split is None:
        if any(len(items) != 1 for items in by_pin.values()):
            raise ValueError('unaliased_manufacturer_physical_pinmap_required')
        return by_pin
    import pcbnew
    if (model['device_package'] != 'ESP32-C6-MINI-1' or split != {'49': 9}
            or model['common_domains'] or len(pads) != 61
            or fp.GetDuplicatePadNumbersAreJumpers()
            or len({p.m_Uuid.AsString() for p in pads}) != len(pads)
            or fp.GetLayer() not in (pcbnew.F_Cu, pcbnew.B_Cu)
            or any(len(items) != split.get(number, 1) for number, items in by_pin.items())
            or any(p.HasHole() or p.GetAttribute() != pcbnew.PAD_ATTRIB_SMD
                or p.GetShape() != pcbnew.PAD_SHAPE_RECT
                or min(tuple(p.GetSize())) <= 0 or tuple(p.GetOffset()) != (0, 0)
                or tuple(p.GetLayerSet().CuStack()) != (fp.GetLayer(),) for p in pads)):
        raise ValueError('exact_manufacturer_split_ground_land_pattern_required')
    blank_native_metadata=all(not p.GetPinFunction() and not p.GetPinType() for p in pads)
    if blank_native_metadata:
        # Legacy saved PCBs often omit both fields. Absence is not role
        # evidence: freshly export the explicit current Source, check all
        # 53 names/types and all61 physical native net identities instead.
        import cec_source_device_pinmap as source_pinmap
        source_pinmap.prove(fp,model,board_hint=board_hint,timeout_s=timeout_s)
    for number, items in by_pin.items():
        role = model['pins'][number]
        expected_type = ('power_in' if role in ('ground', 'power_input') else
            'no_connect' if role == 'no_connect' else 'input' if number == '8' else 'bidirectional')
        if not blank_native_metadata and any(p.GetPinFunction() != model['native_pin_functions'][number]
                or p.GetPinType() != expected_type for p in items):
            raise ValueError('complete_native_manufacturer_pin_name_and_type_required')
        if any((p.GetNetname() == 'GND') != (role == 'ground')
                or p.GetNetCode() <= 0 for p in items):
            raise ValueError('native_manufacturer_ground_partition_required')
    return by_pin


def passive_steering_protector_contract(fp):
    """Exact selected shunt-protector map, NOT a supply/load or pose model.

    Independently reviewed UMW Nov2024 section4 and ST Doc11265 Rev5
    figure1: I/O1=1/6, I/O2=3/4, Ground2, clamp-reference5. Do not
    alias a similarly named but unregistered supplier/package or
    promote a clamp into power_input/nonload. The complete Source compiler
    must separately re-export the current schematic and own every port.
    """
    import pcbnew
    from cec_footprint_fields import footprint_properties
    fields=footprint_properties(fp)
    selected=(str(fields.get('Manufacturer','')).strip().upper(),
              str(fields.get('LCSC','')).strip().upper())
    evidence={
        ('UMW','C2687116'):dict(device_package='UMW USBLC6-2SC6 SOT23-6',
            source='https://www.umw-ic.com/static/pdf/b2c190f0a00a742e1ffd3347f22dc112.pdf',
            selected_datasheet_sha256='973ea7520f3cd820e2c9326fcf3ee3ca5239cff491d6f42de057573942dcdf83',
            selected_datasheet_path='lib/datasheets/UMW_USBLC6-2SC6_C2687116.pdf',
            revision='Nov2024',page=1,section='4',
            selected_manufacturer='UMW',selected_lcsc='C2687116'),
        ('STMICROELECTRONICS','C7519'):dict(device_package='ST USBLC6-2SC6 SOT23-6',
            source='https://www.st.com/resource/en/datasheet/usblc6-2.pdf',
            selected_datasheet_sha256='8ba7ab4ec1781b7f6052f5999a2304bd611c0ed2b5e8f36ffa5092552932a42e',
            selected_datasheet_path='lib/datasheets/ST_USBLC6-2SC6_C7519.pdf',
            reviewed_binary_source='https://datasheet.lcsc.com/datasheet/pdf/0d3a2ab954b34651a0695e7ccf534db0.pdf?productCode=C7519',
            revision='Doc ID 11265 Rev 5 October 2011',page=1,section='Figure 1',
            selected_manufacturer='STMicroelectronics',selected_lcsc='C7519'),
    }.get(selected)
    if (fp.IsDNP() or str(fp.GetValue()).strip().upper()!='USBLC6-2SC6'
            or str(fields.get('MPN','')).strip().upper()!='USBLC6-2SC6'
            or evidence is None
            or not re.fullmatch(r'[^:]+:SOT-23-6',fp.GetFPIDAsString())):
        return None
    pads=list(fp.Pads());face=fp.GetLayer()
    if (face not in (pcbnew.F_Cu,pcbnew.B_Cu) or len(pads)!=6
            or {p.GetNumber()for p in pads}!={str(n)for n in range(1,7)}
            or any(p.HasHole() or p.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD
                or tuple(p.GetLayerSet().CuStack())!=(face,)
                or p.GetNetCode()<=0 or p.GetPinType()not in ('','passive') for p in pads)):
        return None
    by_pin={p.GetNumber():p for p in pads}
    functions={'1':'I/O1','6':'I/O1','3':'I/O2','4':'I/O2','2':'GND','5':'VBUS'}
    if (any(p.GetPinFunction() not in ('',functions[n]) for n,p in by_pin.items())
            or by_pin['2'].GetNetname()!='GND'
            or by_pin['1'].GetNetCode()!=by_pin['6'].GetNetCode()
            or by_pin['3'].GetNetCode()!=by_pin['4'].GetNetCode()
            or len({by_pin[n].GetNetCode()for n in ('1','3','2','5')})!=4):
        return None
    return dict(**evidence, selected_mpn='USBLC6-2SC6',
        pins={'1':'signal_io','6':'signal_io','3':'signal_io','4':'signal_io',
            '2':'ground','5':'clamp_reference'},
        io_banks=[['1','6'],['3','4']],ground_pin='2',clamp_reference_pin='5',
        ground_net=str(by_pin['2'].GetNetname()),clamp_net=str(by_pin['5'].GetNetname()),
        source_pin_functions=functions,source_pin_type='passive',
        bypass_owner=False,load_budget_declared=False,current_authority=False,
        internal_conduction_is_not_native_PCB_connection=True,
        pose_or_pair_reconstruction_authority=False,release_authority=False)


def optional_ground_attachment_contract(fp,pin):
    """Manufacturer-permitted reserved metal, NOT a functional return pin.

    TI SBOS662C table 6-1 permits INA240 PW1/D4 to connect to Ground or
    float. Preserve the primary no_connect role: it is never a bypass return,
    a mandatory ground obligation, a current path through the package, or a
    general permission to ground another device's reserved/DNC terminal.
    """
    if fp.IsDNP():return None
    model=footprint_contract(fp)
    if (not model or {'INA240 D':'4','INA240 PW':'1'}.get(model['device_package'])!=str(pin)
            or model['pins'].get(str(pin))!='no_connect'):return None
    return dict(scope='manufacturer_optional_external_ground_attachment',pin=str(pin),
        device_package=model['device_package'],source=model['source'],revision='SBOS662C',
        table='6-1',permitted_external_nets=['GND'],may_float=True,
        functional_ground_return=False,current_authority=False,release_authority=False)


def functional_ground_attachment_contract(fp, pin):
    """Selected C6 module functional Ground, not an optional/NC or load role.

    Espressif MINI-1/1U datasheet v1.5 table 3-1 names Ground pins 1, 2,
    11, 14 and 36--53. Keep this independent of the power catalog: it adds
    no supply budget, bypass-owner assignment or barrel-current authority.
    The caller must still recompile actual source symbol/net membership.
    """
    from cec_footprint_fields import footprint_properties
    import pcbnew
    if fp.IsDNP() or type(pin) is not str:
        return None
    selected = str(footprint_properties(fp).get('MPN') or '').strip().upper()
    if re.fullmatch(r'INA238AIDGS[RT]',selected):
        # Existing registered TI DGS pin table, not a new load model. Address
        # pins tied to Ground remain address pins; ONLY physical pin7 is GND.
        pads=list(fp.Pads());model=footprint_contract(fp)
        if (pin!='7' or str(fp.GetValue()).strip().upper()not in('INA238',selected)
                or not re.search(r'(?:^|:)VSSOP-10_3x3mm_P0\.5mm$',fp.GetFPIDAsString())
                or len(pads)!=10 or {p.GetNumber()for p in pads}!={str(n)for n in range(1,11)}
                or any(p.HasHole()or p.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD
                    or tuple(p.GetLayerSet().CuStack())!=(fp.GetLayer(),)for p in pads)
                or not model or model['device_package']!='INA238 DGS'
                or model['pins'].get(pin)!='ground'
                or fp.FindPadByNumber(pin).GetNetname()!='GND'
                or fp.FindPadByNumber(pin).GetNetCode()<=0
                or fp.FindPadByNumber(pin).GetPinType()not in('','power_in')
                or fp.FindPadByNumber(pin).GetPinFunction()not in('','GND')):return None
        return dict(scope='manufacturer_functional_ground_pin',role='ground',pin=pin,
            device_package=model['device_package'],selected_mpn=selected,source=model['source'],
            functional_ground_return=True,optional_ground=False,may_float=False,
            bypass_owner=False,current_authority=False,release_authority=False)
    match = re.fullmatch(r'ESP32-C6-MINI-(1U?)-N([48])', selected)
    if not match:
        return None
    package = 'ESP32-C6-MINI-' + match[1]
    if (str(fp.GetValue()).strip().upper() not in (package, selected)
            or not re.search(r'(?:^|:)' + package + r'$', fp.GetFPIDAsString(), re.I)):
        return None
    ground = {'1', '2', '11', '14'} | {str(n) for n in range(36, 54)}
    if pin not in ground:
        return None
    pads = list(fp.Pads())
    counts = {str(n): sum(p.GetNumber() == str(n) for p in pads) for n in range(1, 54)}
    # Split EP49 lands remain one logical terminal, never arbitrary aliases.
    if ({p.GetNumber() for p in pads} != set(counts)
            or any(n != 1 for p, n in counts.items() if p != '49')
            or not 1 <= counts['49'] <= 16
            or any(p.GetAttribute() != pcbnew.PAD_ATTRIB_SMD or p.HasHole()
                   or tuple(p.GetLayerSet().CuStack()) != (fp.GetLayer(),) for p in pads)
            or any((p.GetNetname() == 'GND') != (p.GetNumber() in ground) for p in pads)):
        return None
    return dict(scope='manufacturer_functional_ground_pin', role='ground', pin=pin,
        device_package=package, selected_mpn=selected,
        source='https://documentation.espressif.com/esp32-c6-mini-1_mini-1u_datasheet_en.html',
        revision='1.5', table='3-1', functional_ground_return=True,
        optional_ground=False, may_float=False, bypass_owner=False,
        current_authority=False, release_authority=False)


def control_shunt_input_contract(fp,pin):
    """Exact module EN witness, not a power or bypass-owner contract.

    Espressif S3 MINI datasheet v1.7 table3-1 and section11.2. The
    established S2-MINI land-pattern alias has the same65 numbered lands;
    this role check does not qualify its geometry, RF or assembly process.
    No typical load, RC value or reset timing is inferred here.
    """
    from cec_footprint_fields import footprint_properties
    if str(pin)=='23':return boot_mode_strap_shunt_contract(fp,pin)
    if str(pin)=='8':return c6_enable_shunt_contract(fp,pin)
    if fp.IsDNP() or str(pin)!='45':return None
    mpn=str(footprint_properties(fp).get('MPN','')).upper()
    match=re.fullmatch(r'ESP32-S3-MINI-(1U?)-(N8|N4R2)',mpn)
    if not match or str(fp.GetValue()).upper()!=mpn:return None
    pattern=r'(?:^|:)ESP32-S[23]-MINI-'+match[1]+r'(?:_NoAntKeepout)?$'
    if not re.search(pattern,fp.GetFPIDAsString(),re.I):return None
    pads=list(fp.Pads())
    counts={str(i):sum(p.GetNumber()==str(i) for p in pads) for i in range(1,66)}
    # KiCad may split the same EPAD61 into multiple solderable lands. That
    # is one electrical terminal, not eight extra manufacturer pins. Do not
    # tolerate duplication of EN or another signal to get the same result.
    if ({p.GetNumber() for p in pads}!={str(i)for i in range(1,66)}
            or any(n!=1 for p,n in counts.items() if p!='61')
            or not 1<=counts['61']<=16
            or counts['61']>1 and any(p.GetNetname()!='GND' for p in pads if p.GetNumber()=='61')):
        return None
    return dict(scope='manufacturer_control_shunt_input',role='enable_reset_input',pin='45',
        device_package='ESP32-S3-MINI-'+match[1],
        source='https://documentation.espressif.com/esp32-s3-mini-1_mini-1u_datasheet_en.pdf',
        revision='1.7',table='3-1',application_section='11.2',
        functional_ground_return=False,bypass_owner=False,current_authority=False,
        reset_timing_qualified=False,release_authority=False)


def boot_mode_strap_shunt_contract(fp,pin):
    """Selected C6 physical GPIO9 boot strap, never EN or post-boot mode.

    Espressif C6 MINI v1.5 table3-1 and4-3. A canonical source must separately
    prove the external cap/pull-up/button topology. Net spelling grants none
    of this role; GPIO0 (physical12) is deliberately not an alias.
    """
    import pcbnew
    from cec_footprint_fields import footprint_properties
    selected=str(footprint_properties(fp).get('MPN')or'').strip().upper()
    if (str(pin)!='23' or selected!='ESP32-C6-MINI-1-N4'
            or fp.GetValue().strip().upper()!=selected
            or not re.search(r'(?:^|:)ESP32-C6-MINI-1$',fp.GetFPIDAsString(),re.I)
            or not functional_ground_attachment_contract(fp,'1')):return None
    pad=fp.FindPadByNumber('23');power=fp.FindPadByNumber('3')
    if (pad.GetNetCode()<=0 or power.GetNetCode()<=0 or pad.GetNetname()=='GND'
            or pad.GetNetCode()==power.GetNetCode()
            or pad.GetPinType()not in('','bidirectional')
            or pad.GetPinFunction()not in('','IO9','GPIO9')):return None
    return dict(scope='manufacturer_control_shunt_input',role='boot_mode_strap_input',
        pin='23',function='IO9',device_package='ESP32-C6-MINI-1',selected_mpn=selected,
        source='https://documentation.espressif.com/esp32-c6-mini-1_mini-1u_datasheet_en.pdf',
        revision='1.5',table='3-1',boot_table='4-3',boot_gpio='GPIO9',
        source_pin_type='bidirectional',functional_ground_return=False,bypass_owner=False,
        current_authority=False,reset_timing_qualified=False,boot_timing_qualified=False,
        postboot_gpio_mode_assumed=False,release_authority=False)


def c6_enable_shunt_contract(fp,pin):
    """Selected physical EN8, never the module GPIO0/BOOT net spelling.

    Reuse the exact native C6 package/MPN/53-logical-land proof, not the
    bootstrap electrical function. The source compiler must separately prove
    EN input/name and the complete cap/pull-up/button topology.
    """
    from cec_footprint_fields import footprint_properties
    selected=str(footprint_properties(fp).get('MPN')or'').strip().upper()
    if (str(pin)!='8' or selected!='ESP32-C6-MINI-1-N4'
            or fp.GetValue().strip().upper()!=selected
            or not re.search(r'(?:^|:)ESP32-C6-MINI-1$',fp.GetFPIDAsString(),re.I)
            or not functional_ground_attachment_contract(fp,'1')):return None
    pad=fp.FindPadByNumber('8');power=fp.FindPadByNumber('3')
    if (pad.GetNetCode()<=0 or power.GetNetCode()<=0 or pad.GetNetname()=='GND'
            or pad.GetNetCode()==power.GetNetCode() or pad.GetPinType()not in('','input')
            or pad.GetPinFunction()not in('','EN')):return None
    return dict(scope='manufacturer_control_shunt_input',role='enable_reset_input',
        pin='8',function='EN',device_package='ESP32-C6-MINI-1',selected_mpn=selected,
        source='https://documentation.espressif.com/esp32-c6-mini-1_mini-1u_datasheet_en.pdf',
        revision='1.5',table='3-1',source_pin_type='input',
        requires_complete_pullup_button_topology=True,functional_ground_return=False,
        bypass_owner=False,current_authority=False,reset_timing_qualified=False,
        release_authority=False)


def source_return_pins(value, pin_nets, *, return_rail='GND', explicit_pin=None,
                       mpn=None, footprint=None):
    """Source-geometry counterpart of the native device-return selector.

    A grounded control/reference/NC is not a decoupling return for a covered
    package. Unknown devices retain explicitly unqualified net-only geometry;
    contradictory selected packages still raise rather than becoming unknown.
    Rail-to-rail contracts keep their explicit non-ground endpoint unchanged.
    """
    model = contract(value, mpn=mpn, footprint=footprint)
    pins = [str(pin) for pin, net in pin_nets.items() if net == return_rail]
    if return_rail == 'GND' and model is not None:
        pins = [pin for pin in pins if model['pins'].get(pin)
                in ('ground', 'power_return')]
    if explicit_pin is not None:
        pins = [pin for pin in pins if pin == str(explicit_pin)]
    return dict(pins=sorted(set(pins)),
                scope=('manufacturer-pin-functions' if model and return_rail == 'GND'
                       else 'explicit-rail-to-rail-contract' if return_rail != 'GND'
                       else 'native-net-only-unresolved'),
                device_package=model['device_package'] if model else None,
                source=model['source'] if model else None,
                manufacturer_ground_role_qualified=(model is not None)
                    if return_rail == 'GND' else None,
                current_or_fabrication_qualification=False)


def resistive_voltage_monitor_contract(fp, pin):
    """Pin-function/absolute-voltage bounds for a resistor-fed monitor.

    TI SLVSEA3F tables 6 and 7.1. This is NOT a new rail voltage or load
    budget: the conservative differential uses both endpoint stress bounds.
    Operation/transients/OVP and resistor qualification remain separate gates.
    CP2, ILIM, SS, outputs, supplies and unknown devices are not in this scope.
    """
    if fp.IsDNP():return None
    model=footprint_contract(fp)
    if not model or model['device_package']!='TPS2121 RUX':return None
    if not re.search(r'(?:^|:)RUX0012A$',fp.GetFPIDAsString()):return None
    selected={'6':('PR1','7'),'5':('OV1','7'),'4':('OV2','2')}.get(str(pin))
    if selected is None:return None
    name,power_pin=selected
    if model['pins'].get(str(pin))!='control' or model['pins'].get(power_pin)!='power_input':return None
    return dict(function=name,pin=str(pin),associated_power_pin=power_pin,
        source=model['source'],revision='SLVSEA3F',tables=['6','7.1'],
        power_voltage_bounds_v=[-.3,24.],monitor_voltage_bounds_v=[-.3,6.],
        operating_or_transient_qualification=False,release_authority=False)


def resistive_sensing_endpoint_contract(fp, pin):
    """Positive resistor-fed input roles; GPIO high-Z mode is NOT assumed.

    Voltage envelopes are conditional endpoint bounds, not supply protection
    or operating/transient qualification. A series resistor bounds aggregate
    current even if an ADC-capable GPIO drives within its voltage envelope.
    Unknown pins, package variants and power/output functions fail closed.
    """
    from cec_footprint_fields import footprint_properties
    import pcbnew
    if fp.IsDNP():return None
    legacy=resistive_voltage_monitor_contract(fp,pin)
    if legacy:
        return dict(legacy,source_rail_must_equal_associated_power=True,
                    endpoint_role='power_mux_voltage_monitor')
    props=footprint_properties(fp)
    selected=str(props.get('MPN') or '').strip().upper()
    displayed=str(fp.GetValue()).strip().upper()
    pin=str(pin);pads=list(fp.Pads())
    def unique(number):
        hits=[p for p in pads if str(p.GetNumber())==number]
        return hits[0] if len(hits)==1 else None
    if re.fullmatch(r'TLV7011DBV[RT]',selected):
        if (displayed not in ('TLV7011','TLV7011DBVR','TLV7011DBVT',selected)
                or not re.search(r'(?:^|:)SOT-23-5(?:_|$)',fp.GetFPIDAsString())
                or len(pads)!=5 or {p.GetNumber() for p in pads}!={'1','2','3','4','5'}
                or any(p.HasHole() or p.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD for p in pads)
                or pin not in ('3','4')):return None
        function={'3':'IN+','4':'IN-'}[pin]
        supply=unique('5');ground=unique('2');grounds=[ground]
        input_bounds=[-.3,6.];power_bounds=[0.,6.]
        package='TLV7011 DBV';revision='SLVSDM5F';tables=['Pin Functions','6.1']
        source='https://www.ti.com/lit/ds/symlink/tlv7011.pdf'
        role='analog_comparator_input'
    elif re.fullmatch(r'ESP32-S3-WROOM-1U?-N(?:4|8|16)(?:R(?:2|8))?',selected):
        package=selected.split('-N')[0]
        if (displayed not in (package,selected)
                or not re.search(r'(?:^|:)'+re.escape(package)+r'(?:_NoAntKeepout)?$',fp.GetFPIDAsString())
                or len(pads)>128
                or {p.GetNumber() for p in pads if p.GetNumber()}!={str(n) for n in range(1,42)}):return None
        # ADC-capable module lands from table 3-1. Dedicated USB pins
        # 13/14 remain pair-owned even though they also have ADC functions.
        functions={'4':'IO4','5':'IO5','6':'IO6','7':'IO7','8':'IO15',
            '9':'IO16','10':'IO17','11':'IO18','12':'IO8','15':'IO3',
            '17':'IO9','18':'IO10','19':'IO11','20':'IO12','21':'IO13',
            '22':'IO14','38':'IO2','39':'IO1'}
        function=functions.get(pin)
        if function is None or unique(pin) is None:return None
        supply=unique('2');grounds=[unique('1'),unique('40')]
        grounds += [p for p in pads if p.GetNumber()=='41']
        if any(unique(n) is None for n in ('1','2','40')):return None
        input_bounds=[-.3,3.9];power_bounds=[-.3,3.6]
        revision='v1.8';tables=['3-1','6-1','6-3']
        source='https://documentation.espressif.com/esp32-s3-wroom-1_wroom-1u_datasheet_en.pdf'
        role='adc_capable_gpio_voltage_envelope_not_application_mode'
    else:return None
    endpoint=unique(pin)
    if (supply is None or supply.GetNetCode()<=0 or supply.GetNetname()=='GND'
            or any(p is None or p.GetNetname()!='GND' for p in grounds)
            or endpoint is None or endpoint.GetNetCode() in (0,supply.GetNetCode())
            or any(p.HasHole() or p.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD for p in (endpoint,supply))):return None
    return dict(function=function,pin=pin,associated_power_pin=str(supply.GetNumber()),
        device_package=package,selected_mpn=selected,source=source,revision=revision,tables=tables,
        power_voltage_bounds_v=power_bounds,monitor_voltage_bounds_v=input_bounds,
        source_rail_must_equal_associated_power=False,endpoint_role=role,
        gpio_application_mode_or_high_impedance_assumed=False,
        voltage_bounds_are_conditional_not_a_clamp_or_protection=True,
        operating_or_transient_qualification=False,release_authority=False)


def resistive_source_voltage_contract(fp, pin):
    """Actual selected same-net power land and its manufacturer stress bounds.

    This witnesses a conditional voltage envelope only. It does not claim
    that the device regulates/clamps the rail, or change its current budget.
    """
    from cec_footprint_fields import footprint_properties
    import pcbnew
    if fp.IsDNP():return None
    selected=str(footprint_properties(fp).get('MPN') or '').strip().upper()
    pads=list(fp.Pads());pin=str(pin)
    if (not re.fullmatch(r'TPS2121RUX[RT]',selected)
            or str(fp.GetValue()).strip().upper() not in ('TPS2121',selected)
            or not re.search(r'(?:^|:)RUX0012A$',fp.GetFPIDAsString())
            or len(pads)!=12 or {p.GetNumber() for p in pads}!={str(n) for n in range(1,13)}
            or any(p.HasHole() or p.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD for p in pads)
            or pin not in ('1','2','7','8')
            or fp.FindPadByNumber('12').GetNetname()!='GND'):return None
    port=fp.FindPadByNumber(pin)
    if port.GetNetCode()<=0 or port.GetNetname()=='GND':return None
    return dict(device_package='TPS2121 RUX',selected_mpn=selected,pin=pin,
        role='power_output' if pin in ('1','8') else 'power_input',
        source='https://www.ti.com/lit/ds/symlink/tps2121.pdf',revision='SLVSEA3F',tables=['6','7.1'],
        voltage_bounds_v=[-.3,24.],voltage_bound_not_a_physical_clamp=True,
        current_budget_modified=False,operating_or_transient_qualification=False,release_authority=False)


def tied_enable_contract(fp):
    """Known EN/IN topology, never a typical-current-as-maximum rating.

    TI SBVS320D tables 4-1/5.5 and section 6.3.2. The WSON package's
    enable is pin 4, not IN pin 6. A supply-tied enable is a control leaf;
    proving that topology does not qualify barrel ampacity or the rail load.
    Cover only the selected package positively witnessed below.
    """
    from cec_footprint_fields import footprint_properties
    props=footprint_properties(fp)
    selected=str(props.get('MPN') or fp.GetValue()).strip().upper()
    if not re.fullmatch(r'TLV75533PDRV[A-Z]*',selected):return None
    displayed=str(fp.GetValue()).strip().upper()
    if displayed not in ('TLV75533P',selected):return None
    if not re.search(r'(?:^|:)WSON-6-1EP_2x2mm_P0\.65mm_EP1x1\.6mm$',
                     fp.GetFPIDAsString(),re.I):return None
    model=footprint_contract(fp)
    if (not model or model['device_package']!='TLV75533P DRV'
            or model['pins'].get('4')!='control' or model['pins'].get('6')!='power_input'):
        return None
    return dict(device_package=model['device_package'],enable_pin='4',input_pin='6',
        source=model['source'],source_revision='SBVS320D',source_table='4-1',
        current_max_a=None,branch_current_qualified=False,
        typical_current_is_not_maximum_authority=True,release_authority=False)


def _s3_mini_scalar_pin(fp, pin):
    """Selected 65-land MINI GPIO table, not a WROOM pad-number alias.

    Espressif S3 MINI v1.7 table 3-1: module lands 5..22 expose GPIO1..18.
    Dedicated USB lands 23/24 stay pair-owned. The existing S2-MINI land
    pattern alias is accepted ONLY with the positively selected S3 MPN and
    complete native package/ground/supply identity. No ADC mode, input
    impedance, voltage envelope, current or RF qualification is inferred.
    """
    import pcbnew
    from cec_footprint_fields import footprint_properties
    pin=str(pin)
    if pin not in {str(n) for n in range(5,23)}:return None
    package=control_shunt_input_contract(fp,'45')
    if not package:return None
    pads=list(fp.Pads());ground={'1','2','42','43'}|{str(n)for n in range(46,66)}
    if (any(p.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD or p.HasHole()
            or tuple(p.GetLayerSet().CuStack())!=(fp.GetLayer(),) for p in pads)
            or any((p.GetNetname()=='GND')!=(p.GetNumber() in ground) for p in pads)):
        return None
    supplies=[p for p in pads if p.GetNumber()=='3']
    endpoints=[p for p in pads if p.GetNumber()==pin]
    if (len(supplies)!=1 or supplies[0].GetNetCode()<=0 or len(endpoints)!=1
            or endpoints[0].GetNetCode()<=0
            or endpoints[0].GetNetCode()==supplies[0].GetNetCode()):return None
    return dict(package=package['device_package'],
        selected_mpn=str(footprint_properties(fp)['MPN']).upper(),
        pin=pin,function='IO'+str(int(pin)-4),associated_power_pin='3',
        source='https://documentation.espressif.com/esp32-s3-mini-1_mini-1u_datasheet_en.html',
        source_table='3-1',source_revision='1.7',adc_capable=True,
        gpio_application_mode_or_high_impedance_assumed=False,
        current_authority=False,voltage_envelope_authority=False,release_authority=False)


def scalar_gpio_pin(fp, pin):
    """Positive package witness, not a guess from a net or pad function.

    ESP32-C6-MINI-1/1U table 3-1, datasheet v1.5. USB-capable GPIO12/13
    stay excluded here: their dedicated pair producer still owns routing.
    This does not declare application mode, current, RF or timing authority.
    """
    from cec_footprint_fields import footprint_properties
    # Reuse the existing complete, selected-package ADC/GPIO pin table. This
    # supplies a physical scalar role only, not an ADC firmware setting,
    # high-impedance assumption, voltage clamp or GPIO current budget.
    selected = str(footprint_properties(fp).get('MPN') or fp.GetValue()).upper()
    if selected.startswith('ESP32-S3-MINI-'):
        return _s3_mini_scalar_pin(fp,pin)
    endpoint=(resistive_sensing_endpoint_contract(fp,str(pin))
        if selected.startswith('ESP32-S3-WROOM-') else None)
    if endpoint and endpoint['endpoint_role']=='adc_capable_gpio_voltage_envelope_not_application_mode':
        return dict(package=endpoint['device_package'],selected_mpn=endpoint['selected_mpn'],
            pin=str(pin),function=endpoint['function'],source=endpoint['source'],source_table='3-1',
            source_revision=endpoint['revision'],associated_power_pin=endpoint['associated_power_pin'],
            gpio_application_mode_or_high_impedance_assumed=False,release_authority=False)
    if not re.fullmatch(r'ESP32-C6-MINI-1U?(?:-N[48](?:-[A-Z0-9]+)?)?', selected):
        return None
    package = 'ESP32-C6-MINI-1U' if selected.startswith('ESP32-C6-MINI-1U') else 'ESP32-C6-MINI-1'
    if str(fp.GetValue()).strip().upper() not in (package, selected):
        return None
    if not re.search(r'(?:^|:)' + package + r'$', fp.GetFPIDAsString(), re.I):
        return None
    pins = {'5': 'IO2', '6': 'IO3', '9': 'IO4', '10': 'IO5',
            '12': 'IO0', '13': 'IO1', '15': 'IO6', '16': 'IO7',
            '19': 'IO14', '20': 'IO15', '22': 'IO8', '23': 'IO9',
            '24': 'IO18', '25': 'IO19', '26': 'IO20', '27': 'IO21',
            '28': 'IO22', '29': 'IO23', '30': 'RXD0', '31': 'TXD0'}
    function = pins.get(str(pin))
    if not function:
        return None
    return dict(package=package, pin=str(pin), function=function,
        source='https://documentation.espressif.com/esp32-c6-mini-1_mini-1u_datasheet_en.html',
        source_table='3-1', release_authority=False)


def scalar_logic_output_pin(fp, pin):
    """Positive selected digital-buffer output, not any IC's OUT spelling.

    This small signal-role witness does not add a supply-load model or relax
    clock, pair, voltage, edge-rate, field or production qualification. The
    exact DBV package and complete five-land footprint must agree with the
    selected manufacturer MPN. Analog/comparator outputs are not aliases.
    """
    from cec_footprint_fields import footprint_properties
    if fp.IsDNP() or str(pin) != '4':
        return None
    props=footprint_properties(fp)
    selected=str(props.get('MPN') or '').strip().upper()
    displayed=str(fp.GetValue()).strip().upper()
    if (not re.fullmatch(r'SN74LVC1G17DBV[RT]',selected)
            or displayed not in ('74LVC1G17','SN74LVC1G17',selected)
            or not re.search(r'(?:^|:)SOT-23-5(?:_|$)',fp.GetFPIDAsString())):
        return None
    pads=list(fp.Pads())
    if len(pads)!=5 or {str(p.GetNumber()) for p in pads} != {'1','2','3','4','5'}:
        return None
    # Require each actual native surface land, not a reference-name or
    # pad-number convention applied to an unrelated drilled footprint.
    import pcbnew
    if any(p.HasHole() or p.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD for p in pads):
        return None
    return dict(package='SN74LVC1G17 DBV',selected_mpn=selected,pin='4',function='Y',
        role='digital_buffer_output',
        source='https://www.ti.com/lit/ds/symlink/sn74lvc1g17.pdf',
        source_table='Pin Functions',release_authority=False,
        electrical_edge_rate_or_voltage_qualification=False)
