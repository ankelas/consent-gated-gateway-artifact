"""Data-backed native draw.io figures; one geometry source for XML, SVG and PNG.

All labels, nodes, edges, axes and marks remain native editable mxCells.
No embedded bitmap is used in a .drawio file. Regeneration overwrites generated
files; preserve manual edits under a new name. PNG is a 3x preview/export.
"""
from pathlib import Path
import csv, math, json, hashlib, statistics
import xml.etree.ElementTree as E
from PIL import Image, ImageDraw, ImageFont

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'figures'; SRC=ROOT/'drawio'; DATA=ROOT.parent/'experiments/data'
OUT.mkdir(exist_ok=True); SRC.mkdir(exist_ok=True)
INK='#203448'; GRAY='#586B7B'; GRID='#DCE4EA'; BLUE='#28658D'; TEAL='#14877F'; RED='#B54C41'; GOLD='#B97712'
PALE='#EDF4F8'; MINT='#EAF5F2'; WARM='#FCF4E6'
FONT_PATHS=['C:/Windows/Fonts/arial.ttf','/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf']
def font(size,bold=False):
    for f in FONT_PATHS:
        p=Path(f.replace('arial.ttf','arialbd.ttf').replace('DejaVuSans.ttf','DejaVuSans-Bold.ttf') if bold else f)
        if p.exists(): return ImageFont.truetype(str(p),round(size*3))
    raise RuntimeError('No publication font available; do not use tiny bitmap fallback')

