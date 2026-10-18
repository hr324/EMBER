/* EMBER: dependency-free, offline-capable Canvas map + time replay UI.
 * The map shows georeferenced points in a local flat display; without a
 * basemap, it makes no claim about unseen terrain or infrastructure.
 */
'use strict';
const $ = id => document.getElementById(id);
const state = { observations:[], output:null, context:null, time:1, playing:false,
  timer:null, scale:1, panX:0, panY:0, drag:null, extent:null, perimeter:true };
const canvas=$('mapCanvas'), ctx=canvas.getContext('2d');
const leafletView={map:null,enabled:false,layers:null,tileErrors:0,loadedTiles:false};
const accent={ink:'#eaf3ef',line:'#26373d',teal:'#73ddd0',amber:'#f2ad65',red:'#ff8272'};

/** Read a JSON API response with complete, actionable error messages. */
async function request(url){
  const r=await fetch(url,{cache:'no-store'});let data;
  try{data=await r.json()}catch{throw new Error('Backend did not return JSON')}
  if(!r.ok)throw new Error(data.error||data.detail||`HTTP ${r.status}`);
  return data;
}

/** Format UTC ISO dates consistently on any viewer machine. */
function utc(t){return t?new Date(t).toISOString().replace('T',' ').slice(0,16)+' UTC':'—'}
function fmt(v,d=2){return Number.isFinite(Number(v))?Number(v).toFixed(d):'—'}
function text(id,value){$(id).textContent=value}

/** Compute geographic extents from actual model outputs, not known origin. */
function getExtent(){
  const entries=[];
  for(const d of state.observations)entries.push([+d.longitude,+d.latitude]);
  if(state.output){
    const inf=state.output.inference;
    for(const c of inf.candidate_cells)entries.push([c.longitude,c.latitude]);
  }
  if(!entries.length)return {left:-122,right:-121,bottom:39,top:40};
  const lons=entries.map(x=>x[0]),lats=entries.map(x=>x[1]);
  const left=Math.min(...lons),right=Math.max(...lons),bottom=Math.min(...lats),top=Math.max(...lats);
  const pad=Math.max(right-left,top-bottom)*.08||.02;
  return {left:left-pad,right:right+pad,bottom:bottom-pad,top:top+pad};
}

/** Resize for pixel-perfect canvas render at the device's DPI. */
function resize(){
  const r=canvas.getBoundingClientRect(),ratio=window.devicePixelRatio||1;
  canvas.width=Math.max(100,Math.round(r.width*ratio));canvas.height=Math.max(100,Math.round(r.height*ratio));
  ctx.setTransform(ratio,0,0,ratio,0,0);draw();
}

/** Project lon/lat to screen using cos(latitude) aspect compensation. */
function xy(lon,lat){
  const w=canvas.clientWidth,h=canvas.clientHeight,b=state.extent||getExtent();
  const mid=(b.bottom+b.top)/2,k=Math.cos(mid*Math.PI/180);
  const worldW=(b.right-b.left)*k,worldH=b.top-b.bottom;
  const factor=.90*Math.min(w/Math.max(worldW,1e-10),h/Math.max(worldH,1e-10));
  return [w/2+((lon-(b.left+b.right)/2)*k*factor)*state.scale+state.panX,
          h/2-((lat-(b.bottom+b.top)/2)*factor)*state.scale+state.panY];
}

/** Grid ticks are actual coordinates rather than an invented basemap. */
function grid(){
  const w=canvas.clientWidth,h=canvas.clientHeight,b=state.extent||getExtent();
  ctx.fillStyle='#10191c';ctx.fillRect(0,0,w,h);
  ctx.strokeStyle=accent.line;ctx.lineWidth=.6;ctx.font='10px monospace';ctx.fillStyle='#566e71';
  for(let i=0;i<=8;i++){
    const lon=b.left+(b.right-b.left)*i/8;
    const x=xy(lon,(b.bottom+b.top)/2)[0];
    ctx.beginPath();ctx.moveTo(x,0);ctx.lineTo(x,h);ctx.stroke();
    if(x>3&&x<w-70)ctx.fillText(lon.toFixed(3)+'°',x+5,h-15);
  }
  for(let i=0;i<=7;i++){
    const lat=b.bottom+(b.top-b.bottom)*i/7;
    const y=xy((b.left+b.right)/2,lat)[1];
    ctx.beginPath();ctx.moveTo(0,y);ctx.lineTo(w,y);ctx.stroke();
    if(y>18&&y<h-18)ctx.fillText(lat.toFixed(3)+'°',w-69,y-5);
  }
}

