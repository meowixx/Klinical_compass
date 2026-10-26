import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StdioClientTransport } from '@modelcontextprotocol/sdk/client/stdio.js';
import { chromium } from '@playwright/test';
import fs from 'node:fs';
const executable=chromium.executablePath().replace(/chromium-(\d+)/,(_,version)=>'chromium_headless_shell-'+version).replace('chrome-win64','chrome-headless-shell-win64').replace('chrome.exe','chrome-headless-shell.exe');
const results=[];
for(const [name,entry,args] of [
 ['playwright','node_modules/@playwright/mcp/cli.js',['--headless','--isolated','--executable-path',executable]],
 ['chrome-devtools','node_modules/chrome-devtools-mcp/build/src/bin/chrome-devtools-mcp.js',['--headless','--isolated','--no-usage-statistics','--no-performance-crux','--executablePath',executable]],
]) {
 const client=new Client({name:'compass-audit',version:'1.0'});
 const transport=new StdioClientTransport({command:process.execPath,args:[entry,...args],stderr:'pipe'});
 try {
  await client.connect(transport);
  const tools=await client.listTools();
  const call=async(name,args)=>{const r=await client.callTool({name,arguments:args});results.push({server:entry,tool:name,result:r});fs.writeFileSync('audit-results/mcp.json',JSON.stringify(results,null,2));if(r.isError)throw new Error(JSON.stringify(r));};
  if(name==='playwright'){
   await call('browser_navigate',{url:'http://127.0.0.1:3130'});
   await call('browser_snapshot',{});
   await call('browser_console_messages',{level:'error'});
  }else{
   await call('new_page',{url:'http://127.0.0.1:3130'});
   await call('list_console_messages',{pageId:1});
   await call('list_network_requests',{pageId:1});
   await call('take_snapshot',{pageId:1});
  }
  console.log(name,tools.tools.length,'tools: OK');
 }finally{await client.close();}
}
fs.mkdirSync('audit-results',{recursive:true});fs.writeFileSync('audit-results/mcp.json',JSON.stringify(results,null,2));