class Scene:
    def __init__(self,name,w,h,title):
        self.name,self.w,self.h=name,w,h
        self.file=E.Element('mxfile',host='app.diagrams.net',type='device')
        self.diagram=E.SubElement(self.file,'diagram',name=title,id=name)
        model=E.SubElement(self.diagram,'mxGraphModel',page='1',pageScale='1',pageWidth=str(w),pageHeight=str(h),grid='1',gridSize='10',background='#FFFFFF')
        self.root=E.SubElement(model,'root'); E.SubElement(self.root,'mxCell',id='0'); E.SubElement(self.root,'mxCell',id='1',parent='0')
        self.svg=E.Element('svg',xmlns='http://www.w3.org/2000/svg',width=str(w),height=str(h),viewBox=f'0 0 {w} {h}')
        E.SubElement(self.svg,'rect',width=str(w),height=str(h),fill='white')
        self.im=Image.new('RGB',(w*3,h*3),'white'); self.d=ImageDraw.Draw(self.im); self.i=1
    def cell(self,value,style,x,y,w,h,edge=False):
        self.i+=1
        c=E.SubElement(self.root,'mxCell',id=str(self.i),parent='1',value=value,style=style,**({'edge':'1'} if edge else {'vertex':'1'}))
        g=E.SubElement(c,'mxGeometry',x=str(x),y=str(y),width=str(w),height=str(h),**{'as':'geometry'})
        return c,g
    def rect(self,x,y,w,h,fill='white',stroke=GRID,r=9):
        self.cell('',f'rounded={int(r>0)};arcSize=12;fillColor={fill};strokeColor={stroke};strokeWidth=1.5;',x,y,w,h)
        E.SubElement(self.svg,'rect',x=str(x),y=str(y),width=str(w),height=str(h),rx=str(r),fill=fill,stroke=stroke,**{'stroke-width':'1.5'})
        self.d.rounded_rectangle(tuple(round(v*3) for v in (x,y,x+w,y+h)),radius=r*3,fill=fill,outline=stroke,width=4)
    def text(self,x,y,w,h,label,size=22,bold=False,color=INK,align='center'):
        # Plain text: line breaks remain editable, with no HTML dependency.
        self.cell(label,f'text;html=0;whiteSpace=wrap;overflow=hidden;align={align};verticalAlign=middle;spacing=0;fontFamily=Arial;fontSize={size};fontStyle={int(bold)};fontColor={color};strokeColor=none;fillColor=none;',x,y,w,h)
        lines=label.split('\n'); leading=size*1.22; cy=y+h/2-(len(lines)-1)*leading/2
        for i,line in enumerate(lines):
            xx=x+w/2 if align=='center' else x+2; yy=cy+i*leading
            e=E.SubElement(self.svg,'text',x=str(xx),y=str(yy),fill=color,**{'font-family':'Arial, sans-serif','font-size':str(size),'font-weight':'bold' if bold else 'normal','text-anchor':'middle' if align=='center' else 'start','dominant-baseline':'central'}); e.text=line
            self.d.text((round(xx*3),round(yy*3)),line,font=font(size,bold),fill=color,anchor='mm' if align=='center' else 'lm')
    def line(self,points,color=INK,width=2,arrow=False,dash=False):
        c,g=self.cell('',f'edgeStyle=none;rounded=0;endArrow={"block" if arrow else "none"};endFill=1;strokeColor={color};strokeWidth={width};dashed={int(dash)};',0,0,0,0,True)
        g.attrib.clear();g.set('relative','1');g.set('as','geometry')
        E.SubElement(g,'mxPoint',x=str(points[0][0]),y=str(points[0][1]),**{'as':'sourcePoint'})
        E.SubElement(g,'mxPoint',x=str(points[-1][0]),y=str(points[-1][1]),**{'as':'targetPoint'})
        if len(points)>2:
            ar=E.SubElement(g,'Array',**{'as':'points'})
            for x,y in points[1:-1]:E.SubElement(ar,'mxPoint',x=str(x),y=str(y))
        attrs={'points':' '.join(f'{x},{y}' for x,y in points),'fill':'none','stroke':color,'stroke-width':str(width)}
        if dash:attrs['stroke-dasharray']='7 5'
        E.SubElement(self.svg,'polyline',**attrs)
        for (x1,y1),(x2,y2) in zip(points,points[1:]):
            if dash:
                dist=math.hypot(x2-x1,y2-y1)
                for start in range(0,int(dist),12):
                    a=start/max(1,dist);b=min(start+7,dist)/max(1,dist)
                    self.d.line(tuple(round(z*3) for z in (x1+(x2-x1)*a,y1+(y2-y1)*a,x1+(x2-x1)*b,y1+(y2-y1)*b)),fill=color,width=round(width*3))
            else:self.d.line(tuple(round(z*3) for z in (x1,y1,x2,y2)),fill=color,width=round(width*3))
        if arrow:
            a,b=points[-2:];ang=math.atan2(b[1]-a[1],b[0]-a[0]);tri=[b,(b[0]-10*math.cos(ang-.45),b[1]-10*math.sin(ang-.45)),(b[0]-10*math.cos(ang+.45),b[1]-10*math.sin(ang+.45))]
            E.SubElement(self.svg,'polygon',points=' '.join(f'{x},{y}' for x,y in tri),fill=color)
            self.d.polygon([(round(x*3),round(y*3)) for x,y in tri],fill=color)
    def marker(self,x,y,color,shape='circle',r=6):
        self.cell('',f'shape={"ellipse" if shape=="circle" else "rectangle"};fillColor={color};strokeColor=white;strokeWidth=1;',x-r,y-r,r*2,r*2)
        if shape=='circle':
            E.SubElement(self.svg,'circle',cx=str(x),cy=str(y),r=str(r),fill=color,stroke='white')
            self.d.ellipse(tuple(round(v*3) for v in (x-r,y-r,x+r,y+r)),fill=color,outline='white',width=3)
        else:
            E.SubElement(self.svg,'rect',x=str(x-r),y=str(y-r),width=str(r*2),height=str(r*2),fill=color,stroke='white')
            self.d.rectangle(tuple(round(v*3) for v in (x-r,y-r,x+r,y+r)),fill=color,outline='white',width=3)
    def node(self,x,y,w,h,head,body,fill=PALE,body_size=15):
        self.rect(x,y,w,h,fill,BLUE); self.text(x+8,y+10,w-16,32,head,19,True); self.text(x+8,y+49,w-16,h-55,body,body_size)
    def save(self):
        E.ElementTree(self.file).write(SRC/(self.name+'.drawio'),encoding='utf-8',xml_declaration=True)
        E.ElementTree(self.svg).write(OUT/(self.name+'.svg'),encoding='utf-8',xml_declaration=True)
        self.im.save(OUT/(self.name+'.png'),dpi=(600,600)); return self.diagram

