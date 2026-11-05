import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,readFileSync,writeFileSync,rmSync,existsSync} from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {PassThrough} from 'node:stream';
import {EventEmitter} from 'node:events';
import {claimDelivery} from '../scripts/cec_event_delivery.mjs';
import {runBridge,waitForCompletion} from '../scripts/cec_wave_completion_bridge.mjs';
import {callAppTool} from '../scripts/cec_codex_app_events.mjs';

const threadId='01234567-89ab-cdef-0123-456789abcdef';
function setup(t) {
  const outputDir=mkdtempSync(path.join(os.tmpdir(),'cec-event-test-'));
  t.after(()=>rmSync(outputDir,{recursive:true,force:true}));
  return {threadId,outputDir,serverPath:'/adapter.mjs',repo:'/repo',distro:'test',
    unit:'cec-test.service',invocation:'a'.repeat(32),prompt:'Inspect the saved result.'};
}
function state(c) {return JSON.parse(readFileSync(path.join(c.outputDir,'state.json'),'utf8'));}
function event(c,kind='service_completed') {
  return {unit:c.unit,expected_invocation:c.invocation,kind};
}
function options(extra={}) {
  return {env:{CODEX_THREAD_ID:threadId},retryDelay:async()=>{},...extra};
}

for (const status of ['connecting','armed','connection_failed','listener_failed',
                      'transport_failed_before_dispatch',null]) {
  test(`dead pre-dispatch owner can recover: ${status}`,t=>{
    const c=setup(t), first=claimDelivery(c,{pid:10});
    if (status) first.record({status});
    const second=claimDelivery(c,{pid:11,isAlive:()=>false});
    assert.equal(second.attempt,2);
    second.record({status:'connecting'});
    assert.equal(state(c).attempt,2);
    assert.throws(()=>claimDelivery(c,{isAlive:pid=>pid===11}),/still alive/);
  });
}
test('claim identity and legacy evidence must agree',t=>{
  const c=setup(t);
  writeFileSync(path.join(c.outputDir,'claim.json'),JSON.stringify({
    threadId,unit:c.unit,invocation:c.invocation,pid:10}));
  assert.throws(()=>claimDelivery(c,{isAlive:()=>false}),/unknown/);
  writeFileSync(path.join(c.outputDir,'state.json'),JSON.stringify({
    threadId,unit:c.unit,invocation:'b'.repeat(32),status:'armed'}));
  assert.throws(()=>claimDelivery(c,{isAlive:()=>false}),/identity mismatch/);
  writeFileSync(path.join(c.outputDir,'state.json'),JSON.stringify({
    threadId,unit:c.unit,invocation:c.invocation,status:'armed'}));
  const recovered=claimDelivery(c,{pid:11,isAlive:()=>false});
  assert.equal(recovered.attempt,2);
  recovered.record({status:'connecting'});
  assert.throws(()=>claimDelivery({...c,prompt:'Different work'},{isAlive:()=>false}),/identity mismatch/);
});
for (const status of ['dispatch_in_flight','sent','delivery_unknown']) {
  test(`uncertain or completed delivery is never retried: ${status}`,t=>{
    const c=setup(t),claim=claimDelivery(c);
    claim.beginDispatch(event(c)); claim.record({status});
    assert.throws(()=>claimDelivery(c,{isAlive:()=>false}),/already have occurred/);
    assert.throws(()=>claim.record({status:'connecting'}),/cannot return/);
    assert.throws(()=>claim.beginDispatch(event(c)),/EEXIST/);
  });
}
test('exclusive dispatch marker survives lost state and bounded recovery stops',t=>{
  const c=setup(t),first=claimDelivery(c,{pid:10}); first.record({status:'armed'});
  const second=claimDelivery(c,{pid:11,isAlive:()=>false});
  second.record({status:'armed'});
  const third=claimDelivery(c,{pid:12,isAlive:()=>false});
  third.record({status:'armed'});
  assert.throws(()=>claimDelivery(c,{isAlive:()=>false}),/recovery limit/);
  third.beginDispatch(event(c));
  rmSync(path.join(c.outputDir,'attempt-3.state.json'));
  assert.throws(()=>claimDelivery(c,{isAlive:()=>false}),/already have occurred/);
});
test('live first owner cannot be stolen',t=>{
  const c=setup(t); claimDelivery(c).record({status:'armed'});
  assert.throws(()=>claimDelivery(c),/still alive/);
  assert.equal(existsSync(path.join(c.outputDir,'claim-2.json')),false);
});
test('dispatch during owner-death check cannot be recovered from a stale state',t=>{
  const c=setup(t),first=claimDelivery(c,{pid:10});first.record({status:'armed'});
  assert.throws(()=>claimDelivery(c,{isAlive:()=>{
    first.beginDispatch(event(c));return false;
  }}),/already have occurred/);
  assert.equal(existsSync(path.join(c.outputDir,'claim-2.json')),false);
});
test('broken claim is fail-closed',t=>{
  const c=setup(t); writeFileSync(path.join(c.outputDir,'claim.json'),'{');
  assert.throws(()=>claimDelivery(c,{isAlive:()=>false}),SyntaxError);
});

