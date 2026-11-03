// iBlueControlMod module, page side: the custom widget "iblue-ports" (layout.json): the headline, four port buttons that say Empty /
// BT-connected / Wired-connected with the controller type under each, and one pop-up (opens under the buttons, also for a port that has a
// controller) with the controller type, the accessory and the profiles. Everything shown comes ready from GET /iblue/view (S.iblue).
// A choice POSTs /iblue/port or /iblue/profile; the service does it and the next /iblue/view carries the answer.
custom("iblue-ports",function(host){
 var grid=h("div",{"class":"iblue-ports"}),note=h("div",{"class":"sub"}),
  pop=h("div",{"class":"iblue-pop"}),popEl=pop,sel=-1,msg="",key="",popKey="";
 grid.style.cssText="display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;margin:8px 0";
 host.appendChild(grid);host.appendChild(note);host.appendChild(pop);
 var p=ui.popup(popEl);
 function view(){return S.iblue||null}
 function send(url,body){
  msg="Working...";paint();
  post(url,body,function(r,st,b){var m=b||r;msg=m&&m.message?m.message:"";reloadData("iblue");paint()})}
 function opt(text,on,fn,disabled){
  var b=h("button",{type:"button","class":"pill-s"+(on?" on":""),text:text});b.disabled=!!disabled;b.onclick=fn;return b}
 function group(label,items){
  var t=h("div",{"class":"t",text:label});t.style.marginTop=popEl.children.length>1?"14px":"0";
  var row=h("div",{"class":"optrow"},items);row.style.cssText="display:grid;grid-template-columns:repeat(auto-fit,minmax(6em,1fr));gap:8px";
  items.forEach(function(b){b.style.width="100%"});
  popEl.appendChild(t);popEl.appendChild(row)}
 function drawPop(v){
  var port=v.ports[sel];if(!port)return;
  var k=JSON.stringify([sel,port.type,port.acc,v.busy,v.profiles]);if(k===popKey)return;popKey=k;
  popEl.innerHTML="";
  popEl.appendChild(h("div",{"class":"t",text:"Port "+port.name+" - "+port.status}));
  var off=!v.online||v.busy;
  group("Controller type",v.types.map(function(t){
   return opt(t.label,t.value===port.type,function(){send("/iblue/port",{port:port.port,type:t.value,acc:port.acc})},off)}));
  group("Accessory",v.accs.map(function(a){
   return opt(a.label,a.value===port.acc,function(){send("/iblue/port",{port:port.port,type:port.type,acc:a.value})},off)}));
  var profs=(v.profiles||[]).filter(function(x){return x.used});
  group("Profile (also loads the button mapping, for all ports)",profs.length?profs.map(function(x){
   return opt(x.name,false,function(){if(confirm("Load profile “"+x.name+"”? It replaces the adapter's current configuration."))send("/iblue/profile",{slot:x.slot})},off)}):[h("span",{"class":"sub",text:"No saved profiles on the adapter"})])}
 function paint(){
  var v=view();if(!v)return;
  var k=JSON.stringify([v.ports.map(function(x){return [x.status,x.type_text]}),sel,v.online]);
  if(k!==key){key=k;grid.innerHTML="";
   v.ports.forEach(function(x,i){
    var b=h("button",{type:"button","class":"pill-s"+(i===sel?" on":""),"aria-label":"Port "+x.name+": "+x.status+(x.type_text?", "+x.type_text:"")});
    b.style.cssText="flex-direction:column;justify-content:flex-start;height:auto;min-height:8em;padding:12px 2px 10px;gap:6px;border-radius:var(--r-ctl);white-space:normal;line-height:1.2";
    var top=h("span",{"class":"iblue-top"},[h("b",{text:x.name}),h("span",{"class":"dot"+(x.kind==="bt"||x.kind==="wired"?" ok":"")})]);
    top.style.cssText="display:flex;align-items:center;justify-content:center;gap:8px;font-size:1.4em;line-height:1";
    var lines=x.status.split("-"),st=h("span",{"class":"iblue-status"},lines.map(function(l){return h("span",{text:l})}));      // "BT-connected" on two lines: BT / connected
    st.style.cssText=(x.kind==="empty"?"opacity:.6;":"")+"display:flex;flex-direction:column;align-items:center;min-height:2.4em;justify-content:center;font-size:.78em";
    var ty=h("span",{"class":"sub",text:x.type_text||"\u00a0"});ty.style.cssText="margin-top:auto;padding-top:6px;font-size:.74em;white-space:nowrap;width:86%;border-top:1px solid currentColor;opacity:.75";
    b.appendChild(top);b.appendChild(st);b.appendChild(ty);
    b.disabled=!v.online;
    b.onclick=function(e){e.stopPropagation();sel=i;popKey="";key="";p.open(grid);paint()};     // anchored to the row: paint() rebuilds the buttons
    grid.appendChild(b)})}
  setText(note,msg||v.message||v.note||"");
  if(sel>=0&&p.isOpen())drawPop(v)}
 p.onclose=function(){sel=-1;popKey="";key=""};
 UPD.push(paint);paint();
});
