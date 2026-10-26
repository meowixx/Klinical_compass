'use client';
import { createContext, useContext } from 'react';
import type { AppData, ClinicalAlert, ClinicalDocument, Patient, Simulation } from '@/types';
export type PageName='dashboard'|'patients'|'patient'|'alerts'|'tasks'|'messages'|'ai'|'knowledge'|'reports'|'settings';
export type ModalState={type:'patient'}|{type:'task';patientId?:string}|{type:'questionnaire';patientId:string}|{type:'alert';alert:ClinicalAlert}|{type:'document';document:ClinicalDocument}|null;
export interface AppContextValue { data:AppData; page:PageName; selectedId:string; search:string; setSearch:(s:string)=>void; navigate:(p:PageName,id?:string)=>void; modal:(v:ModalState)=>void; busy:boolean; run:(action:()=>Promise<unknown>,message?:string)=>Promise<boolean>; toast:(message:string)=>void; simulation:Simulation; setSimulation:(s:Simulation)=>void; logout:()=>void; }
export const AppContext=createContext<AppContextValue|null>(null);
export function useApp(){const value=useContext(AppContext);if(!value)throw new Error('App context unavailable');return value;}
export function usePatient():Patient|undefined{const {data,selectedId}=useApp();return data.patients.find(p=>p.id===selectedId);}
