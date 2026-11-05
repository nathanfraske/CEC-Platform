/** One-shot MCP client for the installed, unmodified Codex app-tools adapter.
 * No credentials, model process, new task, daemon or scheduler is created.
 * The desktop owns message queuing and preserves the target task's settings.
 */
import {spawn} from 'node:child_process';
import {createInterface} from 'node:readline';
import {realpathSync} from 'node:fs';
import {pathToFileURL} from 'node:url';

export async function callAppTool(serverPath, threadId, name, args,
                                  {timeoutMs=10000,onDispatch}={}) {
  if (!process.env.CODEX_APP_TOOLS_PIPE_PATH) throw Error('Codex app-tools connection is unavailable');
  if (!/^[0-9a-f-]{36}$/i.test(threadId)) throw Error('An explicit existing task ID is required');
  const child = spawn(process.execPath, [serverPath], {stdio:['pipe','pipe','pipe'], windowsHide:true});
  const pending = new Map();
  let serial=0, stderr='', failure=null;
  const lines=createInterface({input:child.stdout});
  function fail(error) {
    failure ??= error;
    for (const value of pending.values()) { clearTimeout(value.timer); value.reject(error); }
    pending.clear();
  }
  child.on('error',fail);
  child.stdin.on('error',fail);
  child.on('close',(code)=>fail(Error(`App-tools adapter closed (${code}): ${stderr.slice(-1000)}`)));
  child.stderr.on('data',chunk=>{stderr=(stderr+chunk).slice(-4000);});
  lines.on('line',line=>{
    let row;
    try { row=JSON.parse(line); } catch { return fail(Error('Invalid MCP response')); }
    if (row===null || typeof row!=='object' || Array.isArray(row))
      return fail(Error('Invalid MCP response shape'));
    const waiter=pending.get(row.id);
    if (!waiter) return;
    pending.delete(row.id); clearTimeout(waiter.timer);
    row.error ? waiter.reject(Error(row.error.message)) : waiter.resolve(row.result);
  });
  function request(method,params,beforeWrite) {
    if (failure) return Promise.reject(failure);
    const id=++serial;
    return new Promise((resolve,reject)=>{
      const timer=setTimeout(()=>{
        pending.delete(id); reject(Error(`MCP ${method} acknowledgement timed out`));
      },timeoutMs);
      pending.set(id,{resolve,reject,timer});
      try {
        // Synchronous durable evidence must precede the mutating request, not
        // initialization or catalog lookup. A failed marker prevents dispatch.
        if (beforeWrite) {
          const result=beforeWrite();
          if (result && typeof result.then==='function')
            throw Error('Dispatch evidence callback must be synchronous');
        }
        child.stdin.write(JSON.stringify({jsonrpc:'2.0',id,method,params})+'\n');
      } catch (error) {
        clearTimeout(timer); pending.delete(id); reject(error);
      }
    });
  }
  try {
    await request('initialize',{protocolVersion:'2024-11-05',capabilities:{},
      clientInfo:{name:'cec-wave-event-bridge',version:'1.0'}});
    child.stdin.write(JSON.stringify({jsonrpc:'2.0',method:'notifications/initialized'})+'\n');
    const catalog=await request('tools/list',{});
    if (!catalog.tools?.some(tool=>tool.name===name)) throw Error(`App tool unavailable: ${name}`);
    const result=await request('tools/call',{name,arguments:args,_meta:{threadId}},onDispatch);
    if (result?.isError) throw Error(JSON.stringify(result.content));
    return result;
  } finally {
    fail(Error('MCP client closed')); lines.close(); child.stdin.end(); child.kill();
  }
}

if (process.argv[1] && import.meta.url===pathToFileURL(realpathSync(process.argv[1])).href) {
  const [mode,serverPath,threadId]=process.argv.slice(2);
  if (mode!=='probe') throw Error('Only the read-only probe is exposed here');
  const result=await callAppTool(serverPath,threadId,'read_thread',
    {threadId,turnLimit:1,includeOutputs:false,maxOutputCharsPerItem:200});
  console.log(JSON.stringify({ok:true,readOnly:true,result}));
}
