"""Aurora Industries UNS Simulator — FastAPI server (port 8081).
Mirrors the IoTAuto simulator pattern exactly so both can run side-by-side.
"""
import asyncio, contextlib, json, os, random, threading, time
from collections import deque
from typing import Dict, Optional, Set
import paho.mqtt.client as mqtt
import uvicorn
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from aurora_model import STREAMS, FAULT_SCENARIOS, STREAM_BY_ID, SIM

MQTT_HOST   = os.getenv("MQTT_HOST",   "mqtt.iotdemozone.com")
MQTT_PORT   = int(os.getenv("MQTT_PORT",   "1883"))
MQTT_USER   = os.getenv("MQTT_USER",   "admin")
MQTT_PASS   = os.getenv("MQTT_PASS",   "28luXF7q")
SERVER_PORT = int(os.getenv("AURORA_PORT", "8081"))
SIM_API_KEY = os.getenv("AURORA_API_KEY", "").strip()
INFLUX_URL  = os.getenv("INFLUX_URL",  "").strip()
INFLUX_TOKEN= os.getenv("INFLUX_TOKEN","").strip()
INFLUX_ORG  = os.getenv("INFLUX_ORG",  "iotauto").strip()
INFLUX_BUCKET=os.getenv("INFLUX_BUCKET","aurora").strip()

class SimulatorState:
    def __init__(self):
        self.running = True
        self.mqtt_connected = False
        self.active_scenario = "normal"
        self.total_published = 0
        self.start_time = time.time()
        self.dpp_pending = False          # set by /api/trigger_dpp
        self.dpp_history: list = []
        self.stream_running: Dict[str,bool] = {s["id"]: True for s in STREAMS}
        self.stream_values:  Dict[str,str]  = {}
        self.stream_last_ts: Dict[str,float]= {}
        self.stream_pub_count: Dict[str,int]= {s["id"]: 0 for s in STREAMS}
        self.recent_messages: deque = deque(maxlen=300)
        self._rate_window:    deque = deque(maxlen=300)

    def get_rate(self):
        now=time.time(); recent=[t for t in self._rate_window if t>now-10]
        return round(len(recent)/10.0,1)

    def get_shared(self):
        sc = FAULT_SCENARIOS.get(self.active_scenario,{})
        hour = int(time.strftime("%H"))
        self.shift = "A" if hour<8 else ("B" if hour<16 else "C")
        SIM.shift = self.shift
        return {"fault": sc.get("fault_key"), "shift": self.shift,
                "health_degrade": sc.get("health_degrade",{})}

    def record(self, sid, payload):
        now=time.time(); self.total_published+=1; self._rate_window.append(now)
        self.stream_pub_count[sid]=self.stream_pub_count.get(sid,0)+1
        self.stream_last_ts[sid]=now
        v=payload.get("value",payload.get("total_kw",payload.get("result",payload.get("oee_pct","—"))))
        self.stream_values[sid]=str(v)
        stream=STREAM_BY_ID.get(sid,{})
        self.recent_messages.append({"ts":time.strftime("%H:%M:%S",time.localtime(now)),
            "topic":stream.get("topic",""),"label":stream.get("label",sid),
            "source":stream.get("source",""),"asset_id":stream.get("asset_id",""),
            "asset_type":stream.get("asset_type",""),"value":str(v),"payload":json.dumps(payload)[:200]})

    def reset_for_demo(self):
        self.total_published=0; self.start_time=time.time()
        self.active_scenario="normal"; self.stream_values={}
        self.stream_last_ts={}; self.stream_pub_count={s["id"]:0 for s in STREAMS}
        self.stream_running={s["id"]:True for s in STREAMS}
        self.recent_messages.clear(); self._rate_window.clear()
        SIM.reset()

STATE=SimulatorState()
_MAIN_LOOP: Optional[asyncio.AbstractEventLoop]=None