def architecture():
    s=Scene('fig1_architecture',1100,840,'1 Architecture')
    s.rect(180,20,740,105,WARM,'#D2AD69')
    s.text(195,29,710,32,'ADVISORY JUDGMENT PLANE',23,True)
    s.text(195,63,710,50,'Closed labels + scores; policy owns thresholds and fallbacks\nJ1/J2 routing   |   J3/J4 consent   |   J5/J6 recovery   |   J7 screening',19)
    s.node(180,195,220,115,'M1  Ingress','Authenticate + normalize\nJ7 screening only')
    s.node(440,195,220,115,'M2  Isolation','Partition context\nby caller and chat')
    s.node(700,195,220,115,'M3  Discovery','Rank eligible candidates\nJ1 / J2')
    s.node(700,375,220,115,'M4  Consent','Enforce approval\nJ3 / J4',WARM)
    s.node(440,375,220,115,'M5  Execution','Bind identity + endpoint\nExecute AIP task')
    s.node(180,375,220,115,'M7  Delivery','Reply to originating\nchat  |  Record outcomes')
    for a,b in [((400,252),(440,252)),((660,252),(700,252)),((810,310),(810,375)),((700,432),(660,432)),((440,432),(400,432))]:
        s.line([a,b],arrow=True)
    s.line([(810,125),(810,195)],GOLD,2,arrow=True,dash=True)
    s.line([(290,125),(290,195)],GOLD,2,arrow=True,dash=True)
    s.line([(920,72),(965,72),(965,345),(870,345),(870,375)],GOLD,2,arrow=True,dash=True)
    s.text(0,205,145,75,'iMessage /\nPhoton',18,True)
    s.line([(145,252),(180,252)],arrow=True)
    s.text(0,388,145,70,'User-visible\nreply',17)
    s.line([(180,432),(145,432)],arrow=True)
    # Distinct request and return edges terminate at their actual peers.
    s.rect(420,570,260,100,MINT,BLUE)
    s.text(428,579,244,40,'ACPs Partner Agents',20,True)
    s.text(428,622,244,32,'AIP v2.2 / mTLS',17,color=GRAY)
    s.line([(495,490),(495,570)],BLUE,2,arrow=True)
    s.line([(605,570),(605,490)],BLUE,2,arrow=True)
    s.text(342,513,140,38,'Task request',16,color=BLUE)
    s.text(506,508,88,48,'Status /\nresult',14,color=BLUE)
    # State-support links use separate lanes, with no protocol intersections.
    s.node(180,715,740,80,'M6  State, idempotency and recovery','Keys, consent and task context  |  J5 / J6',MINT)
    s.line([(290,490),(290,715)],TEAL,2,dash=True)
    s.line([(660,470),(695,470),(695,715)],TEAL,2,dash=True)
    s.line([(810,490),(810,715)],TEAL,2,dash=True)
    s.text(180,804,740,30,'CODE ENFORCES: authorization • identity • isolation • idempotency',20,True)
    return s.save()

