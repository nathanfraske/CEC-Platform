"""Prove custom rules loaded; CLI exit zero is not evidence of rule validity.

KiCad 10.0.5 catches InitEngine's PARSE_ERROR in LoadBoard, then its DRC job
continues with implicit rules. Probe the exact producer before tests, without
changing the board, rules, severities, factory limits, or native engine. The
caller binds the verified official/cap-only producer and complete source family.
Stripped/unobserved engines, timeouts, and rule compilation exceptions refuse.
"""
import hashlib
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

MAX_RULE_BYTES=1024*1024
MAX_PROBE_BYTES=256*1024
MAX_TOKENS=32768


def _tokens(text):
    if type(text) is not str or len(text.encode('utf-8'))>MAX_RULE_BYTES:
        raise ValueError('bounded_custom_rule_text_required')
    result=[];i=0;depth=0
    while i<len(text):
        c=text[i]
        if c.isspace():i+=1;continue
        if c=='#':
            end=text.find('\n',i);i=len(text) if end<0 else end+1;continue
        start=i
        if c in '()':
            depth+=1 if c=='(' else -1
            if not 0<=depth<=256:raise ValueError('custom_rule_parenthesis_bound')
            i+=1;kind=c;value=c
        elif c=='"':
            i+=1
            while i<len(text):
                if text[i]=='\\':i+=2;continue
                if text[i]=='"':break
                i+=1
            if i>=len(text):raise ValueError('unterminated_custom_rule_string')
            value=text[start+1:i];kind='string';i+=1
        else:
            while i<len(text) and not text[i].isspace() and text[i] not in '()#"':i+=1
            if i==start:raise ValueError('unknown_custom_rule_token')
            value=text[start:i];kind='atom'
        result.append((kind,value,start,i))
        if len(result)>MAX_TOKENS:raise ValueError('custom_rule_token_bound')
    if depth:raise ValueError('unclosed_custom_rule_parenthesis')
    return result


def _decode(value):
    escapes={'a':'\a','b':'\b','f':'\f','n':'\n','r':'\r','t':'\t','v':'\v','"':'"','\\':'\\'}
    out=[];i=0
    while i<len(value):
        if value[i]!='\\':out.append(value[i]);i+=1;continue
        i+=1
        if i>=len(value) or value[i] not in escapes:
            raise ValueError('unsupported_condition_string_escape')
        out.append(escapes[value[i]]);i+=1
    return ''.join(out)


def _condition(value):
    """Change whitespace only outside expression literals, never inside nets."""
    text=_decode(value);out=[];quote=None;escaped=False;space=False
    for c in text:
        if quote:
            if c in '\r\n':raise ValueError('newline_in_condition_literal_not_repairable')
            out.append(c)
            if escaped:escaped=False
            elif c=='\\':escaped=True
            elif c==quote:quote=None
        elif c in "'\"":
            if space and out:out.append(' ')
            space=False;quote=c;out.append(c)
        elif c in ' \t\n\r\f\v':space=True
        else:
            if space and out:out.append(' ')
            space=False;out.append(c)
    if quote or escaped:raise ValueError('unterminated_condition_literal')
    return ''.join(out)


