import type { ClinicalRepository } from '../repositories';
import { MockClinicalRepository } from '../mock/MockClinicalRepository';
import { ApiClinicalRepository } from '../api/ApiClinicalRepository';
import type { AppData, Simulation } from '../types';
export const isMock = process.env.NEXT_PUBLIC_DATA_SOURCE !== 'api';
let instance:ClinicalRepository|undefined;
export function repository():ClinicalRepository {if(!instance)instance=isMock?new MockClinicalRepository(typeof window==='undefined'?undefined:window.localStorage):new ApiClinicalRepository(process.env.NEXT_PUBLIC_API_URL||'http://localhost:8000/api/v1');return instance;}
export async function loadDashboard(simulation:Simulation):Promise<AppData>{await new Promise(resolve=>setTimeout(resolve,300));if(simulation==='error')throw new Error('Не удалось загрузить данные. Попробуйте ещё раз.');if(simulation==='denied')throw new Error('Нет доступа к этому разделу. Проверьте права учётной записи.');const data=await repository().getData();return simulation==='empty'?{...data,patients:[],alerts:[],tasks:[],recommendations:[],documents:[],assignments:[],audit:[]}:data;}
export function formatDate(value:string,withTime=false){return new Date(value).toLocaleString('ru-RU',{day:'numeric',month:'long',...(withTime?{hour:'2-digit',minute:'2-digit'}:{})});}
export const DEMO_TODAY=new Date().toLocaleDateString('en-CA');

