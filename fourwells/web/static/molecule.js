/* Offline PDB C-alpha viewer: no CDN, network service or fabricated coordinates. */
window.AntibodyPDB = {mount: async function(id, url, meta) {
  const node = document.getElementById(id); if (!node) return;
  try {
    const r = await fetch(url); if (!r.ok) throw Error('Saved structure could not be loaded');
    const data = await r.json(), points = data.atoms.filter(a => a.name === 'CA');
    if (!points.length) throw Error('No C-alpha coordinates in this PDB');
    const chains = [...new Set(points.map(a => a.chain))], visible = new Set(chains);
    node.innerHTML = '<div class="chain-controls"></div><canvas width="900" height="450" aria-label="Interactive molecular C-alpha trace"></canvas><p class="muted"></p>';
    const controls = node.querySelector('div'), canvas = node.querySelector('canvas'), ctx = canvas.getContext('2d');
    node.querySelector('p').textContent = (meta.model || 'Saved PDB') + ' · ' + points.length + ' residues. Red: supplied CDR residue mapping, when present.';
    chains.forEach((c,i) => { const label=document.createElement('label'), input=document.createElement('input'); input.type='checkbox'; input.checked=true; input.onchange=()=>{input.checked?visible.add(c):visible.delete(c);draw();}; label.append(input,document.createTextNode(' chain '+c+' ')); controls.append(label); });
    const center = [0,1,2].map(i=>points.reduce((s,p)=>s+p.xyz[i],0)/points.length);
    const radius = Math.max(...points.map(p=>Math.hypot(...p.xyz.map((v,i)=>v-center[i]))),1);
    const colors=['#4b9bff','#ffb347','#62d5a5','#bd91ff','#e59abf'];
    let ax=0, ay=0, zoom=1, down=null;
    function draw() {
      ctx.fillStyle='#111827';ctx.fillRect(0,0,900,450);
      let last={};
      points.forEach(p=>{
        if(!visible.has(p.chain))return;
        let [x,y,z]=p.xyz.map((v,i)=>v-center[i]);
        let yy=y*Math.cos(ax)-z*Math.sin(ax), zz=y*Math.sin(ax)+z*Math.cos(ax);
        let xx=x*Math.cos(ay)+zz*Math.sin(ay); const scale=190/radius*zoom;
        let q=[450+xx*scale,225+yy*scale], prev=last[p.chain];
        const cdr=(meta.cdr_regions||[]).some(c=>c.chain===p.chain && (c.residues||[]).map(String).includes(p.residue));
        ctx.strokeStyle=cdr?'#ff5964':colors[chains.indexOf(p.chain)%colors.length];ctx.lineWidth=cdr?4:2;
        if(prev && Math.hypot(...p.xyz.map((v,i)=>v-prev.atom.xyz[i]))<4.8){ctx.beginPath();ctx.moveTo(...prev.q);ctx.lineTo(...q);ctx.stroke();}
        ctx.fillStyle=ctx.strokeStyle;ctx.beginPath();ctx.arc(...q,cdr?3:1.5,0,Math.PI*2);ctx.fill();
        last[p.chain]={q:q,atom:p};
      });
    }
    canvas.onpointerdown=e=>{down=[e.clientX,e.clientY];canvas.setPointerCapture(e.pointerId);};
    canvas.onpointerup=()=>down=null;
    canvas.onpointermove=e=>{if(!down)return;ay+=(e.clientX-down[0])*0.01;ax+=(e.clientY-down[1])*0.01;down=[e.clientX,e.clientY];draw();};
    canvas.onwheel=e=>{e.preventDefault();zoom=Math.max(0.2,Math.min(6,zoom*Math.exp(-e.deltaY*0.001)));draw();};draw();
  } catch(e) { node.textContent=e.message; }
}};