test('listener failure reattaches, pre-dispatch transport failure retries once',async t=>{
  const c=setup(t); let listeners=0,sends=0,actualDispatch=0;
  const result=await runBridge(c,options({
    listen:async()=>{if (++listeners===1) throw Error('listener crashed');return event(c);},
    callTool:async(_s,_t,name,_a,opts)=>{
      if (name==='read_thread') return {};
      if (++sends===1) throw Error('catalog unavailable');
      opts.onDispatch(); actualDispatch++; return {ok:true};
    }}));
  assert.equal(result.status,'sent');assert.equal(listeners,2);
  assert.equal(sends,2);assert.equal(actualDispatch,1);assert.equal(state(c).status,'sent');
});
test('post-dispatch acknowledgement timeout never resends',async t=>{
  const c=setup(t);let sends=0;
  await assert.rejects(runBridge(c,options({listen:async()=>event(c),
    callTool:async(_s,_t,name,_a,opts)=>{
      if(name==='read_thread') return {};
      sends++; opts.onDispatch();throw Error('ack timed out');
    }})),/ack timed out/);
  assert.equal(sends,1);assert.equal(state(c).status,'delivery_unknown');
  assert.throws(()=>claimDelivery(c,{isAlive:()=>false}),/already have occurred/);
});
test('unavailable connection is bounded and does not start listener',async t=>{
  const c=setup(t);let probes=0;
  await assert.rejects(runBridge(c,options({callTool:async()=>{probes++;throw Error('offline');},
    listen:async()=>{throw Error('must not listen');}})),/offline/);
  assert.equal(probes,3);assert.equal(state(c).status,'connection_failed');
  assert.equal(existsSync(path.join(c.outputDir,'attempt-1.dispatch.json')),false);
});
test('unauthorized task identity is refused before claiming',async t=>{
  const c=setup(t);
  await assert.rejects(runBridge(c,{env:{}}),/authorized task identity/);
  assert.equal(existsSync(path.join(c.outputDir,'claim.json')),false);
});

test('listener retry limit is enforced without any send',async t=>{
  const c=setup(t);let listens=0,sends=0;
  await assert.rejects(runBridge(c,options({
    listen:async()=>{listens++;throw Error('listener failed');},
    callTool:async(_s,_t,name)=>{if(name!=='read_thread')sends++;return {};}
  })),/listener failed/);
  assert.equal(listens,3);assert.equal(sends,0);assert.equal(state(c).status,'listener_failed');
});

