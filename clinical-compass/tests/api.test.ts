import { afterEach, expect, test, vi } from 'vitest';
import { ApiClinicalRepository } from '../src/api/ApiClinicalRepository';
afterEach(()=>vi.unstubAllGlobals());
test('API validation details are readable',async()=>{
 vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response(JSON.stringify({detail:[{msg:'Invalid email'},{msg:'Required'}]}),{status:422})));
 await expect(new ApiClinicalRepository('/api').login('x','y')).rejects.toThrow('Invalid email; Required');
});
test('logout calls the server and accepts an empty response',async()=>{
 const fetcher=vi.fn().mockResolvedValue(new Response(null,{status:204}));vi.stubGlobal('fetch',fetcher);
 await new ApiClinicalRepository('/api').logout();expect(fetcher).toHaveBeenCalledWith('/api/auth/logout',expect.objectContaining({method:'POST',credentials:'include'}));
});
test('expired API session asks the app to show login again',async()=>{
 const listener=vi.fn();window.addEventListener('cc-auth-required',listener);
 vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response(JSON.stringify({detail:'Требуется вход'}),{status:401})));
 await expect(new ApiClinicalRepository('/api').getData()).rejects.toThrow('Требуется вход');
 expect(listener).toHaveBeenCalledOnce();window.removeEventListener('cc-auth-required',listener);
});