class ConnectionManager:
    def __init__(self): self._clients: Set[WebSocket]=set()
    async def connect(self,ws):
        await ws.accept(); self._clients.add(ws)
    def disconnect(self,ws): self._clients.discard(ws)
    async def broadcast(self,data):
        dead=set(); msg=json.dumps(data)
        for ws in list(self._clients):
            try: await ws.send_text(msg)
            except: dead.add(ws)
        for ws in dead: self._clients.discard(ws)
    @property
    def count(self): return len(self._clients)

WS_MGR=ConnectionManager(); EVENT_QUEUE: Optional[asyncio.Queue]=None

def _make_mqtt():
    c=mqtt.Client(client_id=f"aurora-sim-{int(time.time())}",clean_session=True)
    c.username_pw_set(MQTT_USER,MQTT_PASS); c.reconnect_delay_set(3,60)
    def _on_conn(c,_u,_f,rc):
        STATE.mqtt_connected=(rc==0)
        if _MAIN_LOOP and EVENT_QUEUE:
            asyncio.run_coroutine_threadsafe(EVENT_QUEUE.put({"type":"mqtt_status","connected":rc==0}),_MAIN_LOOP)
    def _on_disc(c,_u,rc): STATE.mqtt_connected=False
    c.on_connect=_on_conn; c.on_disconnect=_on_disc; return c

mqtt_client=_make_mqtt()

def _start_mqtt():
    def _run():
        while True:
            try:
                mqtt_client.connect(MQTT_HOST,MQTT_PORT,keepalive=60)
                mqtt_client.loop_forever(retry_first_connection=True)
            except Exception as e: print(f"MQTT err: {e}")
            STATE.mqtt_connected=False; time.sleep(5)
    threading.Thread(target=_run,daemon=True,name="mqtt-aurora").start()

_next_pub: Dict[str,float]={}

def _publisher(loop):
    global _next_pub
    now=time.time(); _next_pub={s["id"]:now+i*0.08 for i,s in enumerate(STREAMS)}
    while True:
        if not STATE.running: time.sleep(0.25); continue
        now=time.time(); shared=STATE.get_shared()
        for stream in STREAMS:
            sid=stream["id"]
            if not STATE.stream_running.get(sid,True): continue
            if now<_next_pub.get(sid,0): continue
            try: payload=stream["gen"](shared)
            except Exception as e: _next_pub[sid]=now+stream["interval"]; continue
            if STATE.mqtt_connected:
                try: mqtt_client.publish(stream["topic"],json.dumps(payload),qos=0)
                except: pass
            # InfluxDB write (fire-and-forget)
            if INFLUX_URL and INFLUX_TOKEN:
                _write_influx(stream, payload)
            STATE.record(sid,payload)
            if loop and EVENT_QUEUE:
                asyncio.run_coroutine_threadsafe(EVENT_QUEUE.put({
                    "type":"message","stream_id":sid,"label":stream["label"],
                    "topic":stream["topic"],"source":stream["source"],
                    "asset_id":stream.get("asset_id",""),"asset_type":stream.get("asset_type",""),
                    "value":STATE.stream_values.get(sid,""),"ts":time.strftime("%H:%M:%S")}),loop)
            _next_pub[sid]=now+stream["interval"]+random.uniform(-0.2,0.2)
        # DPP manual trigger
        if STATE.dpp_pending:
            STATE.dpp_pending=False
            dpp_payload={"timestamp":__import__('datetime').datetime.utcnow().isoformat()+"Z",
                "event":"dpp_triggered","batch_id":SIM.current_batch,
                "product":SIM.current_product,"triggered_by":"manual_demo",
                "unit_count":SIM.unit_seq}
            if STATE.mqtt_connected:
                mqtt_client.publish("aurora/line_04_inspection/cell_02/process/step_status",
                    json.dumps({**dpp_payload,"step":"inspection","status":"complete","result":"pass"}),qos=1)
            STATE.dpp_history.append(dpp_payload)
            if loop and EVENT_QUEUE:
                asyncio.run_coroutine_threadsafe(EVENT_QUEUE.put({"type":"dpp_triggered",**dpp_payload}),loop)
        time.sleep(0.04)