function fakeChild() {
  const child=new EventEmitter();
  child.stdin=new PassThrough();child.stdout=new PassThrough();child.stderr=new PassThrough();
  child.kills=0;child.kill=()=>{child.kills++;};return child;
}
test('silent listener startup is bounded and cleaned up',async t=>{
  const c=setup(t),child=fakeChild(),claim=claimDelivery(c);
  await assert.rejects(waitForCompletion(c,claim,()=>child,{armTimeoutMs:10}),/did not arm/);
  assert.equal(child.stdin.writableEnded,true);assert.equal(child.kills,1);
  assert.equal(claim.dispatched(),false);
});
test('armed listener waits for an event, not a periodic deadline',async t=>{
  const c=setup(t),child=fakeChild(),claim=claimDelivery(c);
  const pending=waitForCompletion(c,claim,()=>child,{armTimeoutMs:10});
  child.stdout.write(JSON.stringify(event(c,'armed'))+'\n');
  await new Promise(resolve=>setTimeout(resolve,25));
  assert.equal(child.kills,0);
  child.stdout.write(JSON.stringify(event(c))+'\n');
  assert.equal((await pending).kind,'service_completed');
});
for (const kind of ['service_completed','service_failed','unit_unavailable','tracked_unit_removed',
                    'unit_snapshot_unstable']) {
  test(`listener accepts exact ${kind} and closes its owned pipe`,async t=>{
    const c=setup(t),child=fakeChild(),claim=claimDelivery(c);let args;
    const result=waitForCompletion(c,claim,(_exe,a)=>{args=a;return child;});
    child.stdout.write(JSON.stringify(event(c,'armed'))+'\n');
    child.stdout.write(JSON.stringify(event(c,kind))+'\n');
    child.emit('close',0);
    assert.equal((await result).kind,kind);assert.equal(child.kills,1);
    assert.equal(child.stdin.writableEnded,true);assert.ok(args.includes('--parent-pipe'));
  });
}
for (const wrong of ['kind','invocation','unit']) {
  test(`listener refuses invalid ${wrong} without a dispatch marker`,async t=>{
    const c=setup(t),child=fakeChild(),claim=claimDelivery(c),e=event(c);
    if(wrong==='kind')e.kind='unrecognized';
    if(wrong==='unit')e.unit='different.service';
    if(wrong==='invocation')e.expected_invocation='b'.repeat(32);
    const result=waitForCompletion(c,claim,()=>child);
    child.stdout.write(JSON.stringify(e)+'\n');
    await assert.rejects(result);assert.equal(claim.dispatched(),false);
  });
}

test('real MCP adapter protocol persists marker immediately before tools/call',async t=>{
  const c=setup(t),adapter=path.join(c.outputDir,'fake-adapter.mjs');
  const audit=path.join(c.outputDir,'requests.jsonl');
  writeFileSync(adapter,`import {createInterface} from 'node:readline';
    import {appendFileSync} from 'node:fs';
    for await(const line of createInterface({input:process.stdin})) {
      const r=JSON.parse(line);appendFileSync(${JSON.stringify(audit)},line+'\\n');
      if(!r.id)continue;
      const result=r.method==='tools/list'?{tools:[{name:'read_thread'}]}:{ok:true};
      console.log(JSON.stringify({jsonrpc:'2.0',id:r.id,result}));
    }`);
  const saved=process.env.CODEX_APP_TOOLS_PIPE_PATH;
  process.env.CODEX_APP_TOOLS_PIPE_PATH='test-only-no-real-transport';
  t.after(()=>{if(saved===undefined)delete process.env.CODEX_APP_TOOLS_PIPE_PATH;
    else process.env.CODEX_APP_TOOLS_PIPE_PATH=saved;});
  await assert.rejects(callAppTool(adapter,threadId,'read_thread',{},
    {onDispatch:()=>{throw Error('marker write failed');}}),/marker write failed/);
  let requests=readFileSync(audit,'utf8').trim().split('\n').map(JSON.parse);
  assert.equal(requests.filter(r=>r.method==='tools/call').length,0);
  await assert.rejects(callAppTool(adapter,threadId,'missing_tool',{},
    {onDispatch:()=>assert.fail('must not dispatch')}),/unavailable/);
  let callbackCount=0;
  await callAppTool(adapter,threadId,'read_thread',{}, {onDispatch:()=>{
    callbackCount++;
    const recorded=readFileSync(audit,'utf8').trim().split('\n').map(JSON.parse);
    assert.equal(recorded.filter(r=>r.method==='tools/call').length,0);
  }});
  requests=readFileSync(audit,'utf8').trim().split('\n').map(JSON.parse);
  assert.equal(callbackCount,1);assert.equal(requests.filter(r=>r.method==='tools/call').length,1);
});

test('malformed JSON response shape becomes a pre-dispatch protocol failure',async t=>{
  const c=setup(t),adapter=path.join(c.outputDir,'malformed-adapter.mjs');
  writeFileSync(adapter,"process.stdout.write('null\\n');process.stdin.resume();");
  const saved=process.env.CODEX_APP_TOOLS_PIPE_PATH;
  process.env.CODEX_APP_TOOLS_PIPE_PATH='test-only-no-real-transport';
  t.after(()=>{if(saved===undefined)delete process.env.CODEX_APP_TOOLS_PIPE_PATH;
    else process.env.CODEX_APP_TOOLS_PIPE_PATH=saved;});
  let dispatched=false;
  await assert.rejects(callAppTool(adapter,threadId,'read_thread',{},
    {onDispatch:()=>{dispatched=true;}}),/Invalid MCP response shape/);
  assert.equal(dispatched,false);
});