def states():
    s=Scene('fig2_state_machine',1140,1000,'2 Gateway processing flow')
    s.text(20,6,1100,36,'GATEWAY REQUEST PROCESSING FLOW',25,True)
    s.text(20,44,1100,28,'Reference design; terminal outcomes share one processing endpoint',17,color=GRAY)
    def box(x,y,w,title,body,fill=PALE,col=BLUE):
        s.rect(x,y,w,72,fill,col)
        s.text(x+8,y+4,w-16,29,title,19,True,color=col)
        s.text(x+8,y+35,w-16,32,body,15,color=INK)
    def label(x,y,w,t,col=GRAY): s.text(x,y,w,24,t,14,color=col)
    def connector(x,y):
        s.rect(x,y,34,34,WARM,GOLD,17); s.text(x,y,34,34,'A',18,True,color=GOLD)
    s.rect(410,88,270,40,MINT,TEAL,20); s.text(415,91,260,34,'Receive inbound event',19,True,color=TEAL)
    connector(310,91); s.line([(344,108),(410,108)],GOLD,2,arrow=True)
    main=[(156,'Authenticate','Verify event; reject invalid ingress'),(268,'Resolve context','Bind caller/session; deduplicate; discover'),(400,'Apply policy','Check route, consent and cancellation'),(560,'Validate endpoint','Verify AIC, endpoint and mTLS'),(680,'Execute AIP task','Claim key; execute / resume task')]
    for y,t,b in main: box(375,y,340,t,b)
    s.line([(545,128),(545,156)],arrow=True)
    for y,nexty,t in [(228,268,'valid'),(340,400,'new event / eligible route'),(472,560,'authorized'),(632,680,'verified')]:
        s.line([(545,y),(545,nexty)],arrow=True); label(552,(y+nexty)/2-12,150,t)
    # All red branches feed an outer bus; no path is labelled successful merely for ending.
    for y,t,b in [(156,'Rejected','Invalid signature / malformed event'),(268,'Not executable','No eligible route / invalid context'),(400,'Cancelled / denied','User declines / policy blocks'),(560,'Rejected','Endpoint or identity mismatch')]:
        box(795,y,300,t,b,'#FAEFED',RED)
        s.line([(715,y+36),(795,y+36)],RED,2,arrow=True)
        s.line([(1095,y+36),(1120,y+36)],RED,1.5)
    # A duplicate with stored output is replayed; an in-flight duplicate reuses its existing task.
    box(20,268,275,'Reuse existing event','Cached response / pending status','#F2F4F6',GRAY)
    s.line([(375,304),(295,304)],GRAY,2,arrow=True)
    s.line([(20,304),(8,304),(8,924),(375,924)],GRAY,1.5,arrow=True)
    # The A connector restarts ingress authentication for each new user response.
    box(20,400,275,'Wait for user','Persist context; ask / obtain consent',WARM,GOLD)
    s.line([(375,436),(295,436)],GOLD,2,arrow=True)
    label(298,405,74,'pending',GOLD)
    s.line([(157,472),(157,503)],GOLD,2,arrow=True,dash=True); connector(140,503)
    s.text(22,540,271,48,'New user reply via A\nReauthenticate and bind same session',14,color=GOLD)
    # Retry is permitted only with an explicit replay-safety check and finite budget.
    box(20,680,275,'Classify failure','Retryable + replay-safe + budget?',WARM,GOLD)
    s.line([(375,716),(295,716)],GOLD,2,arrow=True); label(298,684,74,'error',GOLD)
    s.line([(157,680),(157,638),(340,638),(340,596),(375,596)],GOLD,2,arrow=True,dash=True)
    label(32,606,284,'yes: backoff; same key; valid consent',GOLD)
    box(20,800,275,'Failed / unresolved','No safe retry or budget exhausted','#FAEFED',RED)
    s.line([(157,752),(157,800)],RED,2,arrow=True);label(167,765,65,'no',RED)
    s.line([(157,872),(157,910),(375,910)],RED,2,arrow=True)
    # Success is distinct from the shared record/end step.
    s.line([(545,752),(545,894)],TEAL,2,arrow=True)
    label(552,786,182,'success: return result',TEAL)
    s.line([(1120,192),(1120,924),(715,924)],RED,1.5,arrow=True)
    box(375,894,340,'Record handling outcome','Reply only to an authenticated context',MINT,TEAL)
    s.line([(545,966),(545,973)],TEAL,2,arrow=True)
    s.rect(455,973,180,25,MINT,TEAL,12);s.text(460,973,170,25,'End this event',16,True,color=TEAL)
    return s.save()

