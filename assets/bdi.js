// ═══════════════════════════════════════════════════════════════
//  BDI FRONTEND ENGINE v4.0
//  Reads from /data/latest.json (updated daily by GitHub Actions)
//  No CORS proxies needed — pure static file read
// ═══════════════════════════════════════════════════════════════

window.BDI = {

  fmt: n => Math.round(n).toLocaleString('en-US'),
  pct: (c,p) => (((c-p)/p)*100).toFixed(2),

  chg: function(val, change) {
    const up = change >= 0, sign = up ? '+' : '';
    return { text: `${up?'▲':'▼'} ${sign}${this.fmt(change)} pts`, up };
  },

  chgSimple: function(val, change) {
    const up = change >= 0, sign = up ? '+' : '';
    const prev = val - change;
    const p = prev ? ((change/prev)*100).toFixed(2) : '0.00';
    return { text: `${up?'▲':'▼'} ${sign}${this.fmt(change)} (${sign}${p}%)`, up };
  },

  fmtDate: function(s) {
    try { return new Date(s+'T00:00:00').toLocaleDateString('en-GB',{day:'numeric',month:'short',year:'numeric'}); }
    catch(e) { return s; }
  },

  el: function(id,val) { const e=document.getElementById(id); if(e) e.textContent=val; },
  elClass: function(id,cls) { const e=document.getElementById(id); if(e) e.className=cls; },

  setHero: function(data) {
    const bdi=data.bdi;
    this.el('bdi-val', this.fmt(bdi.value));
    const ch = this.chg(bdi.value, bdi.change);
    const sign = bdi.change >= 0 ? '+' : '';
    this.el('bdi-change', `${ch.text}  ${sign}${bdi.pct}%`);
    this.elClass('bdi-change', 'bdi-change '+(ch.up?'up':'dn'));
    this.el('bdi-ts', this.fmtDate(data.date)+' · Baltic Exchange');
  },

  setSub: function(valId, chgId, index) {
    this.el(valId, this.fmt(index.value));
    const ch = this.chgSimple(index.value, index.change);
    this.el(chgId, ch.text);
    this.elClass(chgId, 'sub-change '+(ch.up?'up':'dn'));
  },

  buildTicker: function(data) {
    const indices = [
      {name:'BDI',  obj:data.bdi},
      {name:'BCI',  obj:data.bci},
      {name:'BPI',  obj:data.bpi},
      {name:'BSI',  obj:data.bsi},
      {name:'BHSI', obj:data.bhsi},
    ];
    const stocks = [
      {name:'SBLK', cur:14.22, chg:0.34, dollar:true},
      {name:'GOGL', cur:11.87, chg:-0.09, dollar:true},
      {name:'EGLE', cur:42.10, chg:0.88, dollar:true},
      {name:'IRON ORE', cur:106.40, chg:-1.20, dollar:true},
      {name:'COAL', cur:118.75, chg:0.55, dollar:true},
    ];

    const items = [
      ...indices.map(({name, obj}) => {
        const up=obj.change>=0, sign=up?'+':'';
        return `<div class="ticker-item"><span class="t-name">${name}</span><span class="t-val">${this.fmt(obj.value)}</span><span class="${up?'up':'dn'}">${up?'▲':'▼'} ${sign}${this.fmt(obj.change)}</span></div>`;
      }),
      ...stocks.map(s => {
        const up=s.chg>=0, sign=up?'+':'';
        return `<div class="ticker-item"><span class="t-name">${s.name}</span><span class="t-val">$${s.cur.toFixed(2)}</span><span class="${up?'up':'dn'}">${up?'▲':'▼'} ${sign}${s.chg.toFixed(2)}</span></div>`;
      })
    ];
    const el=document.getElementById('tickerTrack');
    if(el) el.innerHTML=[...items,...items].join('');
  },

  filterRange: function(data, range) {
    if(range==='ALL'||!data.length) return data;
    const last=new Date(data[data.length-1].date+'T00:00:00');
    const cut=new Date(last);
    if(range==='1M') cut.setMonth(cut.getMonth()-1);
    if(range==='3M') cut.setMonth(cut.getMonth()-3);
    if(range==='1Y') cut.setFullYear(cut.getFullYear()-1);
    if(range==='5Y') cut.setFullYear(cut.getFullYear()-5);
    return data.filter(d=>new Date(d.date+'T00:00:00')>=cut);
  },

  renderChart: function(histData, range, canvasId, existingChart) {
    const filtered=this.filterRange(histData,range);
    if(!filtered.length) return null;
    const canvas=document.getElementById(canvasId);
    if(!canvas) return null;
    const skeleton=document.getElementById('chartSkeleton');
    if(skeleton) skeleton.style.display='none';
    canvas.style.display='block';
    const tickLabels=filtered.map(d=>{
      const dt=new Date(d.date+'T00:00:00');
      return (range==='1M'||range==='3M')
        ? dt.toLocaleDateString('en-GB',{day:'numeric',month:'short'})
        : dt.toLocaleDateString('en-GB',{month:'short',year:'numeric'});
    });
    const values=filtered.map(d=>d.value);
    const ctx=canvas.getContext('2d');
    const grad=ctx.createLinearGradient(0,0,0,300);
    grad.addColorStop(0,'rgba(200,168,75,0.22)');
    grad.addColorStop(1,'rgba(200,168,75,0)');
    if(existingChart) existingChart.destroy();
    const self=this;
    return new Chart(ctx,{
      type:'line',
      data:{labels:tickLabels,datasets:[{data:values,borderColor:'#c8a84b',borderWidth:1.5,backgroundColor:grad,fill:true,tension:0.3,pointRadius:0,pointHoverRadius:4,pointHoverBackgroundColor:'#c8a84b',pointHoverBorderColor:'#fff',pointHoverBorderWidth:2}]},
      options:{
        responsive:true,maintainAspectRatio:false,
        interaction:{mode:'index',intersect:false},
        plugins:{
          legend:{display:false},
          tooltip:{
            backgroundColor:'#0f1318',borderColor:'#252e3a',borderWidth:1,
            titleColor:'#c8a84b',bodyColor:'#d4dbe8',
            titleFont:{family:"'IBM Plex Mono'",size:11,weight:'500'},
            bodyFont:{family:"'IBM Plex Mono'",size:13,weight:'500'},
            padding:12,
            callbacks:{
              title:items=>{
                const dt=new Date(filtered[items[0].dataIndex].date+'T00:00:00');
                return dt.toLocaleDateString('en-GB',{weekday:'short',day:'numeric',month:'long',year:'numeric'});
              },
              label:c=>`  BDI   ${self.fmt(c.parsed.y)}`
            }
          }
        },
        scales:{
          x:{grid:{color:'rgba(30,37,48,0.7)'},ticks:{color:'#3d4a5c',font:{family:"'IBM Plex Mono'",size:10},maxTicksLimit:9},border:{display:false}},
          y:{position:'right',grid:{color:'rgba(30,37,48,0.7)'},ticks:{color:'#3d4a5c',font:{family:"'IBM Plex Mono'",size:10},callback:v=>self.fmt(v)},border:{display:false}}
        }
      }
    });
  },

  drawSpark: function(id, color, histData) {
    const canvas=document.getElementById(id);
    if(!canvas) return;
    const w=canvas.offsetWidth||200,h=28;
    canvas.width=w; canvas.height=h;
    const ctx=canvas.getContext('2d');
    ctx.clearRect(0,0,w,h);
    // Only draw a sparkline once we have enough REAL points. No synthetic noise.
    if(!histData || histData.length<8) return;
    const recent=histData.slice(-30);
    const mn=Math.min(...recent.map(d=>d.value)),mx=Math.max(...recent.map(d=>d.value));
    const pts=recent.map((d,i)=>({x:(i/(recent.length-1))*w,y:h-3-((d.value-mn)/(mx-mn+1))*(h-6)}));
    ctx.beginPath();
    pts.forEach((p,i)=>i===0?ctx.moveTo(p.x,p.y):ctx.lineTo(p.x,p.y));
    ctx.strokeStyle=color; ctx.lineWidth=1.5; ctx.stroke();
  },

  subscribe: function(emailId) {
    const e=document.getElementById(emailId)||document.getElementById('alertEmail');
    if(!e||!e.value||!e.value.includes('@')){alert('Please enter a valid email.');return;}
    alert(`✓ Subscribed! Daily BDI alerts will be sent to ${e.value}`);
    e.value='';
  },

  // Fetch the REAL growing history series written daily by update_bdi.py.
  // Returns [{date, value}] (value = BDI). Empty array if not present yet.
  loadHistory: async function() {
    try {
      const r = await fetch('/data/history.json?t=' + Date.now(), { cache: 'no-store' });
      if(!r.ok) return [];
      const raw = await r.json();
      const rows = Array.isArray(raw) ? raw : (raw.series || []);
      return rows
        .filter(x => x && x.date && (x.bdi != null || x.value != null))
        .map(x => ({ date: x.date, value: x.bdi != null ? x.bdi : x.value }));
    } catch(e) { return []; }
  },

  load: async function(callback) {
    const statusEl=document.getElementById('chartStatus');
    const skeleton=document.getElementById('chartSkeleton');
    try {
      const r=await fetch('/data/latest.json?t=' + Date.now(), { cache: 'no-store' });
      if(!r.ok) throw new Error('not found');
      const d=await r.json();
      const history=await this.loadHistory();
      const daysDiff=(new Date()-new Date(d.date+'T00:00:00'))/86400000;
      const isStale=daysDiff>5;
      const live={bdi:d.bdi,bci:d.bci,bpi:d.bpi,bsi:d.bsi,bhsi:d.bhsi,date:d.date,updated:d.updated,history:history,live:!isStale};
      if(callback) callback(live);
      if(statusEl){
        statusEl.textContent=isStale?`Last confirmed: ${this.fmtDate(d.date)}`:`● Live · ${this.fmtDate(d.date)}`;
        statusEl.className='chart-status'+(isStale?'':' live');
      }
      // Thin-history state: show an honest message instead of an empty chart.
      if(history.length < 2 && skeleton){
        skeleton.style.display='flex';
        skeleton.textContent='Chart is building — we log the BDI every trading day and the history grows daily.';
        const cv=document.getElementById('bdiChart'); if(cv) cv.style.display='none';
      }
      return live;
    } catch(err) {
      if(statusEl){statusEl.textContent='Data temporarily unavailable';statusEl.className='chart-status';}
      if(skeleton){skeleton.style.display='flex';skeleton.textContent='Live data temporarily unavailable — please refresh shortly.';}
      const fb={bdi:{value:0,change:0,pct:0},bci:{value:0,change:0,pct:0},bpi:{value:0,change:0,pct:0},bsi:{value:0,change:0,pct:0},bhsi:{value:0,change:0,pct:0},date:'',history:[],live:false};
      if(callback) callback(fb);
      return fb;
    }
  }
};