_influx_session=None
def _write_influx(stream, payload):
    """Best-effort InfluxDB line-protocol write in a background thread."""
    try:
        import urllib.request
        asset=stream.get("asset_id","plant"); atype=stream.get("asset_type","generic")
        lines=[]
        for k,v in payload.items():
            if k=="timestamp" or isinstance(v,(dict,list,str,bool)): continue
            meas=f"aurora_{stream['id']}"
            lines.append(f"{meas},asset_id={asset},asset_type={atype},stream={stream['id']} {k}={v}")
        if not lines: return
        data="\n".join(lines).encode()
        req=urllib.request.Request(f"{INFLUX_URL}/api/v2/write?org={INFLUX_ORG}&bucket={INFLUX_BUCKET}&precision=s",
            data=data,method="POST",headers={"Authorization":f"Token {INFLUX_TOKEN}","Content-Type":"text/plain; charset=utf-8"})
        urllib.request.urlopen(req,timeout=2)
    except: pass

@contextlib.asynccontextmanager
async def lifespan(_app):
    global EVENT_QUEUE,_MAIN_LOOP
    EVENT_QUEUE=asyncio.Queue(); _MAIN_LOOP=asyncio.get_event_loop()
    _start_mqtt()
    loop=asyncio.get_event_loop()
    threading.Thread(target=_publisher,args=(loop,),daemon=True,name="aurora-publisher").start()
    asyncio.create_task(_broadcast_loop()); asyncio.create_task(_watchdog()); asyncio.create_task(_announce_state())
    print(f"Aurora Simulator  port={SERVER_PORT}  streams={len(STREAMS)}  scenarios={len(FAULT_SCENARIOS)}")
    yield
    STATE.running=False
    with contextlib.suppress(Exception): mqtt_client.disconnect()

app=FastAPI(title="Aurora UNS Simulator",lifespan=lifespan)
app.add_middleware(CORSMiddleware,allow_origins=["*"],allow_methods=["*"],allow_headers=["*"])

if SIM_API_KEY:
    class _AuthMW(BaseHTTPMiddleware):
        async def dispatch(self,req,call_next):
            if req.url.path in("/health","/") or req.method=="OPTIONS": return await call_next(req)
            key=req.query_params.get("api_key","") if req.url.path=="/ws" else req.headers.get("X-API-Key","")
            if key!=SIM_API_KEY: return Response('{"detail":"Unauthorized"}',status_code=401,media_type="application/json")
            return await call_next(req)
    app.add_middleware(_AuthMW)

async def _broadcast_loop():
    while True:
        try:
            event=await asyncio.wait_for(EVENT_QUEUE.get(),timeout=2.0)
            await WS_MGR.broadcast(event)
        except asyncio.TimeoutError:
            await WS_MGR.broadcast({"type":"stats","running":STATE.running,"mqtt_connected":STATE.mqtt_connected,
                "total_published":STATE.total_published,"rate":STATE.get_rate(),
                "scenario":STATE.active_scenario,"ws_clients":WS_MGR.count,"uptime":round(time.time()-STATE.start_time)})
        except Exception as e: await asyncio.sleep(0.1)

async def _announce_state():
    await asyncio.sleep(3); await WS_MGR.broadcast({"type":"control","running":STATE.running})

async def _watchdog():
    last=0
    while True:
        await asyncio.sleep(30); total=STATE.total_published; delta=total-last; last=total
        print(f"[aurora-wd] running={STATE.running} mqtt={STATE.mqtt_connected} ws={WS_MGR.count} +{delta}/30s total={total:,}")