def coverage():
    # Pool the three sampled runs of the deployed model, scored against the
    # adjudicated labels that Table 7 reports. Earlier versions of this figure
    # were drawn before the reasoning-effort fix and used the built labels.
    rows=[]
    for name in ('judgment_model_predictions_adj_r1.csv','judgment_model_predictions_adj_r2.csv',
                 'judgment_model_predictions_adj_r3.csv'):
        rows+=list(csv.DictReader((DATA/name).open()))
    eval_rows=[]
    for name in ('judgment_model_eval_adj_r1.csv','judgment_model_eval_adj_r2.csv','judgment_model_eval_adj_r3.csv'):
        eval_rows+=list(csv.DictReader((DATA/name).open()))
    # A compact point-and-interval comparison is easier to read than a dense
    # curve after the figure is reduced to the LNCS text width.  Each point is
    # the mean of the three runs and each horizontal interval is their range.
    s=Scene('fig3_coverage_risk',760,350,'3 Coverage and risk')
    palette={'typed':(TEAL,'circle','Typed'),'free_text':(BLUE,'square','Free text'),'keyword':(GOLD,'square','Keyword')}
    summary={}; source={}
    for cond,(col,shape,_) in palette.items():
        fallback=[r for r in eval_rows if r['condition']==cond and r['split']=='test_threshold' and r['judgment_point']=='ALL']
        if fallback:
            cov=[float(r['coverage'])*100 for r in fallback]
            err=[float(r['residual_error'])*100 for r in fallback]
            summary[cond]={'coverage':(min(cov),sum(cov)/len(cov),max(cov)),
                           'error':None if max(cov)==0 else (min(err),sum(err)/len(err),max(err))}
        a=[r for r in rows if r['condition']==cond and r['split']=='test']
        pts=[]
        for t in sorted({float(r['confidence']) for r in a},reverse=True):
            covered=[r for r in a if float(r['confidence'])>=t];pts.append((len(covered)/len(a)*100,sum(r['correct']!='true' for r in covered)/len(covered)*100,t))
        source[cond]=[dict(coverage=c,residual_error=e,threshold=t) for c,e,t in pts]
    for yy,cond in zip((95,170,245),palette):
        col,shape,label=palette[cond]
        s.text(8,yy-15,113,30,label,19,True,align='left')
    def interval_panel(x0,x1,title,metric,maxv,ticks,ref=None):
        s.text(x0-12,8,x1-x0+24,32,title,22,True)
        for t in ticks:
            xp=x0+t/maxv*(x1-x0)
            s.line([(xp,65),(xp,272)],GRID,1)
            s.text(xp-26,280,52,25,f'{t:g}',17)
        s.line([(x0,272),(x1,272)],GRAY,1)
        if ref is not None:
            xp=x0+ref/maxv*(x1-x0)
            s.line([(xp,65),(xp,272)],RED,1.5,dash=True)
            s.text(xp-45,41,90,24,'5% target',16,color=RED)
        for yy,(cond,(col,shape,_)) in zip((95,170,245),palette.items()):
            vals=summary[cond][metric]
            if vals is None:
                s.rect(x0-2,yy-19,x1-x0+4,38,'white','white',0)
                s.text(x0,yy-16,x1-x0,32,'N/A (no coverage)',18,color=GRAY)
                continue
            lo,mean,hi=vals
            xl=x0+lo/maxv*(x1-x0);xm=x0+mean/maxv*(x1-x0);xh=x0+hi/maxv*(x1-x0)
            s.line([(xl,yy),(xh,yy)],col,3)
            for xp in (xl,xh):s.line([(xp,yy-5),(xp,yy+5)],col,2)
            s.marker(xm,yy,col,shape,6)
            lx=max(x0+33,min(xm,x1-33))
            s.text(lx-34,yy-34,68,24,f'{mean:.1f}%',18,True,color=col)
    interval_panel(135,365,'Coverage (%)','coverage',100,(0,25,50,75,100))
    interval_panel(475,725,'Residual error (%)','error',15,(0,5,10,15),ref=5)
    s.text(8,318,744,26,'Points: three-run means. Lines: observed min-max ranges.',18,color=GRAY)
    (SRC/'coverage_plot_data.json').write_text(json.dumps(source,indent=2),encoding='utf-8')
    return s.save()

def overhead():
    """Gateway-side handling cost, measured apart from model generation."""
    data=json.loads((DATA/'live_gateway_overhead.json').read_text(encoding='utf-8'))
    def stats(values):
        ordered=sorted(values)
        return statistics.median(ordered), ordered[0], ordered[-1], len(ordered)
    rows=[]
    for label,key,colour in (
        ('Ingress authentication (reject)','ingress_reject_ms',TEAL),
        ('Deduplication lookup (cache hit)','dedup_hit_ms',TEAL),
        ('AIP identity check (reject)','identity_reject_ms',TEAL),
        ('AIP request/response (accepted)','partner_task_ms',TEAL),
        ('First delivery incl. generation','first_delivery_ms',GRAY),
    ):
        p50,lo,hi,n=stats(data[key]); rows.append((label,p50,lo,hi,n,colour))
    s=Scene('fig3_overhead',1000,600,'3 Gateway overhead')
    s.text(30,14,940,32,'GATEWAY-SIDE HANDLING COST',25,True)
    s.text(30,52,940,26,'Bar = median; each label gives the observed range and n; the model call is shown for scale',17,color=GRAY)
    x0,x1,top=330,740,150
    lo_lg,hi_lg=math.log10(0.1),math.log10(10000)
    row_h=62
    def xpos(value):
        return x0+(math.log10(max(value,0.1))-lo_lg)/(hi_lg-lo_lg)*(x1-x0)
    for value in (0.1,1,10,100,1000):
        xp=xpos(value)
        s.line([(xp,top-14),(xp,top+row_h*len(rows)-18)],GRID,1)
        s.text(xp-42,top-46,84,24,f'{value:g}',16,color=GRAY)
    s.text(30,top-42,290,24,'milliseconds (log scale)',16,color=GRAY,align='left')
    for index,(label,value,low,high,n,colour) in enumerate(rows):
        y=top+index*row_h
        s.text(30,y+6,290,26,label,17,align='left')
        width=max(2.0,xpos(value)-x0)
        s.rect(x0,y+8,width,22,colour,colour,4)
        if value<1000:
            text=f'{value:,.2f} ms  ({low:,.2f}–{high:,.2f}), n={n}'
        else:
            text=f'{value/1000:,.2f} s  ({low/1000:,.2f}–{high/1000:,.2f}), n={n}'
        s.text(748,y+4,252,26,text,16,color=INK,align='left')
    s.text(30,548,940,26,'Each gateway operation is milliseconds; an end-to-end delivery is dominated by assistant generation.',16,color=GRAY)
    return s.save()