/** Draw optional polygons and powerline features only as contextual overlays. */
function geojsonFeatures(geojson,color,width){
  if(!geojson||!geojson.features)return;
  ctx.strokeStyle=color;ctx.lineWidth=width;
  for(const feature of geojson.features){
    const g=feature.geometry;if(!g)continue;
    let lines=[];
    if(g.type==='LineString')lines=[g.coordinates];
    if(g.type==='MultiLineString'||g.type==='Polygon')lines=g.coordinates;
    if(g.type==='MultiPolygon')lines=g.coordinates.flat();
    for(const line of lines){
      ctx.beginPath();line.forEach(([lon,lat],i)=>{const [x,y]=xy(lon,lat);i?ctx.lineTo(x,y):ctx.moveTo(x,y)});
      if(g.type.includes('Polygon'))ctx.closePath();ctx.stroke();
    }
  }
}

/** Draw circles/markers in a single deterministic render path. */
function circle(lon,lat,r,color,stroke){
  const [x,y]=xy(lon,lat);ctx.beginPath();ctx.arc(x,y,r,0,2*Math.PI);
  ctx.fillStyle=color;ctx.fill();if(stroke){ctx.strokeStyle=stroke;ctx.lineWidth=1.4;ctx.stroke()}
}

/** Render inferred candidate surface, observed detections, wind and spatial overlays. */
function draw(){
  if(!canvas.width)return;
  grid();const output=state.output;
  if(!output)return;
  const info=output.inference, cells=info.candidate_cells;
  const maxScore=Math.max(...cells.map(c=>c.score_mass),1e-10);
  for(const c of cells.slice().reverse()){
    const strength=Math.sqrt(Math.max(0,c.score_mass/maxScore));
    const [x,y]=xy(c.longitude,c.latitude);
    const size=Math.max(2.5,Math.min(12,5.0*state.scale))*Math.max(.3,strength);
    ctx.fillStyle=`rgba(242,173,101,${Math.max(.035,Math.min(.57,strength*.40))})`;
    ctx.fillRect(x-size/2,y-size/2,size,size);
  }
  if(state.context){
    if(state.perimeter)geojsonFeatures(state.context.perimeter,'rgba(255,130,114,.80)',2);
    geojsonFeatures(state.context.powerlines,'rgba(245,224,140,.65)',1.7);
    for(const p of state.context.lightning||[])circle(+p.longitude,+p.latitude,4,accent.red,'#10191c');
  }
  const all=state.observations.slice().sort((a,b)=>a.observed_utc.localeCompare(b.observed_utc));
  const displayCount=Math.ceil(all.length*state.time);
  for(const d of all.slice(0,displayCount))circle(+d.longitude,+d.latitude,3.1,accent.teal,'#10191c');
  const origin=info.best_origin,b=info.baseline_centroid;
  if(origin){
    const [x,y]=xy(origin.longitude,origin.latitude);
    ctx.beginPath();ctx.arc(x,y,14,0,Math.PI*2);ctx.strokeStyle='rgba(255,255,255,.36)';ctx.lineWidth=2;ctx.stroke();
    circle(origin.longitude,origin.latitude,6,'#fff',accent.amber);
    ctx.font='bold 10px monospace';ctx.fillStyle='#f3ede1';ctx.fillText('ORIGIN',x+15,y-10);
  }
  if(b){const [x,y]=xy(b.longitude,b.latitude);ctx.strokeStyle=accent.red;ctx.lineWidth=2;
    ctx.beginPath();ctx.moveTo(x-6,y-6);ctx.lineTo(x+6,y+6);ctx.moveTo(x+6,y-6);ctx.lineTo(x-6,y+6);ctx.stroke();}
  if(info.weather_summary){
    const wind=info.weather_summary,a=wind.wind_to_deg*Math.PI/180;
    const x=canvas.clientWidth-80,y=80,length=44;
    ctx.strokeStyle=accent.teal;ctx.lineWidth=2;ctx.beginPath();ctx.moveTo(x,y);
    ctx.lineTo(x+Math.sin(a)*length,y-Math.cos(a)*length);ctx.stroke();
    const tipX=x+Math.sin(a)*length,tipY=y-Math.cos(a)*length;
    ctx.beginPath();ctx.moveTo(tipX,tipY);ctx.lineTo(tipX-Math.sin(a-.5)*12,tipY+Math.cos(a-.5)*12);
    ctx.moveTo(tipX,tipY);ctx.lineTo(tipX-Math.sin(a+.5)*12,tipY+Math.cos(a+.5)*12);ctx.stroke();
    ctx.font='10px monospace';ctx.fillStyle=accent.teal;ctx.fillText('WIND →',x-20,y+20);
    ctx.fillText(fmt(wind.wind_speed_mps,1)+' m/s',x-20,y+34);
  }
}

