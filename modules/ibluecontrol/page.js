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
 function group(label,items,cols){
  var t=h("div",{"class":"t",text:label});t.style.marginTop=popEl.children.length>1?"14px":"0";
  var row=h("div",{"class":"optrow"},items);row.style.cssText="display:grid;grid-template-columns:"+(cols?"repeat("+cols+",minmax(0,1fr))":"repeat(auto-fit,minmax(6em,1fr))")+";gap:"+(cols?"6px":"8px");
  items.forEach(function(b){b.style.width="100%";if(cols)b.style.cssText+=";padding:0;font-size:.78em;letter-spacing:-.01em"});
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
   return opt(a.label,a.value===port.acc,function(){send("/iblue/port",{port:port.port,type:port.type,acc:a.value})},off)}),4);
  var profs=(v.profiles||[]).filter(function(x){return x.used});
  group("Profile (also loads the button mapping, for all ports)",profs.length?profs.map(function(x){
   return opt(x.name,false,function(){if(confirm("Load profile “"+x.name+"”? It replaces the adapter's current configuration."))send("/iblue/profile",{slot:x.slot})},off)}):[h("span",{"class":"sub",text:"No saved profiles on the adapter"})])}
 function paint(){
  var v=view();if(!v)return;
  var k=JSON.stringify([v.ports.map(function(x){return [x.status,x.console_name]}),sel,v.online,[1,2,3,4].map(function(n){return colourId("port_"+"abcd".charAt(n-1),"ibluecontrol")})]);
  if(k!==key){key=k;grid.innerHTML="";
   v.ports.forEach(function(x,i){
    var pc=colourId("port_"+x.name.toLowerCase(),"ibluecontrol"),b=h("button",{type:"button","class":"pill-s pri"+(pc?" c-"+pc:""),"aria-label":"Port "+x.name+": "+x.status+(x.type_text?", "+x.type_text:"")});      // the whole tile in the port's colour (A orange, B green, C blue, D magenta by default)
    b.style.cssText="flex-direction:column;justify-content:flex-start;height:auto;min-height:7em;padding:12px 2px 10px;gap:6px;border-radius:var(--r-ctl);white-space:normal;line-height:1.2"+(i===sel?";box-shadow:0 0 0 3px var(--text-1)":"")+(x.kind==="empty"?";background:transparent;text-shadow:none;color:var(--text-2)":x.kind==="wired"?";opacity:.55":"");      // empty: only the border; wired: the paler fill; Bluetooth: the full colour
    var top=h("b",{text:x.name});top.style.cssText="font-size:1.6em;line-height:1";                    // the port letter
    var st=h("span",{text:x.short||x.status});st.style.cssText="font-size:.9em";                           // BT, Wired or Empty
    var ty=h("span",{text:x.console_name||"\u00a0"});                                                     // what the controller tells the console: Controller, Keyboard, Mouse
    ty.style.cssText="margin-top:auto;padding-top:6px;font-size:.74em;white-space:nowrap;width:90%;border-top:1px solid "+(x.console_name?"currentColor":"transparent");
    b.appendChild(top);b.appendChild(st);b.appendChild(ty);
    b.disabled=!v.online;
    b.onclick=function(e){e.stopPropagation();sel=i;popKey="";key="";p.open(grid);paint()};     // anchored to the row: paint() rebuilds the buttons
    grid.appendChild(b)})}
  setText(note,msg||v.message||v.note||"");
  if(sel>=0&&p.isOpen())drawPop(v)}
 p.onclose=function(){sel=-1;popKey="";key=""};
 UPD.push(paint);paint();
});
