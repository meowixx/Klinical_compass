import { test } from 'vitest';
import assert from 'node:assert/strict';
import { MockClinicalRepository, type StorageAdapter } from '../src/mock/MockClinicalRepository';

class MemoryStorage implements StorageAdapter {
 private values=new Map<string,string>();
 getItem(key:string){return this.values.get(key)??null;}
 setItem(key:string,value:string){this.values.set(key,value);}
 removeItem(key:string){this.values.delete(key);}
}

test('mock repository persists a newly added patient',async()=>{
 const storage=new MemoryStorage();
 const repository=new MockClinicalRepository(storage);
 const created=await repository.addPatient({name:'Тестовый П.',age:42,sex:'М',code:'F41.1'});
 const restored=new MockClinicalRepository(storage);
 assert.equal((await restored.getPatient(created.id)).name,'Тестовый П.');
 assert.equal((await restored.getPatients()).length,9);
});

test('demo login assigns the configured role for every account',async()=>{
 const repository=new MockClinicalRepository(new MemoryStorage());
 assert.equal((await repository.login('Admin','AdminAIMPY')).user.role,'admin');
 assert.equal((await repository.login('Doctor','Admin241')).user.role,'patient');
 assert.equal((await repository.login('Persent','Admin321')).user.role,'doctor');
 assert.equal((await repository.login('doctor@clinical-compass.local','Admin321')).user.role,'doctor');
 assert.equal((await repository.login('8 (999) 000-00-03','Admin241')).user.role,'patient');
 await assert.rejects(()=>repository.login('Admin','wrong'),/Неверный логин/);
});

test('admin role assignment changes the selected account type',async()=>{
 const repository=new MockClinicalRepository(new MemoryStorage());
 const changed=await repository.updateUserRole('patient-demo','doctor');
 assert.equal(changed.role,'doctor');
 assert.equal((await repository.getUsers()).find(account=>account.id==='patient-demo')?.role,'doctor');
});

test('doctor contacts and administrator-managed profile are stored separately',async()=>{
 const repository=new MockClinicalRepository(new MemoryStorage());
 const contact=await repository.saveContact('new-doctor@example.com','+79991112233');
 assert.equal(contact.email,'new-doctor@example.com');
 const profile=await repository.updateUserProfile('doctor-demo',{name:'Елена Тестовая',specialty:'Врач-тестировщик',organization:'Тестовая клиника'});
 assert.equal(profile.specialty,'Врач-тестировщик');
 assert.equal((await repository.getAccount()).phone,'+79991112233');
});
