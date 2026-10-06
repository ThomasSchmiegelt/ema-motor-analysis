"use strict";
const fs=require("fs"), vm=require("vm");
const ctx={console,performance:{now:()=>Date.now()},Math,Float64Array,Uint8Array,document:null};
vm.createContext(ctx);
for(const f of ["geometrie.js","feld.js"]) vm.runInContext(fs.readFileSync(__dirname+"/"+f,"utf8"),ctx,f);
const P={topo:"esdr",laeufer:"sektor",stapel:1,ro:130,ri:75.01,lam:.577,poles:16,q:48,
  bnut:6,spalt:1,zahn:25,jochS:12,jochR:13,magd:6,alpha:.85,welle:30,wkI:14,rs:102.5,
  last:0,rotorOhneJoch:false,statorOhneJoch:true,nSpalte:2};
const g0=ctx.feldGitter(P,8,8); const ny=100, nx=Math.round(ny*(g0.breite/g0.hGes));
const g=ctx.feldGitter(P,nx,ny);
const b1=(A)=>{const {Bx,By}=ctx.feldAus(g,A); const e=ctx.eichung(P,g,By);
  let re=0,im=0; for(let i=0;i<nx;i++){const b=By[e.jGap*nx+i]*e.sf,t=2*Math.PI*i/nx;
  re+=b*Math.cos(t); im+=b*Math.sin(t);} return 2*Math.hypot(re,im)/nx;};
console.log(`Gitter ${nx}x${ny}\n`);
console.log("SOR:");
for(const it of [900,3000,10000]){
  const t=Date.now(); const r=ctx.loeseCG(g,it); const ms=Date.now()-t;
  let am=0; for(const v of r.A) am=Math.max(am,Math.abs(v));
  console.log(`  ${String(it).padStart(6)} Durchg. ${String(ms).padStart(5)} ms  relRest ${(r.rest/am).toExponential(2)}  B1 ${b1(r.A).toFixed(5)} T`);
}
console.log("\nCG (vorkonditioniert):");
for(const it of [100,300,800,2000]){
  const t=Date.now(); const r=ctx.loeseCG(g,it); const ms=Date.now()-t;
  console.log(`  ${String(it).padStart(6)} Schritte (${String(r.schritte).padStart(4)} gebr.) ${String(ms).padStart(5)} ms  relRest ${r.relRest.toExponential(2)}  B1 ${b1(r.A).toFixed(5)} T`);
}
