// --------------------------- State ---------------------------
const state = {
  yaw_x: 0, yaw_y: 0, yaw_z: 0,
  acc_x: 0, acc_y: 0, acc_z: 0,
  vel: 0, alt: 0, temp: 0, pres: 0,
  ts: 0
};

const hist = {
  t: [],
  alt: [],
  temp: [],
  pres: []
};

const MAX_POINTS = 200;
let autoRefresh = true;
let refreshHz = 10;
let lastUpdateTs = 0;
let port = null;
let reader = null;
let readingLoop = null;
let simTimer = null;

// --------------------------- DOM ---------------------------
const els = {
  btnChoosePort: document.getElementById('btn-choose-port'),
  btnConnect: document.getElementById('btn-connect'),
  btnDisconnect: document.getElementById('btn-disconnect'),
  portName: document.getElementById('port-name'),
  baud: document.getElementById('baud'),
  autoRefresh: document.getElementById('auto-refresh'),
  refreshHz: document.getElementById('refresh-hz'),
  hzLabel: document.getElementById('hz-label'),
  charts: {
    alt: document.getElementById('alt-chart'),
    temp: document.getElementById('temp-chart'),
    pres: document.getElementById('pres-chart')
  },
  attitude: document.getElementById('attitude'),
  metrics: {
    alt: document.getElementById('m-alt'),
    temp: document.getElementById('m-temp'),
    pres: document.getElementById('m-pres'),
    ax: document.getElementById('m-ax'),
    ay: document.getElementById('m-ay'),
    az: document.getElementById('m-az'),
    yx: document.getElementById('m-yx'),
    yy: document.getElementById('m-yy'),
    yz: document.getElementById('m-yz'),
    lag: document.getElementById('m-lag'),
    // attitude plot container:
    attitudePlot: document.getElementById('attitude-plot')
  }
};

// --------------------------- Utils ---------------------------
function clampHistory() {
  ['t','alt','temp','pres'].forEach(k => {
    if (hist[k].length > MAX_POINTS) hist[k] = hist[k].slice(-MAX_POINTS);
  });
}

function rad(deg){ return deg * Math.PI / 180; }

function zyxRotationMatrix(yawDeg, pitchDeg, rollDeg) {
  const z = rad(yawDeg), y = rad(pitchDeg), x = rad(rollDeg);
  const cz = Math.cos(z), sz = Math.sin(z);
  const cy = Math.cos(y), sy = Math.sin(y);
  const cx = Math.cos(x), sx = Math.sin(x);
  const Rz = [
    [cz, -sz, 0],
    [sz,  cz, 0],
    [ 0,   0, 1]
  ];
  const Ry = [
    [ cy, 0, sy],
    [  0, 1,  0],
    [-sy, 0, cy]
  ];
  const Rx = [
    [1, 0, 0],
    [0, cx,-sx],
    [0, sx, cx]
  ];
  return matMul(matMul(Rz, Ry), Rx);
}

function matMul(A,B){
  const r = A.length, c = B[0].length, n = B.length;
  const out = Array.from({length: r}, () => Array(c).fill(0));
  for (let i=0;i<r;i++){
    for (let j=0;j<c;j++){
      let sum = 0;
      for (let k=0;k<n;k++) sum += A[i][k]*B[k][j];
      out[i][j] = sum;
    }
  }
  return out;
}

function makeCylinder(R=0.033, H=0.115, nTheta=80, nZ=40) {
  const theta = Array.from({length: nTheta}, (_,i)=> i*(2*Math.PI)/(nTheta-1));
  const z = Array.from({length: nZ}, (_,i)=> -H/2 + i*(H/(nZ-1)));
  const X = [], Y = [], Z = [];
  for (let zi=0; zi<nZ; zi++){
    const rowX=[], rowY=[], rowZ=[];
    for (let ti=0; ti<nTheta; ti++){
      rowX.push(R * Math.cos(theta[ti]));
      rowY.push(R * Math.sin(theta[ti]));
      rowZ.push(z[zi]);
    }
    X.push(rowX); Y.push(rowY); Z.push(rowZ);
  }
  return {X,Y,Z};
}

function rotateMesh(X, Y, Z, R){
  const m = X.length, n = X[0].length;
  const x2 = Array.from({length:m}, ()=>Array(n).fill(0));
  const y2 = Array.from({length:m}, ()=>Array(n).fill(0));
  const z2 = Array.from({length:m}, ()=>Array(n).fill(0));
  for (let i=0;i<m;i++){
    for (let j=0;j<n;j++){
      const x = X[i][j], y = Y[i][j], z = Z[i][j];
      x2[i][j] = R[0][0]*x + R[0][1]*y + R[0][2]*z;
      y2[i][j] = R[1][0]*x + R[1][1]*y + R[1][2]*z;
      z2[i][j] = R[2][0]*x + R[2][1]*y + R[2][2]*z;
    }
  }
  return {x2,y2,z2};
}