def normalize_conditions(text):
    """Return a formatting-only proposal, with a token/literal preservation seal.

    This is not native parser validation and never grants admission. Only
    multiline condition strings are rewritten; other bytes remain unchanged.
    """
    tokens=_tokens(text);conditions=set()
    for i,(kind,value,start,end) in enumerate(tokens):
        if kind=='atom' and value=='condition':
            if i<1 or tokens[i-1][0]!='(' or i+2>=len(tokens) or tokens[i+1][0]!='string' or tokens[i+2][0]!=')':
                raise ValueError('bounded_quoted_condition_form_required')
            conditions.add(i+1)
    semantic=[];edits=[]
    for i,(kind,value,start,end) in enumerate(tokens):
        if i in conditions:
            normalized=_condition(value);semantic.append((kind,normalized))
            if '\n' in value or '\r' in value:
                encoded=normalized.replace('\\','\\\\').replace('"','\\"')
                edits.append((start,end,'"'+encoded+'"'))
        else:
            if kind=='string' and ('\n' in value or '\r' in value):
                raise ValueError('multiline_noncondition_string_not_repairable')
            semantic.append((kind,value))
    import json
    digest=hashlib.sha256(json.dumps(semantic,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
    output=text
    for start,end,value in reversed(edits):output=output[:start]+value+output[end:]
    if edits:
        received=normalize_conditions(output)
        if received['changed_conditions'] or received['semantic_sha256']!=digest:
            raise ValueError('condition_tokens_or_literals_changed')
    return dict(text=output,changed_conditions=len(edits),condition_count=len(conditions),
        semantic_sha256=digest,formatting_only=True,native_parser_validity_proved=False)


PROBE_COMMANDS='''set pagination off
set confirm off
set print thread-events off
set breakpoint pending on
break 'DRC_ENGINE::InitEngine(wxFileName const&)'
commands
  silent
  printf "CEC_NATIVE_RULE_ENGINE_INIT\\n"
  continue
end
break 'DRC_ENGINE::loadRules(wxFileName const&)'
commands
  silent
  printf "CEC_NATIVE_RULE_FILE_LOAD\\n"
  continue
end
catch throw
commands
  silent
  printf "CEC_NATIVE_THROW\\n"
  bt 12
  printf "CEC_NATIVE_THROW_END\\n"
  continue
end
break 'DRC_ENGINE::RunTests'
commands
  silent
  printf "CEC_NATIVE_RULES_REACHED_TESTS\\n"
  info sharedlibrary _pcbnew
  quit
end
run
'''


def assess_probe(output,*,engine,returncode=0):
    """Fail closed on missing/ambiguous milestones or an exception during init."""
    if type(output) is not str or len(output.encode())>MAX_PROBE_BYTES:
        raise ValueError('bounded_native_rule_probe_output_required')
    markers=re.findall(r'^CEC_NATIVE_(RULE_ENGINE_INIT|RULE_FILE_LOAD|RULES_REACHED_TESTS|THROW|THROW_END)$',output,re.M)
    if returncode or any(markers.count(m)!=1 for m in ('RULE_ENGINE_INIT','RULE_FILE_LOAD','RULES_REACHED_TESTS')):
        raise ValueError('native_rule_load_not_completely_observed')
    start=markers.index('RULE_ENGINE_INIT');load=markers.index('RULE_FILE_LOAD');end=markers.index('RULES_REACHED_TESTS')
    if not start<load<end:raise ValueError('native_rule_load_milestones_out_of_order')
    if 'THROW' in markers[start:end] or 'THROW_END' in markers[start:end]:
        raise ValueError('native_rule_initialization_threw_silent_fallback_forbidden')
    after=output.split('CEC_NATIVE_RULES_REACHED_TESTS\n',1)[-1]
    if not any(line.strip().endswith(str(engine)) and re.search(r'\bYes\b',line) for line in after.splitlines()):
        raise ValueError('verified_native_rule_engine_not_observed')
    if markers.count('THROW')!=markers.count('THROW_END'):
        raise ValueError('native_rule_exception_inventory_incomplete')
    return dict(ok=True,complete=True,custom_rules_loaded_and_compiled=True,
        native_rules_fallback=False,native_tests_started=False,source_modified=False,
        stopped_before_tests=True,release_authority=False)


def probe(command,*,env,engine,timeout_s=10.):
    """Read-only rule-loader observation using the caller's exact verified CLI."""
    import math
    if type(timeout_s) not in (int,float) or not math.isfinite(timeout_s) or not 0<timeout_s<=10:
        raise ValueError('native_rule_probe_ten_second_deadline_required')
    debugger=shutil.which('gdb')
    if not debugger:raise ValueError('native_rule_loader_observer_unavailable')
    started=time.monotonic()
    with tempfile.TemporaryDirectory(prefix='cec-native-rules-') as directory:
        script=Path(directory)/'rules.gdb';script.write_text(PROBE_COMMANDS)
        with tempfile.TemporaryFile() as stdout,tempfile.TemporaryFile() as stderr:
            process=subprocess.Popen([debugger,'--batch','-q','-nx','-x',str(script),'--args',*command],
                env=env,stdout=stdout,stderr=stderr,start_new_session=True)
            try:process.wait(timeout=timeout_s)
            except BaseException:
                import os,signal
                os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=1);raise
            stdout.seek(0);stderr.seek(0)
            raw=stdout.read(MAX_PROBE_BYTES+1);err=stderr.read(MAX_PROBE_BYTES+1)
            if len(raw)>MAX_PROBE_BYTES or len(err)>MAX_PROBE_BYTES:
                raise ValueError('native_rule_probe_output_bound')
            output=raw.decode(errors='replace');error=err.decode(errors='replace')
    result=assess_probe(output,engine=engine,returncode=process.returncode)
    result.update(probe_elapsed_s=round(time.monotonic()-started,6),
        observer=str(Path(debugger).resolve()),observer_sha256=hashlib.sha256(Path(debugger).resolve().read_bytes()).hexdigest(),
        observer_commands_sha256=hashlib.sha256(PROBE_COMMANDS.encode()).hexdigest(),
        observation_sha256=hashlib.sha256(raw+err).hexdigest(),producer_stderr=error)
    return result