/** Update replay based on observed chronological hotspot timestamps. */
function setTime(value){
  state.time=Math.max(0,Math.min(1,Number(value)/100));
  const a=state.observations.slice().sort((x,y)=>x.observed_utc.localeCompare(y.observed_utc));
  const count=Math.ceil(a.length*state.time);
  text('observationCount',count+' / '+a.length+' px');
  text('timeLabel',count?utc(a[count-1].observed_utc):'Before first pass');
  draw();
  renderLeafletObservations();
}

/** Fill inference, quality and causal-hypothesis panels without HTML injection. */
function renderPanels(output){
  const i=output.inference,b=i.best_origin,graph=output.evidence_graph;
  text('coordinates',fmt(Math.abs(b.latitude),4)+'° '+(b.latitude>=0?'N':'S')+', '+fmt(Math.abs(b.longitude),4)+'° '+(b.longitude>=0?'E':'W'));
  text('ignitionTime','Model-estimated: '+utc(b.estimated_ignition_utc));
  text('area80',fmt(i.regions.top80.area_km2,1));text('numberCells',i.grid.nodes.toLocaleString());
  const gate=i.observation_gate;
  $('gateText').innerHTML=`<strong>${gate.detections} pixels · ${gate.passes} detected passes</strong><br>${gate.usable?'Multiple passes found; review incident attribution.':'LOW OBSERVABILITY: satellite timing insufficient for strong conclusions.'}`;
  const evidence=$('evidence');evidence.replaceChildren();
  const nodes=graph.nodes.filter(n=>n.kind==='powerline'||n.kind==='lightning');
  if(!nodes.length){const p=document.createElement('p');p.className='empty-content';p.textContent='No optional power-line or lightning inputs. Candidate ranking is driven only by satellite and available environmental data.';evidence.append(p)}
  for(const n of nodes.slice(0,7)){
    const item=document.createElement('div');item.className='evidence-item '+n.kind;
    const heading=document.createElement('div');heading.className='evidence-title';heading.textContent=n.kind==='powerline'?'Mapped power-line proximity':'Lightning proximity';
    const desc=document.createElement('div');desc.className='evidence-detail';
    desc.textContent=n.kind==='powerline'?`${fmt(n.properties.distance_m,0)} m · spatial association ONLY`:
         `${fmt(n.properties.distance_km,1)} km · ${fmt(n.properties.hours_before_model_ignition,1)} h before inferred ignition`;
    item.append(heading,desc);evidence.append(item);
  }
  $('methodText').innerHTML=`<strong>${i.variant.toUpperCase()} · ${i.ensemble_count} scenario(s)</strong><br>Directed graph: ${i.graph_summary.directed_edges.toLocaleString()} edges. Elevation coverage: ${Math.round(100*i.graph_summary.elevation_coverage)}%; fuel: ${Math.round(100*i.graph_summary.fuel_coverage)}%.<br><span class="warning">Score-mass areas are not calibrated confidence regions.</span>`;
}