function rotateVec(vec, R){
  const [x,y,z] = vec;
  return [
    R[0][0]*x + R[0][1]*y + R[0][2]*z,
    R[1][0]*x + R[1][1]*y + R[1][2]*z,
    R[2][0]*x + R[2][1]*y + R[2][2]*z
  ];
}

// Parse lines like: Data: A-450; T-27.5; X-5; YX-10; YY-5; YZ-2
function parseSerialLine(s) {
  const out = {alt:0,temp:0,pres:0,acc_x:0,acc_y:0,acc_z:0,yaw_x:0,yaw_y:0,yaw_z:0};
  s = (s||"").trim();
  if (!s.includes("Data")) return out;
  if (s.startsWith("Data:")) s = s.slice(5).trim();
  const parts = s.split(";").map(p=>p.trim()).filter(Boolean);
  for (const p of parts){
    if (!p.includes("-")) continue;
    const [key, val] = p.split("-", 2);
    const f = parseFloat(val);
    if (Number.isNaN(f)) continue;
    if (key==="A") out.alt = f;
    else if (key==="T") out.temp = f;
    else if (key==="P") out.pres = f;
    else if (key==="X") out.acc_x = f;
    else if (key==="Y") out.acc_y = f;
    else if (key==="Z") out.acc_z = f;
    else if (key==="YX") out.yaw_x = f;
    else if (key==="YY") out.yaw_y = f;
    else if (key==="YZ") out.yaw_z = f;
  }
  return out;
}

// --------------------------- Charts ---------------------------
function initCharts(){
  const layoutSmall = title => ({
    title,
    margin: {l:20,r:20,t:30,b:20},
    height: 200,
    paper_bgcolor: 'rgba(0,0,0,0)',
    plot_bgcolor: 'rgba(0,0,0,0)',
    xaxis: {visible:false},
    yaxis: {zeroline:false, gridcolor:'#22314c'}
  });

  Plotly.newPlot('alt-chart', [{ y: [], mode: 'lines' }], layoutSmall('Altitude (m)'), {displayModeBar:false, responsive:true});
  Plotly.newPlot('temp-chart', [{ y: [], mode: 'lines' }], layoutSmall('Temperature (°C)'), {displayModeBar:false, responsive:true});
  Plotly.newPlot('pres-chart', [{ y: [], mode: 'lines' }], layoutSmall('Pressure (hPa)'), {displayModeBar:false, responsive:true});
}

const cylinder = makeCylinder(0.033, 0.115, 80, 40);

function initAttitude(){
  // initial at identity
  const Rm = zyxRotationMatrix(0,0,0);
  const {x2, y2, z2} = rotateMesh(cylinder.X, cylinder.Y, cylinder.Z, Rm);

  // axes (like streamlit version)
  const L = 0.08;
  const axes = {
    X: [[0,L,NaN],[0,0,NaN],[0,0,NaN]],
    Y: [[0,0,NaN],[0,L,NaN],[0,0,NaN]],
    Z: [[0,0,NaN],[0,0,NaN],[0,L,NaN]]
  };
  const traces = [];
  for (const name of Object.keys(axes)){
    const V = [axes[name][0][1], axes[name][1][1], axes[name][2][1]];
    const vrot = rotateVec(V, Rm);
    traces.push({
      type: 'scatter3d', mode: 'lines',
      x: [0, vrot[0], NaN], y:[0, vrot[1], NaN], z:[0, vrot[2], NaN],
      line: {width: 6}, showlegend:false
    });
    traces.push({
      type: 'scatter3d', mode: 'text',
      x:[vrot[0]], y:[vrot[1]], z:[vrot[2]],
      text:[name], showlegend:false
    });
  }

  const surface = {
    type: 'surface',
    x: x2, y: y2, z: z2,
    opacity: 0.9, showscale: false
  };

  const layout = {
    title: `YawX 0.0°, YawY 0.0°, YawZ 0.0°`,
    margin: {l:0,r:0,t:30,b:0},
    paper_bgcolor: 'rgba(0,0,0,0)',
    scene: {
      xaxis: {range:[-0.12,0.12], backgroundcolor:'rgba(0,0,0,0)', gridcolor:'#22314c'},
      yaxis: {range:[-0.12,0.12], backgroundcolor:'rgba(0,0,0,0)', gridcolor:'#22314c'},
      zaxis: {range:[-0.12,0.12], backgroundcolor:'rgba(0,0,0,0)', gridcolor:'#22314c'}
    }
  };

  Plotly.newPlot('attitude-plot', [surface, ...traces], layout, {displayModeBar:false, responsive:true});
}