def _status_dict():
    sc=FAULT_SCENARIOS.get(STATE.active_scenario,{})
    return {"running":STATE.running,"mqtt_connected":STATE.mqtt_connected,
        "total_published":STATE.total_published,"rate":STATE.get_rate(),
        "scenario":STATE.active_scenario,"uptime":round(time.time()-STATE.start_time),
        "ws_clients":WS_MGR.count,"dpp_history":STATE.dpp_history[-10:],
        "current_batch":SIM.current_batch,"current_product":SIM.current_product,
        "unit_seq":SIM.unit_seq,"shift":SIM.shift,
        "ai_hint":sc.get("ai_hint",""),
        "streams":[{"id":s["id"],"label":s["label"],"topic":s["topic"],"area":s["area"],
            "source":s["source"],"unit":s.get("unit",""),"interval":s["interval"],
            "asset_id":s.get("asset_id",""),"asset_type":s.get("asset_type",""),
            "running":STATE.stream_running.get(s["id"],True),
            "value":STATE.stream_values.get(s["id"],"—"),
            "last_ts":STATE.stream_last_ts.get(s["id"]),
            "pub_count":STATE.stream_pub_count.get(s["id"],0)} for s in STREAMS],
        "scenarios":[{"id":k,"label":v["label"],"description":v["description"],
            "affected":v.get("affected",[]),"ai_hint":v.get("ai_hint","")} for k,v in FAULT_SCENARIOS.items()],
        "recent_messages":list(STATE.recent_messages)[-50:]}

@app.get("/health")
async def health(): return {"status":"ok","running":STATE.running,"mqtt":STATE.mqtt_connected,"streams":len(STREAMS),"uptime":round(time.time()-STATE.start_time)}

@app.get("/")
async def root():
    html_path=__import__('pathlib').Path(__file__).parent/"static"/"aurora.html"
    if html_path.exists(): return HTMLResponse(html_path.read_text())
    return JSONResponse({"service":"Aurora UNS Simulator","streams":len(STREAMS),"api":"/api/status","ws":"/ws"})

@app.get("/api/status")
async def get_status(): return _status_dict()

@app.post("/api/start")
async def start_all():
    STATE.running=True; STATE.start_time=time.time()
    await WS_MGR.broadcast({"type":"control","running":True})
    return {"ok":True,"running":True}

@app.post("/api/stop")
async def stop_all():
    STATE.running=False; await WS_MGR.broadcast({"type":"control","running":False})
    return {"ok":True,"running":False}

@app.post("/api/reset")
async def reset_demo():
    STATE.reset_for_demo(); STATE.running=True
    await WS_MGR.broadcast({"type":"control","running":True}); await WS_MGR.broadcast({"type":"reset"})
    return {"ok":True,"running":True,"message":"Aurora demo reset complete"}

@app.post("/api/scenario/{scenario_id}")
async def set_scenario(scenario_id:str):
    if scenario_id not in FAULT_SCENARIOS: return JSONResponse({"ok":False,"error":"Unknown scenario"},status_code=404)
    STATE.active_scenario=scenario_id; sc=FAULT_SCENARIOS[scenario_id]
    await WS_MGR.broadcast({"type":"scenario_change","scenario":scenario_id,
        "label":sc["label"],"affected":sc.get("affected",[]),"ai_hint":sc.get("ai_hint","")})
    return {"ok":True,"scenario":scenario_id,"ai_hint":sc.get("ai_hint","")}

@app.post("/api/trigger_dpp")
async def trigger_dpp():
    """Manual DPP trigger — for demo use only. Fires the batch-complete event."""
    STATE.dpp_pending=True
    return {"ok":True,"message":f"DPP trigger queued for batch {SIM.current_batch}",
            "batch_id":SIM.current_batch,"product":SIM.current_product}

@app.get("/api/dpp_history")
async def dpp_history(): return {"history":STATE.dpp_history}

@app.websocket("/ws")
async def ws_endpoint(ws:WebSocket):
    await WS_MGR.connect(ws)
    try:
        await ws.send_text(json.dumps({"type":"init",**_status_dict()}))
        while True:
            try: await asyncio.wait_for(ws.receive_text(),timeout=30.0)
            except asyncio.TimeoutError: await ws.send_text(json.dumps({"type":"ping"}))
    except (WebSocketDisconnect,Exception): pass
    finally: WS_MGR.disconnect(ws)

if __name__=="__main__":
    uvicorn.run(app,host="0.0.0.0",port=SERVER_PORT,log_level="info")