/** Fetch backend results fresh, with user-selectable ablation and geometry. */
async function run(){
  $('runBtn').disabled=true;$('runBtn').innerHTML='<span class="spinner">↻</span> RECONSTRUCTING';
  $('mapOverlay').classList.remove('hidden');text('mapOverlay','COMPUTING REVERSE SHORTEST PATHS...');
  try{
    const p=new URLSearchParams({variant:$('variant').value,cell_m:$('cell').value,
       margin_km:$('margin').value,ensemble:$('ensemble').checked});
    state.output=await request('/api/infer?'+p.toString());
    state.extent=getExtent();state.scale=1;state.panX=state.panY=0;
    renderPanels(state.output);$('mapOverlay').classList.add('hidden');draw();
    renderLeafletAll();fitLeaflet();
  }catch(err){text('mapOverlay','ERROR: '+err.message);$('gateText').textContent=err.message}
  finally{$('runBtn').disabled=false;$('runBtn').textContent='↻ RUN INFERENCE'}
}

/** Prime observation timeline and host provenance, then request inference. */
async function init(){
  try{
    const [health,obs]=await Promise.all([request('/api/health'),request('/api/observations')]);
    state.observations=obs.detections;
    const synthetic=String(health.data_mode).toLowerCase().includes('synthetic');
    text('dataBadge',synthetic?'SYNTHETIC TEST DATA':'HISTORICAL INPUT · VERIFY');
    $('dataBadge').classList.toggle('synthetic',synthetic);
    text('machineBadge',health.machine.toUpperCase()+' · PY '+health.python);
    text('provenance','Executed on '+health.machine+' (Python '+health.python+'). Input SHA256: '+health.snapshot_sha256.slice(0,18)+'… No ignition labels loaded by API.');
    if(state.observations.length){text('timeStart',utc(state.observations[0].observed_utc));text('timeEnd',utc(state.observations.at(-1).observed_utc));}
    setTime(100);
    try{state.context=await request('/api/context')}catch{state.context=null}
    await run();
  }catch(err){text('mapOverlay','SETUP ERROR: '+err.message);text('provenance',err.message)}
}

/** Viewport interactions preserve identical georeferencing for each layer. */
canvas.addEventListener('pointerdown',e=>{canvas.setPointerCapture(e.pointerId);state.drag={x:e.clientX,y:e.clientY}});
canvas.addEventListener('pointermove',e=>{
  if(state.drag){state.panX+=e.clientX-state.drag.x;state.panY+=e.clientY-state.drag.y;
    state.drag={x:e.clientX,y:e.clientY};draw();return}
  if(!state.output)return;
  const r=canvas.getBoundingClientRect();let winner=null,closest=14;
  for(const c of state.output.inference.candidate_cells.slice(0,400)){
    const [x,y]=xy(c.longitude,c.latitude),d=Math.hypot(e.clientX-r.left-x,e.clientY-r.top-y);
    if(d<closest){winner=c;closest=d}
  }
  const tip=$('mapTooltip');
  if(winner){tip.style.display='block';tip.style.left=Math.min(r.width-165,e.clientX-r.left+13)+'px';tip.style.top=Math.min(r.height-58,e.clientY-r.top+13)+'px';
    tip.textContent='#'+winner.rank+' · '+fmt(winner.latitude,4)+', '+fmt(winner.longitude,4)+' · score '+winner.score_mass.toExponential(2)}
  else tip.style.display='none';
});
canvas.addEventListener('pointerup',()=>state.drag=null);canvas.addEventListener('pointercancel',()=>state.drag=null);
canvas.addEventListener('wheel',e=>{e.preventDefault();state.scale=Math.max(.6,Math.min(12,state.scale*(e.deltaY>0?.88:1.14)));draw()},{passive:false});
$('resetView').addEventListener('click',()=>{
  if(leafletView.enabled){fitLeaflet();return}
  state.scale=1;state.panX=state.panY=0;draw()
});
$('togglePerimeter').addEventListener('click',()=>{state.perimeter=!state.perimeter;draw();renderLeafletContext()});
$('mapMode').addEventListener('click',()=>switchMapMode(!leafletView.enabled));
$('timeSlider').addEventListener('input',e=>setTime(e.target.value));
$('runBtn').addEventListener('click',run);
$('playBtn').addEventListener('click',()=>{
  if(state.playing){clearInterval(state.timer);state.playing=false;text('playBtn','▶');return}
  state.playing=true;text('playBtn','❚❚');if(+$('timeSlider').value>=100)$('timeSlider').value=0;
  state.timer=setInterval(()=>{let next=+$('timeSlider').value+2;if(next>100){clearInterval(state.timer);state.playing=false;text('playBtn','▶');next=100}
    $('timeSlider').value=next;setTime(next)},100);
});
window.addEventListener('resize',resize);resize();init();