function updateCharts(){
  Plotly.update('alt-chart', { y: [hist.alt] });
  Plotly.update('temp-chart', { y: [hist.temp] });
  Plotly.update('pres-chart', { y: [hist.pres] });
}

function updateAttitude(){
  const Rm = zyxRotationMatrix(state.yaw_z, state.yaw_y, state.yaw_x);
  const {x2, y2, z2} = rotateMesh(cylinder.X, cylinder.Y, cylinder.Z, Rm);

  // Recompute axes endpoints
  const L = 0.08;
  const axes = {
    X: [0,L,0,0,0,0],
    Y: [0,0,0,0,L,0],
    Z: [0,0,0,0,0,L]
  };
  const Xv = rotateVec([L,0,0], Rm);
  const Yv = rotateVec([0,L,0], Rm);
  const Zv = rotateVec([0,0,L], Rm);

  const dataUpdates = [
    {x: [x2], y: [y2], z: [z2]}, // surface (trace 0)
    {x: [[0, Xv[0], NaN]], y: [[0, Xv[1], NaN]], z: [[0, Xv[2], NaN]]}, // X axis line (1)
    {x: [[Xv[0]]], y: [[Xv[1]]], z: [[Xv[2]]]}, // X label (2)
    {x: [[0, Yv[0], NaN]], y: [[0, Yv[1], NaN]], z: [[0, Yv[2], NaN]]}, // Y axis line (3)
    {x: [[Yv[0]]], y: [[Yv[1]]], z: [[Yv[2]]]}, // Y label (4)
    {x: [[0, Zv[0], NaN]], y: [[0, Zv[1], NaN]], z: [[0, Zv[2], NaN]]}, // Z axis line (5)
    {x: [[Zv[0]]], y: [[Zv[1]]], z: [[Zv[2]]]}  // Z label (6)
  ];

  Plotly.update('attitude-plot',
    {x: dataUpdates.map(d=>d.x).flat(), y: dataUpdates.map(d=>d.y).flat(), z: dataUpdates.map(d=>d.z).flat()},
    {title: `YawX ${state.yaw_x.toFixed(1)}°, YawY ${state.yaw_y.toFixed(1)}°, YawZ ${state.yaw_z.toFixed(1)}°`}
  );
}

// --------------------------- Telemetry UI ---------------------------
function updateMetrics(){
  els.metrics.alt.textContent = state.alt.toFixed(2);
  els.metrics.temp.textContent = state.temp.toFixed(2);
  els.metrics.pres.textContent = state.pres.toFixed(2);
  els.metrics.ax.textContent = state.acc_x.toFixed(2);
  els.metrics.ay.textContent = state.acc_y.toFixed(2);
  els.metrics.az.textContent = state.acc_z.toFixed(2);
  els.metrics.yx.textContent = state.yaw_x.toFixed(2);
  els.metrics.yy.textContent = state.yaw_y.toFixed(2);
  els.metrics.yz.textContent = state.yaw_z.toFixed(2);

  const lag = Math.max(0, (Date.now()/1000 - state.ts));
  els.metrics.lag.textContent = lag.toFixed(1);
}

// --------------------------- Data Pump ---------------------------
function pushHistory(){
  hist.t.push(Date.now()/1000);
  hist.alt.push(state.alt);
  hist.temp.push(state.temp);
  hist.pres.push(state.pres);
  clampHistory();
}

function stepUI(){
  // (autoRefresh OR new data) -> update
  updateMetrics();
  updateCharts();
  updateAttitude();
}

let refreshTimer = null;
function setRefreshLoop(hz){
  if (refreshTimer) clearInterval(refreshTimer);
  const periodMs = Math.max(10, Math.floor(1000 / Math.max(1, hz)));
  refreshTimer = setInterval(()=>{
    if (!autoRefresh) return;
    pushHistory();
    stepUI();
  }, periodMs);
}

// --------------------------- Web Serial ---------------------------
const hasWebSerial = 'serial' in navigator;

async function choosePort(){
  if (!hasWebSerial){
    alert('Web Serial API not supported in this browser. Use Chrome, Edge, or Opera.');
    return;
  }
  try{
    const p = await navigator.serial.requestPort({});
    port = p;
    els.portName.textContent = port.getInfo ? JSON.stringify(port.getInfo()) : '(selected)';
    els.btnConnect.disabled = false;
  }catch(err){
    console.warn(err);
  }
}

