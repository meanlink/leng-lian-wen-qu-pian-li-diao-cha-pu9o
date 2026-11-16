import {api} from './client.js';
export const datasets={list:()=>api('/datasets'),get:id=>api('/datasets/'+id),create:data=>api('/datasets',{method:'POST',body:JSON.stringify(data)})};
export const jobs={list:()=>api('/jobs'),get:id=>api('/jobs/'+id),create:data=>api('/jobs',{method:'POST',body:JSON.stringify(data)}),approve:id=>api('/jobs/'+id+'/approve',{method:'POST'})};
export const reports={list:()=>api('/reports'),create:data=>api('/reports',{method:'POST',body:JSON.stringify(data)}),toggle:id=>api('/reports/'+id+'/toggle',{method:'POST'}),deliveries:()=>api('/deliveries')};
export const genealogy={
 lots:()=>api('/genealogy/lots'),
 lot:id=>api('/genealogy/lots/'+id),
 registerLot:data=>api('/genealogy/lots',{method:'POST',body:JSON.stringify(data)}),
 split:data=>api('/genealogy/split',{method:'POST',body:JSON.stringify(data)}),
 merge:data=>api('/genealogy/merge',{method:'POST',body:JSON.stringify(data)}),
 outbound:data=>api('/genealogy/outbound',{method:'POST',body:JSON.stringify(data)}),
 events:()=>api('/genealogy/events'),
 recalls:()=>api('/genealogy/recalls'),
 recall:id=>api('/genealogy/recalls/'+id),
 createRecall:data=>api('/genealogy/recalls',{method:'POST',body:JSON.stringify(data)}),
 retryRecall:id=>api('/genealogy/recalls/'+id+'/retry',{method:'POST'})
};