/** Toggle between online, geographically anchored tiles and the original offline grid. */
function switchMapMode(enabled){
  if(!leafletView.map)return;
  leafletView.enabled=Boolean(enabled);
  canvas.style.display=enabled?'none':'block';
  $('leafletMap').style.display=enabled?'block':'none';
  $('mapMode').textContent=enabled?'OFFLINE GRID':'OPENSTREETMAP';
  $('mapHint').textContent=enabled?'DRAG TO PAN · SCROLL TO ZOOM · CLICK FOR CELL':'DRAG TO PAN · SCROLL TO ZOOM · HOVER FOR CELL';
  $('windBadge').hidden=!enabled||!(state.output&&state.output.inference.weather_summary);
  // Hide any stale hover card when switching rendering modes.
  $('mapTooltip').style.display='none';
  if(enabled){leafletView.map.invalidateSize();fitLeaflet()}
  else resize();
}

/** Fit the interactive map to inference candidates and observations; no label leakage. */
function fitLeaflet(){
  if(!leafletView.map||!state.output)return;
  const b=state.extent||getExtent();
  leafletView.map.fitBounds([[b.bottom,b.left],[b.top,b.right]],{
    padding:[26,26],maxZoom:13,animate:false
  });
}

/** Show inferred candidates as canvas-rendered geographic circles with individual scores. */
function renderLeafletCandidates(){
  if(!leafletView.layers||!state.output)return;
  const L=window.L,layer=leafletView.layers.candidates;
  layer.clearLayers();
  const cells=state.output.inference.candidate_cells;
  const maxScore=Math.max(1e-10,...cells.map(c=>+c.score_mass));
  for(const c of cells.slice().reverse()){
    const strength=Math.sqrt(Math.max(0,+c.score_mass/maxScore));
    const marker=L.circleMarker([+c.latitude,+c.longitude],{
      renderer:leafletView.renderer,radius:Math.max(2,4.3*strength),
      color:'#f2ad65',weight:0,fillColor:'#ed9852',
      fillOpacity:Math.max(.10,Math.min(.82,.66*strength))
    });
    marker.bindPopup(`<strong>Candidate #${Number(c.rank)}</strong><br>`+
      `${Number(c.latitude).toFixed(5)}, ${Number(c.longitude).toFixed(5)}<br>`+
      `Model score mass: ${Number(c.score_mass).toExponential(2)}<br>`+
      `In top-80 region: ${c.in_top80?'yes':'no'}<br>`+
      `<small>Score mass is not a calibrated probability.</small>`);
    layer.addLayer(marker);
  }
  leafletView.layers.landmarks.clearLayers();
  const inf=state.output.inference,b=inf.best_origin,base=inf.baseline_centroid;
  if(base){
    L.circleMarker([+base.latitude,+base.longitude],{renderer:leafletView.renderer,
      radius:8,color:'#ff8272',weight:2,fillColor:'#ff8272',fillOpacity:.25})
      .bindPopup('Earliest-hotspot centroid (baseline)').addTo(leafletView.layers.landmarks);
  }
  if(b){
    L.circleMarker([+b.latitude,+b.longitude],{renderer:leafletView.renderer,radius:9,
      color:'#f2ad65',weight:3,fillColor:'#fff',fillOpacity:1})
      .bindPopup('Highest-ranked model origin (not a confirmed ignition)').addTo(leafletView.layers.landmarks);
  }
  const wind=inf.weather_summary;
  $('windBadge').textContent=wind?'WIND TO '+fmt(wind.wind_to_deg,0)+'° · '+fmt(wind.wind_speed_mps,1)+' m/s':'';
  $('windBadge').hidden=!leafletView.enabled||!wind;
}

