/** Event-driven, one-shot desktop follow-up for an exact WSL service run.
 * Listens to systemd D-Bus state changes; no periodic Codex/model wakeups.
 * Sends through the existing app-tools MCP adapter, never a second agent.
 */
import {spawn} from 'node:child_process';
import {readFileSync,realpathSync} from 'node:fs';
import path from 'node:path';
import {createInterface} from 'node:readline';
import {pathToFileURL} from 'node:url';
import {setTimeout as delay} from 'node:timers/promises';
import {callAppTool} from './cec_codex_app_events.mjs';
import {claimDelivery} from './cec_event_delivery.mjs';

const TERMINAL_KINDS=new Set(['service_completed','service_failed','invocation_changed',
  'initial_invocation_unavailable','unit_unavailable','tracked_unit_removed',
  'unit_snapshot_unstable']);

export function waitForCompletion(config,claim,spawnChild=spawn,{armTimeoutMs=10000}={}) {
  const {distro,repo,unit,invocation}=config;
  if (!Number.isFinite(armTimeoutMs) || armTimeoutMs<=0 || armTimeoutMs>10000)
    return Promise.reject(Error('Listener handshake timeout must be within 10 seconds'));
  return new Promise((resolve,reject)=>{
    const child=spawnChild('wsl.exe',['-d',distro,'--cd',repo,'--exec','/usr/bin/python3',
      'scripts/cec_systemd_completion_event.py','--unit',unit,'--invocation',invocation,
      '--parent-pipe'],{stdio:['pipe','pipe','pipe'],windowsHide:true});
    let settled=false,stderr='';
    const lines=createInterface({input:child.stdout});
    const armTimer=setTimeout(()=>finish(Error('Completion listener did not arm before deadline')),
                              armTimeoutMs);
    function finish(error,event) {
      if (settled) return;
      settled=true; clearTimeout(armTimer); lines.close(); child.stdin.end(); child.kill();
      error ? reject(error) : resolve(event);
    }
    child.stderr.on('data',chunk=>{stderr=(stderr+chunk).slice(-4000);});
    child.on('error',error=>finish(error));
    child.stdin.on('error',error=>finish(error));
    lines.on('error',error=>finish(error));
    // close follows drained stdio; exit can race the terminal JSON line.
    child.on('close',code=>finish(Error(`Completion listener closed (${code}): ${stderr}`)));
    lines.on('line',line=>{
      let event;
      try {event=JSON.parse(line);} catch {return;}
      try {
        if (event.unit!==unit || event.expected_invocation!==invocation)
          throw Error('Completion event does not match the watched invocation');
        if (event.kind==='armed') {
          claim.record({status:'armed',event}); clearTimeout(armTimer); return;
        }
        if (!TERMINAL_KINDS.has(event.kind)) throw Error('Unknown completion event kind');
        finish(null,event);
      } catch (error) {finish(error);}
    });
  });
}

export async function runBridge(config,{env=process.env,callTool=callAppTool,
  listen=waitForCompletion,retryDelay=delay,claimOptions={},maxPreDispatchAttempts=3}={}) {
  const {threadId,serverPath,unit,invocation,outputDir,prompt}=config;
  if (!threadId || threadId!==env.CODEX_THREAD_ID)
    throw Error('Bridge must inherit the explicitly authorized task identity');
  if (!path.isAbsolute(outputDir) || typeof prompt!=='string' || !prompt.trim()
      || !/^[A-Za-z0-9_.@:-]+\.service$/.test(unit) || !/^[0-9a-f]{32}$/.test(invocation))
    throw Error('An absolute evidence directory, exact service run and prompt are required');
  if (!Number.isInteger(maxPreDispatchAttempts) || maxPreDispatchAttempts<1
      || maxPreDispatchAttempts>3) throw Error('Pre-dispatch retries must be bounded to 1..3');
  const claim=claimDelivery(config,claimOptions);
  let event;
  for (let attempt=1; attempt<=maxPreDispatchAttempts; attempt++) {
    let phase='connection_failed';
    try {
      claim.record({status:'connecting',connection_attempt:attempt});
      await callTool(serverPath,threadId,'read_thread',
        {threadId,turnLimit:1,includeOutputs:false,maxOutputCharsPerItem:100});
      phase='listener_failed';
      event=await listen(config,claim);
      break;
    } catch (error) {
      claim.record({status:phase,error:String(error),connection_attempt:attempt});
      if (attempt===maxPreDispatchAttempts) throw error;
      await retryDelay(250*attempt);
    }
  }
  const message=`Automatic CEC wave-runner event, requested by the user.\n`+
      `Service: ${unit}; invocation: ${invocation}; event: ${event.kind}.\n`+
      `${prompt}\nEvent details: ${JSON.stringify(event)}\n`+
      `This is an automated continuation, not a new human message. `+
      `Do not reactivate periodic monitoring. Delivery evidence: ${outputDir}`;
  for (let attempt=1; attempt<=maxPreDispatchAttempts; attempt++) {
    try {
      const result=await callTool(serverPath,threadId,'send_message_to_thread',
        {threadId,prompt:message},{onDispatch:()=>claim.beginDispatch(event)});
      if (!claim.dispatched()) throw Error('Transport did not establish dispatch evidence');
      claim.record({status:'sent',event,acknowledgement:result});
      return {status:'sent',unit,invocation,event:event.kind};
    } catch (error) {
      // A timeout after tools/call can mean delivery. Never replay it blindly.
      // Adapter initialization/catalog failures, however, are safe to retry.
      const uncertain=claim.dispatched();
      claim.record({status:uncertain ? 'delivery_unknown' : 'transport_failed_before_dispatch',
        event,error:String(error),transport_attempt:attempt});
      if (uncertain || attempt===maxPreDispatchAttempts) throw error;
      await retryDelay(250*attempt);
    }
  }
}

if (process.argv[1] && import.meta.url===pathToFileURL(realpathSync(process.argv[1])).href) {
  try {console.log(JSON.stringify(await runBridge(JSON.parse(readFileSync(process.argv[2],'utf8')))));}
  catch (error) {console.error(String(error));process.exitCode=1;}
}