async function connect(){
  if (!port) return;
  try{
    els.btnConnect.disabled = true;
    const baudRate = parseInt(els.baud.value, 10);
    await port.open({ baudRate });
    const textDecoder = new TextDecoderStream();
    const readableClosed = port.readable.pipeTo(textDecoder.writable);
    reader = textDecoder.readable.getReader();

    els.btnDisconnect.disabled = false;

    // Stop simulator if running
    if (simTimer) { clearInterval(simTimer); simTimer = null; }

    if (readingLoop) { /* no-op */ }
    readingLoop = (async () => {
      let buffer = '';
      try{
        while (port.readable){
          const { value, done } = await reader.read();
          if (done) break;
          buffer += value;
          let idx;
          while ((idx = buffer.indexOf('\n')) >= 0){
            const line = buffer.slice(0, idx).trim();
            buffer = buffer.slice(idx+1);
            if (!line) continue;
            console.log('[SERIAL]', line);
            const fields = parseSerialLine(line);
            Object.assign(state, {
              yaw_x: fields.yaw_x, yaw_y: fields.yaw_y, yaw_z: fields.yaw_z,
              acc_x: fields.acc_x, acc_y: fields.acc_y, acc_z: fields.acc_z,
              alt: fields.alt, temp: fields.temp, pres: fields.pres,
              ts: Date.now()/1000
            });
            lastUpdateTs = state.ts;
            // Immediate UI bump on fresh data
            pushHistory();
            stepUI();
          }
        }
      }catch(e){
        console.error(e);
      }finally{
        try{ reader.releaseLock(); }catch(_){}
      }
    })();
  }catch(err){
    console.error(err);
    alert('Failed to open port: ' + err.message);
    els.btnConnect.disabled = false;
  }
}

async function disconnect(){
  try{
    if (reader){
      try{ await reader.cancel(); }catch(_){}
      try{ reader.releaseLock(); }catch(_){}
      reader = null;
    }
    if (port){
      try{ await port.close(); }catch(_){}
    }
  }finally{
    els.btnDisconnect.disabled = true;
    els.btnConnect.disabled = !port;
  }
}

// --------------------------- Simulator ---------------------------
function startSimulator(){
  if (simTimer) return;
  let t = 0;
  simTimer = setInterval(()=>{
    // create smooth changing values
    t += 1/refreshHz;
    const alt = 100 + 10*Math.sin(t*0.8);
    const temp = 25 + 2*Math.cos(t*0.5);
    const pres = 1013 + 5*Math.sin(t*0.3);
    const ax = 0.5*Math.sin(t*1.7);
    const ay = 0.5*Math.cos(t*1.2);
    const az = 9.81 + 0.2*Math.sin(t*2.2);
    const yx = 15*Math.sin(t*0.9);
    const yy = 10*Math.cos(t*0.7);
    const yz = (t*20) % 360;

    Object.assign(state, { alt, temp, pres, acc_x:ax, acc_y:ay, acc_z:az, yaw_x:yx, yaw_y:yy, yaw_z:yz, ts: Date.now()/1000 });
  }, Math.max(10, Math.floor(1000 / Math.max(1, refreshHz))));
}

// --------------------------- Events ---------------------------
els.btnChoosePort.addEventListener('click', choosePort);
els.btnConnect.addEventListener('click', connect);
els.btnDisconnect.addEventListener('click', disconnect);

els.autoRefresh.addEventListener('change', (e)=>{
  autoRefresh = !!e.target.checked;
});

els.refreshHz.addEventListener('input', (e)=>{
  refreshHz = parseInt(e.target.value, 10);
  els.hzLabel.textContent = refreshHz.toString();
  setRefreshLoop(refreshHz);
  // adjust simulator step to feel consistent
  if (!reader) { if (simTimer){ clearInterval(simTimer); simTimer=null; } startSimulator(); }
});

// --------------------------- Init ---------------------------
(function init(){
  initCharts();
  initAttitude();
  autoRefresh = els.autoRefresh.checked;
  refreshHz = parseInt(els.refreshHz.value, 10);
  els.hzLabel.textContent = refreshHz.toString();
  setRefreshLoop(refreshHz);

  // If Web Serial not available, keep connect disabled
  if (!('serial' in navigator)) {
    els.btnChoosePort.disabled = true;
    els.btnConnect.disabled = true;
    els.portName.textContent = '(Web Serial not supported)';
  }

  // Start simulator by default (until a port connects)
  startSimulator();
})();