/** Replay only detections observed by the selected time, never future observations. */
function renderLeafletObservations(){
  if(!leafletView.layers)return;
  const layer=leafletView.layers.observations,L=window.L;
  layer.clearLayers();
  const all=state.observations.slice().sort((a,b)=>a.observed_utc.localeCompare(b.observed_utc));
  const count=Math.ceil(all.length*state.time);
  for(const d of all.slice(0,count)){
    const p=L.circleMarker([+d.latitude,+d.longitude],{renderer:leafletView.renderer,
      radius:4,color:'#102324',weight:1.2,fillColor:'#73ddd0',fillOpacity:.95});
    p.bindPopup(`Satellite thermal detection<br>${utc(d.observed_utc)}<br>`+
      `${Number(d.latitude).toFixed(5)}, ${Number(d.longitude).toFixed(5)}`);
    layer.addLayer(p);
  }
}

/** Render context separately; proximity to infrastructure never changes ranking. */
function renderLeafletContext(){
  if(!leafletView.layers)return;
  const L=window.L,layer=leafletView.layers.context;
  layer.clearLayers();
  if(!state.context)return;
  if(state.perimeter&&state.context.perimeter){
    L.geoJSON(state.context.perimeter,{style:{color:'#ff8272',weight:2,
      fillColor:'#ff8272',fillOpacity:.08}}).addTo(layer);
  }
  if(state.context.powerlines){
    L.geoJSON(state.context.powerlines,{style:{color:'#fae69d',weight:2.7,opacity:.9}})
      .bindPopup('Mapped infrastructure: proximity is not evidence of causation').addTo(layer);
  }
  for(const p of state.context.lightning||[]){
    L.circleMarker([+p.latitude,+p.longitude],{renderer:leafletView.renderer,
      radius:6,color:'#ff8272',weight:2,fillOpacity:.2})
      .bindPopup('Lightning observation (context only)').addTo(layer);
  }
}

/** Rebuild all georeferenced layers after inference, preserving current replay time. */
function renderLeafletAll(){
  if(!leafletView.layers)return;
  renderLeafletCandidates();renderLeafletObservations();renderLeafletContext();
}

/** Position the existing hover card without intercepting map interaction. */
function showLeafletHover(textContent, x, y){
  const tip=$('mapTooltip'),map=$('leafletMap');
  const width=map.clientWidth,height=map.clientHeight;
  tip.textContent=textContent;
  tip.style.display='block';
  tip.style.left=Math.max(6,Math.min(width-230,x+16))+'px';
  tip.style.top=Math.max(6,Math.min(height-76,y+15))+'px';
}

/** Hit-test rendered geographic markers directly, independent of Leaflet popup/canvas events.
 * The original offline canvas uses its own hover handler; this restores equivalent
 * hover details on the OpenStreetMap view, giving the white origin marker priority.
 */