def threshold_curves(source):
    """Every pooled threshold point is retained; the curve is descriptive."""
    s=Scene('fig3_threshold_curves',760,515,'3a Full threshold curves')
    s.text(35,10,690,32,'Full held-out coverage-risk curves',23,True,align='left')
    s.text(35,45,690,26,'Three runs pooled; all distinct confidence thresholds retained',17,color=GRAY,align='left')
    palette={'typed':(TEAL,'circle','Typed'),'free_text':(BLUE,'square','Free text'),'keyword':(GOLD,'square','Keyword')}
    x0,x1,top,bottom=92,710,118,413
    maxv=max(10,math.ceil(max(p['residual_error'] for pts in source.values() for p in pts)/10)*10)
    for t in (0,25,50,75,100):
        xp=x0+t/100*(x1-x0);s.line([(xp,top),(xp,bottom)],GRID,1);s.text(xp-25,bottom+8,50,25,str(t),17)
    for i in range(6):
        t=maxv*i/5;yp=bottom-t/maxv*(bottom-top)
        s.line([(x0,yp),(x1,yp)],GRID,1);s.text(38,yp-13,43,26,f'{t:g}',17)
    s.text(35,82,400,27,'Residual error (%)',18,True,align='left')
    s.text(280,449,245,27,'Coverage (%)',18,True)
    for idx,(cond,(col,shape,label)) in enumerate(palette.items()):
        pts=source[cond]
        xy=[(x0+p['coverage']/100*(x1-x0),bottom-p['residual_error']/maxv*(bottom-top)) for p in pts]
        if len(xy)>1:s.line(xy,col,2)
        for x,y in xy:s.marker(x,y,col,shape,2.5)
        lx=320+idx*135
        s.line([(lx,96),(lx+22,96)],col,2);s.marker(lx+11,96,col,shape,4)
        s.text(lx+26,82,107,27,label,17,align='left')
    s.text(30,483,700,25,'Repeated predictions do not constitute independent test tasks.',16,color=GRAY)
    return s.save()

if __name__=='__main__':
    # Only the three figures the manuscript cites are regenerated.
    diagrams=[architecture(),states(),coverage()]
    # Keep the dense threshold data available as a separately editable page.
    curve_source={}
    for name in ('judgment_model_predictions_adj_r1.csv','judgment_model_predictions_adj_r2.csv','judgment_model_predictions_adj_r3.csv'):
        for r in csv.DictReader((DATA/name).open()):
            curve_source.setdefault(r['condition'],[])
    for cond in curve_source:
        a=[r for name in ('judgment_model_predictions_adj_r1.csv','judgment_model_predictions_adj_r2.csv','judgment_model_predictions_adj_r3.csv') for r in csv.DictReader((DATA/name).open()) if r['condition']==cond and r['split']=='test']
        pts=[]
        for t in sorted({float(r['confidence']) for r in a},reverse=True):
            covered=[r for r in a if float(r['confidence'])>=t]
            pts.append({'coverage':len(covered)/len(a)*100,'residual_error':sum(r['correct']!='true' for r in covered)/len(covered)*100,'threshold':t})
        curve_source[cond]=pts
    diagrams.append(threshold_curves(curve_source))
    combined=E.Element('mxfile',host='app.diagrams.net',type='device')
    for d in diagrams:combined.append(d)
    E.ElementTree(combined).write(SRC/'paper_figures.drawio',encoding='utf-8',xml_declaration=True)
    manifest={f:hashlib.sha256((DATA/f).read_bytes()).hexdigest() for f in [
        'judgment_model_eval_adj_r1.csv','judgment_model_eval_adj_r2.csv','judgment_model_eval_adj_r3.csv',
        'judgment_model_predictions_adj_r1.csv','judgment_model_predictions_adj_r2.csv','judgment_model_predictions_adj_r3.csv']}
    (SRC/'data_sha256.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print('Generated 3 manuscript figures plus an editable full-curve supplement.')
