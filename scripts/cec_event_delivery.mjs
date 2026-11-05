/** Crash-safe, at-most-once dispatch evidence for one authorized wave event.
 * Only demonstrably pre-dispatch, dead owners can be recovered. Generations
 * are append-only exclusive claims, so concurrent recovery cannot steal a lock.
 */
import {createHash} from 'node:crypto';
import {closeSync, existsSync, fsyncSync, mkdirSync, openSync, readFileSync,
        renameSync, writeFileSync} from 'node:fs';
import path from 'node:path';

const PRE_DISPATCH = new Set(['connecting', 'armed', 'connection_failed',
  'listener_failed', 'transport_failed_before_dispatch']);
const UNCERTAIN = new Set(['dispatch_in_flight', 'sent', 'delivery_unknown']);

function durableJson(file, value, exclusive=false) {
  const fd=openSync(file, exclusive ? 'wx' : 'w');
  try {writeFileSync(fd, JSON.stringify(value,null,2)+'\n'); fsyncSync(fd);}
  finally {closeSync(fd);}
}

function readJson(file) {return JSON.parse(readFileSync(file,'utf8'));}

export function deliveryIdentity(config) {
  const keys=['threadId','unit','invocation','distro','repo','serverPath','prompt'];
  return createHash('sha256').update(JSON.stringify(keys.map(k=>[k,config[k]]))).digest('hex');
}

export function processAlive(pid) {
  if (!Number.isSafeInteger(pid) || pid<=0) throw Error('Invalid claim owner PID');
  try {process.kill(pid,0); return true;}
  catch (error) {if (error.code==='ESRCH') return false; throw error;}
}

export function claimDelivery(config, {pid=process.pid, isAlive=processAlive,
                                      maxAttempts=3}={}) {
  if (!Number.isInteger(maxAttempts) || maxAttempts<1 || maxAttempts>8)
    throw Error('Recovery attempts must be bounded to 1..8');
  const {outputDir,threadId,unit,invocation}=config;
  mkdirSync(outputDir,{recursive:true});
  const identity=deliveryIdentity(config);
  let attempt;
  for (attempt=1; attempt<=maxAttempts; attempt++) {
    const file=path.join(outputDir, attempt===1 ? 'claim.json' : `claim-${attempt}.json`);
    if (!existsSync(file)) {
      // Do not catch EEXIST and advance: another live recoverer owns this turn.
      durableJson(file,{schema:2,threadId,unit,invocation,identity_sha256:identity,
        pid,attempt,created:new Date().toISOString()},true);
      break;
    }
    const previous=readJson(file);
    if (previous.threadId!==threadId || previous.unit!==unit || previous.invocation!==invocation
        || (previous.schema!==undefined && previous.schema!==2)
        || (previous.schema===2 && previous.identity_sha256!==identity))
      throw Error('Claim identity mismatch; refusing recovery');
    // Establish owner death BEFORE reading its dispatch state. Otherwise the
    // old owner can dispatch/exit between an early state read and a later PID
    // check, making the stale pre-dispatch snapshot unsafe to recover.
    if (isAlive(previous.pid)) throw Error('Delivery owner is still alive');
    const stateFile=path.join(outputDir,previous.schema===2
      ? `attempt-${attempt}.state.json` : 'state.json');
    const state=existsSync(stateFile) ? readJson(stateFile) : null;
    if (state && (state.threadId!==threadId || state.unit!==unit
        || state.invocation!==invocation))
      throw Error('State identity mismatch; refusing recovery');
    if (existsSync(path.join(outputDir,`attempt-${attempt}.dispatch.json`))
        || UNCERTAIN.has(state?.status))
      throw Error('Dispatch may already have occurred; refusing duplicate delivery');
    if ((!state && previous.schema!==2) || (state && !PRE_DISPATCH.has(state.status)))
      throw Error('Previous dispatch state is unknown; refusing recovery');
  }
  if (attempt>maxAttempts) throw Error('Pre-dispatch recovery limit reached');
  const dispatchFile=path.join(outputDir,`attempt-${attempt}.dispatch.json`);
  function record(value) {
    if (existsSync(dispatchFile) && PRE_DISPATCH.has(value.status))
      throw Error('Dispatched delivery cannot return to pre-dispatch state');
    const state={schema:2,threadId,unit,invocation,identity_sha256:identity,attempt,
      updated:new Date().toISOString(),...value};
    const stateFile=path.join(outputDir,`attempt-${attempt}.state.json`);
    const temp=stateFile+'.tmp';
    durableJson(temp,state); renameSync(temp,stateFile);
    const latest=path.join(outputDir,`state-${attempt}.tmp`);
    durableJson(latest,state); renameSync(latest,path.join(outputDir,'state.json'));
  }
  return {attempt,record,
    dispatched:()=>existsSync(dispatchFile),
    beginDispatch(event) {
      durableJson(dispatchFile,{schema:2,identity_sha256:identity,attempt,event,
        created:new Date().toISOString()},true);
      record({status:'dispatch_in_flight',event});
    }
  };
}