function hoverLeaflet(event){
  if(!leafletView.enabled||!leafletView.map||!state.output)return;
  const mapElement=$('leafletMap'),r=mapElement.getBoundingClientRect();
  const x=event.clientX-r.left,y=event.clientY-r.top;
  const tip=$('mapTooltip');
  if(x<0||y<0||x>=r.width||y>=r.height){tip.style.display='none';return}
  const m=leafletView.map;
  const distance=(lat,lon)=>{
    const p=m.latLngToContainerPoint([Number(lat),Number(lon)]);
    return Math.hypot(x-p.x,y-p.y);
  };
  // Best inferred cell gets priority even if candidate or hotspot layers overlap it.
  const origin=state.output.inference.best_origin;
  if(origin&&distance(origin.latitude,origin.longitude)<=18){
    showLeafletHover('INFERRED ORIGIN · '+fmt(origin.latitude,4)+', '+
      fmt(origin.longitude,4)+' · '+utc(origin.estimated_ignition_utc),x,y);
    return;
  }
  // Keep satellite observations hoverable during the historical replay.
  const visible=Math.ceil(state.observations.length*state.time);
  const observations=state.observations.slice().sort((a,b)=>a.observed_utc.localeCompare(b.observed_utc));
  for(const d of observations.slice(0,visible)){
    if(distance(d.latitude,d.longitude)<=8){
      showLeafletHover('OBSERVED HOTSPOT · '+utc(d.observed_utc)+' · '+
        fmt(d.latitude,4)+', '+fmt(d.longitude,4),x,y);
      return;
    }
  }
  let nearest=null,closest=11;
  for(const c of state.output.inference.candidate_cells){
    const d=distance(c.latitude,c.longitude);
    if(d<closest){nearest=c;closest=d;}
  }
  if(nearest){
    showLeafletHover('CANDIDATE #'+nearest.rank+' · '+fmt(nearest.latitude,4)+', '+
      fmt(nearest.longitude,4)+' · score '+Number(nearest.score_mass).toExponential(2)+
      ' · top-80: '+(nearest.in_top80?'yes':'no'),x,y);
  }else{tip.style.display='none';}
}

/** Initialise the map only after first remote tile arrives; offline grid stays usable. */
function initLeaflet(){
  if(!window.L)return;
  const L=window.L,el=$('leafletMap');
  el.style.display='block'; // Size Leaflet correctly while Canvas remains visually in front.
  const map=L.map(el,{preferCanvas:true,zoomControl:false,worldCopyJump:false});
  L.control.zoom({position:'bottomright'}).addTo(map);
  leafletView.map=map;
  // Listen at the DOM level: thousands of Canvas-backed Leaflet circles may not
  // dispatch individual hover events reliably when densely overlapping.
  $('leafletMap').addEventListener('pointermove',hoverLeaflet);
  $('leafletMap').addEventListener('pointerleave',()=>{$('mapTooltip').style.display='none'});
  leafletView.renderer=L.canvas({padding:.25});
  leafletView.layers={candidates:L.layerGroup().addTo(map),context:L.layerGroup().addTo(map),
    observations:L.layerGroup().addTo(map),landmarks:L.layerGroup().addTo(map)};
  // This is a geographic basemap only; OSM does not provide historic fire evidence.
  const tiles=L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{
    minZoom:3,maxZoom:18,attribution:'&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> contributors'
  }).addTo(map);
  map.setView([39.85,-121.48],10);
  if(state.output){renderLeafletAll();fitLeaflet()}
  tiles.on('tileload',()=>{
    if(leafletView.loadedTiles)return;
    leafletView.loadedTiles=true;$('mapMode').disabled=false;switchMapMode(true);
  });
  tiles.on('tileerror',()=>{
    if(!leafletView.loadedTiles&&++leafletView.tileErrors>=8){
      $('mapMode').textContent='GRID · OFFLINE';$('mapMode').disabled=true;
    }
  });
  // The canvas stays on top until a real tile loads, not an empty grey map.
}

/** Load Leaflet lazily so blocked CDNs never break reconstruction or replay. */
function loadGeographicBasemap(){
  const css=document.createElement('link');css.rel='stylesheet';
  css.href='https://unpkg.com/leaflet@1.9.4/dist/leaflet.css';
  css.integrity='sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=';
  css.crossOrigin='anonymous';
  const script=document.createElement('script');script.async=true;
  script.src='https://unpkg.com/leaflet@1.9.4/dist/leaflet.js';
  script.integrity='sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=';
  script.crossOrigin='anonymous';
  script.onload=initLeaflet;
  script.onerror=()=>{$('mapMode').textContent='GRID · OFFLINE';$('mapMode').disabled=true};
  css.onload=()=>document.head.append(script);
  css.onerror=()=>{$('mapMode').textContent='GRID · OFFLINE';$('mapMode').disabled=true};
  document.head.append(css);
}
loadGeographicBasemap();
