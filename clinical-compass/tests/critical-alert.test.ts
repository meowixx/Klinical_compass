import { test } from 'vitest';
import assert from 'node:assert/strict';
import { MockClinicalRepository, type StorageAdapter } from '../src/mock/MockClinicalRepository';

class MemoryStorage implements StorageAdapter {
 private values=new Map<string,string>();
 getItem(key:string){return this.values.get(key)??null;}
 setItem(key:string,value:string){this.values.set(key,value);}
 removeItem(key:string){this.values.delete(key);}
}

test('critical alert cannot close without a meaningful physician comment',async()=>{
 const repository=new MockClinicalRepository(new MemoryStorage());
 await assert.rejects(()=>repository.updateAlert('a1',{status:'closed',comment:'',action:'Проверены данные дневника'}),/нужен комментарий врача/);
 const alert=await repository.updateAlert('a1',{status:'closed',comment:'Данные проверены врачом, запланирован повторный контакт.',action:'Запланирована повторная консультация'});
 assert.equal(alert.status,'closed');
 const data=await repository.getData();
 assert.match(data.audit[0].action,/Закрыт алерт/);
});
