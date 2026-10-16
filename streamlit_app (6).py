# ══════════════════════════════════════════════════════════════════════════════
# SISTEMA DE GESTIÓN DE POLVORÍN MINERO — VERSIÓN COMPLETA
# Parte 1: Operativo | Parte 2: Gestión y Análisis
# Cristóbal Rubio · Memoria de Título · UNAB 2026
# ══════════════════════════════════════════════════════════════════════════════
import streamlit as st
import pandas as pd
import sqlite3
import hashlib
import uuid
import json
import io
import random
from datetime import date, datetime, timedelta
import warnings
warnings.filterwarnings("ignore")
import zipfile
import re
import math
import time
import altair as alt
from xml.sax.saxutils import escape as _xml_escape

st.set_page_config(
    page_title="Sistema Polvorín Minero",
    page_icon="🧨",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
.semaforo-verde   {background:#C6EFCE;border-radius:12px;padding:20px;text-align:center;font-size:1.4em;font-weight:bold;color:#1F5C1F;border:2px solid #1F5C1F;}
.semaforo-amarillo{background:#FFEB9C;border-radius:12px;padding:20px;text-align:center;font-size:1.4em;font-weight:bold;color:#7F6000;border:2px solid #BF8F00;}
.semaforo-rojo    {background:#FFCCCC;border-radius:12px;padding:20px;text-align:center;font-size:1.4em;font-weight:bold;color:#C00000;border:2px solid #C00000;}
.alerta-critica   {background:#FFCCCC;border-left:5px solid #C00000;padding:10px 14px;border-radius:4px;margin:4px 0;}
.alerta-alta      {background:#FFEB9C;border-left:5px solid #BF8F00;padding:10px 14px;border-radius:4px;margin:4px 0;}
.alerta-media     {background:#FFF2CC;border-left:5px solid #7F6000;padding:10px 14px;border-radius:4px;margin:4px 0;}
.alerta-ok        {background:#C6EFCE;border-left:5px solid #1F5C1F;padding:10px 14px;border-radius:4px;margin:4px 0;}
.aviso-ia         {background:#FFF2CC;border:1px solid #BF8F00;border-radius:6px;padding:8px 12px;font-size:0.85em;margin-bottom:12px;}
.chat-usuario     {background:#E8F0FE;border-radius:10px;padding:10px 14px;margin:4px 0;text-align:right;}
.chat-asistente   {background:#F0F0F0;border-radius:10px;padding:10px 14px;margin:4px 0;}
.kpi-logrado      {background:#C6EFCE;border-radius:8px;padding:12px;text-align:center;}
.kpi-parcial      {background:#FFEB9C;border-radius:8px;padding:12px;text-align:center;}
.kpi-no-logrado   {background:#FFCCCC;border-radius:8px;padding:12px;text-align:center;}
.rol-badge        {display:inline-block;padding:3px 10px;border-radius:12px;font-size:0.8em;font-weight:bold;}
.rol-admin        {background:#1F3864;color:white;}
.rol-jefe         {background:#2E75B6;color:white;}
.rol-operario     {background:#70AD47;color:white;}
.rol-lectura      {background:#999;color:white;}
.separador-seccion{background:#1F3864;color:white;padding:6px 12px;border-radius:6px;font-size:0.8em;font-weight:bold;margin:8px 0 4px 0;text-align:center;}
</style>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# CONFIGURACIÓN NORMATIVA
# ══════════════════════════════════════════════════════════════════════════════
EXPLOSIVOS_CFG = {
    "ANFO":               {"tipo":"Secundario","unidad":"saco",  "peso_kg":25.0,"stock_min":5, "vida_dias":365,"almacen":"Container secundarios","temp_max":35,"hum_max":70},
    "Emulsion":           {"tipo":"Secundario","unidad":"caja",  "peso_kg":20.0,"stock_min":3, "vida_dias":180,"almacen":"Container secundarios","temp_max":30,"hum_max":65},
    "Mecha de seguridad": {"tipo":"Secundario","unidad":"rollo", "peso_kg":5.0, "stock_min":2, "vida_dias":730,"almacen":"Container secundarios","temp_max":40,"hum_max":75},
    "Fulminante N8":      {"tipo":"Primario",  "unidad":"caja",  "peso_kg":0.5, "stock_min":2, "vida_dias":365,"almacen":"Boveda enterrada (primarios)","temp_max":30,"hum_max":60},
}
CAPACIDADES = {
    "Container secundarios":        {"kg_max":3500,"dist_m":50},
    "Boveda enterrada (primarios)": {"kg_max":400, "dist_m":25},
}
RUTAS = {
    "Polvorin → Nivel 1":     {"dist_km":3.2,"tiempo_min":12,"limite_kmh":30},
    "Polvorin → Nivel 2":     {"dist_km":4.8,"tiempo_min":18,"limite_kmh":30},
    "Polvorin → Banco Norte": {"dist_km":2.1,"tiempo_min":8, "limite_kmh":25},
    "Polvorin → Banco Sur":   {"dist_km":5.5,"tiempo_min":20,"limite_kmh":30},
    "Polvorin → Rajo":        {"dist_km":7.2,"tiempo_min":28,"limite_kmh":35},
}
ROLES = {
    "administrador":{"label":"Administrador","color":"rol-admin","permisos":["todo"]},
    "jefe_turno":   {"label":"Jefe de Turno","color":"rol-jefe", "permisos":["operar","reportes","kpis","config_turno"]},
    "operario":     {"label":"Operario",      "color":"rol-operario","permisos":["operar"]},
    "solo_lectura": {"label":"Inspector",     "color":"rol-lectura","permisos":["ver"]},
}
MAX_PERSONAS = 5

# ══════════════════════════════════════════════════════════════════════════════
# BASE DE DATOS
# ══════════════════════════════════════════════════════════════════════════════
DB_PATH = "polvorin.db"

def get_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def hash_pin(pin):
    return hashlib.sha256(str(pin).encode()).hexdigest()

def init_db():
    conn = get_conn()
    c = conn.cursor()
    tablas = [
        """CREATE TABLE IF NOT EXISTS usuarios (
            id TEXT PRIMARY KEY, nombre TEXT, usuario TEXT UNIQUE,
            pin_hash TEXT, rol TEXT, licencia_venc TEXT, activo INTEGER DEFAULT 1)""",
        """CREATE TABLE IF NOT EXISTS inventario (
            id_lote TEXT PRIMARY KEY, explosivo TEXT, tipo TEXT,
            cantidad INTEGER, unidad TEXT, peso_kg_total REAL,
            fecha_ingreso TEXT, fecha_vencimiento TEXT,
            proveedor TEXT, n_guia TEXT, operador TEXT,
            almacen TEXT, qr_data TEXT, estado TEXT)""",
        """CREATE TABLE IF NOT EXISTS movimientos (
            id_mov TEXT PRIMARY KEY, id_lote TEXT, explosivo TEXT,
            tipo_mov TEXT, cantidad INTEGER, fecha_hora TEXT,
            operador TEXT, destino TEXT, n_orden TEXT,
            turno TEXT, observaciones TEXT)""",
        """CREATE TABLE IF NOT EXISTS accesos (
            id TEXT PRIMARY KEY, operador TEXT, tipo TEXT,
            fecha_hora TEXT, motivo TEXT, turno TEXT)""",
        """CREATE TABLE IF NOT EXISTS turnos (
            id TEXT PRIMARY KEY, jefe TEXT, tipo TEXT,
            inicio TEXT, fin TEXT, estado TEXT)""",
        """CREATE TABLE IF NOT EXISTS viajes (
            id_viaje TEXT PRIMARY KEY, vehiculo TEXT, ruta TEXT,
            operador TEXT, explosivo TEXT, cantidad INTEGER,
            inicio TEXT, fin TEXT, dist_km REAL,
            t_esperado INTEGER, t_real INTEGER, demora INTEGER,
            estado TEXT, turno TEXT)""",
        """CREATE TABLE IF NOT EXISTS condiciones (
            id TEXT PRIMARY KEY, fecha_hora TEXT,
            temp_sec REAL, hum_sec REAL,
            temp_prim REAL, hum_prim REAL)""",
        """CREATE TABLE IF NOT EXISTS auditorias (
            id TEXT PRIMARY KEY, fecha TEXT, operador TEXT,
            explosivo TEXT, cantidad_sistema INTEGER,
            cantidad_real INTEGER, diferencia INTEGER,
            estado TEXT, observaciones TEXT)""",
        """CREATE TABLE IF NOT EXISTS vehiculos (
            id TEXT PRIMARY KEY, patente TEXT, modelo TEXT,
            rev_tecnica TEXT, permiso TEXT, estado TEXT)""",
        """CREATE TABLE IF NOT EXISTS proveedores (
            id TEXT PRIMARY KEY, nombre TEXT, rut TEXT,
            contacto TEXT, habilitado INTEGER DEFAULT 1)""",
        """CREATE TABLE IF NOT EXISTS kpis (
            id TEXT PRIMARY KEY, nombre TEXT, area TEXT,
            valor_base REAL, meta_6m REAL, meta_12m REAL,
            unidad TEXT, descripcion TEXT)""",
        """CREATE TABLE IF NOT EXISTS kpi_historial (
            id TEXT PRIMARY KEY, fecha TEXT, kpi_id TEXT,
            valor_real REAL, periodo TEXT, registrado_por TEXT)""",
        """CREATE TABLE IF NOT EXISTS sim_historial (
            id TEXT PRIMARY KEY, huella TEXT UNIQUE, etiqueta TEXT, escenario TEXT,
            semilla INTEGER, meses INTEGER, adopcion_final REAL,
            metas6_ok INTEGER, metas6_tot INTEGER, metas12_ok INTEGER, metas12_tot INTEGER,
            prog_global REAL, prog_global_ctrl REAL, params_json TEXT, detalle_json TEXT,
            fecha_registro TEXT, registrado_por TEXT)""",
    ]
    for t in tablas:
        c.execute(t)
    conn.commit()
    conn.close()
    _seed()

def _seed():
    conn = get_conn()
    c = conn.cursor()
    hoy = date.today()

    # Usuarios
    for u in [
        ("USR-001","Carlos Administrador","admin","1234","administrador",str(hoy+timedelta(days=365))),
        ("USR-002","Roberto Jefe","jefe_turno","5678","jefe_turno",str(hoy+timedelta(days=180))),
        ("USR-003","Juan Operario","operario1","9012","operario",str(hoy+timedelta(days=90))),
        ("USR-004","Ana Operaria","operario2","3456","operario",str(hoy+timedelta(days=200))),
        ("USR-005","Pedro Inspector","inspector","7890","solo_lectura",str(hoy+timedelta(days=500))),
        ("USR-006","Luis Vencido","operario3","1111","operario",str(hoy-timedelta(days=10))),
    ]:
        c.execute("INSERT OR IGNORE INTO usuarios VALUES (?,?,?,?,?,?,1)",
                  (u[0],u[1],u[2],hash_pin(u[3]),u[4],u[5]))

    # Inventario
    lotes = [
        ("ANFO-2026-001","ANFO","Secundario",18,"saco",450.0,str(hoy-timedelta(days=45)),str(hoy+timedelta(days=320)),"Enaex S.A.","GU-2026-0041","operario1","Container secundarios","","Vigente"),
        ("ANFO-2026-002","ANFO","Secundario",3,"saco",75.0,str(hoy-timedelta(days=400)),str(hoy-timedelta(days=35)),"Enaex S.A.","GU-2025-0098","operario1","Container secundarios","","Vencido"),
        ("EMUL-2026-001","Emulsion","Secundario",12,"caja",240.0,str(hoy-timedelta(days=20)),str(hoy+timedelta(days=160)),"Orica Chile","GU-2026-0051","operario2","Container secundarios","","Vigente"),
        ("EMUL-2026-002","Emulsion","Secundario",8,"caja",160.0,str(hoy-timedelta(days=160)),str(hoy+timedelta(days=15)),"Enaex S.A.","GU-2026-0028","operario2","Container secundarios","","Por vencer"),
        ("MECH-2026-001","Mecha de seguridad","Secundario",1,"rollo",5.0,str(hoy-timedelta(days=90)),str(hoy+timedelta(days=640)),"Famesa","GU-2026-0019","operario1","Container secundarios","","Stock bajo"),
        ("FULM-2026-001","Fulminante N8","Primario",5,"caja",2.5,str(hoy-timedelta(days=45)),str(hoy+timedelta(days=320)),"Famesa","GU-2026-0035","operario1","Boveda enterrada (primarios)","","Vigente"),
    ]
    for l in lotes:
        c.execute("INSERT OR IGNORE INTO inventario VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", l)

    # Movimientos
    for m in [
        ("MOV-001","ANFO-2026-001","ANFO","Ingreso",18,str(hoy-timedelta(days=45))+" 08:30","operario1","-","GU-2026-0041","Mañana",""),
        ("MOV-002","ANFO-2026-001","ANFO","Despacho",5,str(hoy-timedelta(days=15))+" 07:00","operario1","Polvorin → Nivel 1","ORD-2026-012","Mañana",""),
        ("MOV-003","EMUL-2026-001","Emulsion","Ingreso",12,str(hoy-timedelta(days=20))+" 09:00","operario2","-","GU-2026-0051","Tarde",""),
        ("MOV-004","FULM-2026-001","Fulminante N8","Ingreso",5,str(hoy-timedelta(days=45))+" 10:00","operario1","-","GU-2026-0035","Mañana","Almacenado en boveda primarios"),
    ]:
        c.execute("INSERT OR IGNORE INTO movimientos VALUES (?,?,?,?,?,?,?,?,?,?,?)", m)

    # Vehículos
    for v in [
        ("VEH-001","PAT-001","Camión F-150",str(hoy+timedelta(days=120)),str(hoy+timedelta(days=90)),"Operativo"),
        ("VEH-002","PAT-002","Camioneta Hilux",str(hoy-timedelta(days=5)),str(hoy+timedelta(days=60)),"Rev. técnica vencida"),
        ("VEH-003","PAT-003","Camión Mercedes",str(hoy+timedelta(days=200)),str(hoy+timedelta(days=150)),"Operativo"),
    ]:
        c.execute("INSERT OR IGNORE INTO vehiculos VALUES (?,?,?,?,?,?)", v)

    # Proveedores
    for p in [
        ("PROV-001","Enaex S.A.","76.456.789-0","contacto@enaex.cl",1),
        ("PROV-002","Orica Chile","76.123.456-7","chile@orica.com",1),
        ("PROV-003","Famesa","76.789.012-3","ventas@famesa.cl",1),
        ("PROV-004","Proveedor No Habilitado","12.345.678-9","noauth@test.cl",0),
    ]:
        c.execute("INSERT OR IGNORE INTO proveedores VALUES (?,?,?,?,?)", p)

    # KPIs
    kpis_data = [
        ("KPI-001","% lotes con vencimiento registrado","Inventario",60,90,100,"%","Lotes con fecha de vencimiento registrada"),
        ("KPI-002","% despachos con orden de retiro","Inventario",40,85,100,"%","Despachos respaldados por orden formal"),
        ("KPI-003","Tiempo inventario físico","Inventario",45,20,10,"min","Tiempo promedio conteo físico completo"),
        ("KPI-004","Discrepancias por auditoría","Inventario",8,3,0,"N°/mes","Discrepancias detectadas por auditoría mensual"),
        ("KPI-005","% lotes vencidos detectados a tiempo","Seguridad",30,80,100,"%","Lotes vencidos detectados antes de ser usados"),
        ("KPI-006","Tiempo generación reporte AF","Seguridad",120,15,5,"min","Tiempo para generar reporte para AF"),
        ("KPI-007","% cumplimiento libro control DGMN","Seguridad",50,90,100,"%","Registros del libro control correctamente completados"),
        ("KPI-008","% viajes en tiempo","Traslados",55,80,90,"%","Traslados completados dentro del tiempo esperado"),
        ("KPI-009","Tiempo promedio despacho","Traslados",25,12,8,"min","Tiempo desde solicitud hasta salida del polvorín"),
        ("KPI-010","Alertas ambientales sin respuesta","Ambiental",5,2,0,"N°/mes","Alertas ambientales sin respuesta en plazo"),
    ]
    for k in kpis_data:
        c.execute("INSERT OR REPLACE INTO kpis VALUES (?,?,?,?,?,?,?,?)", k)

    # KPI historial simulado (6 meses) — ritmos distintos para que se vean los 3 estados
    ritmo = {"KPI-001": 1.25, "KPI-002": 0.90, "KPI-003": 1.10, "KPI-004": 0.60, "KPI-005": 0.80,
             "KPI-006": 1.30, "KPI-007": 1.05, "KPI-008": 0.35, "KPI-009": 0.95, "KPI-010": 1.40}
    for k in kpis_data:
        kid, base_v, meta6_v, meta12_v, unidad_k = k[0], k[3], k[4], k[5], k[6]
        for mes in range(6):
            f = hoy - timedelta(days=30 * (5 - mes))
            periodo = f.strftime("%Y-%m")
            val = base_v + (meta6_v - base_v) * (mes / 5.0) * ritmo[kid]
            if unidad_k in ("min", "N°/mes"):
                val = max(val, meta12_v)
            else:
                val = min(val, meta12_v)
            val = round(max(0.0, val), 1)
            c.execute("INSERT OR REPLACE INTO kpi_historial VALUES (?,?,?,?,?,?)",
                      ("KHIST-" + kid + "-" + periodo, str(f), kid, val, periodo, "sistema"))


    # Condiciones (24h)
    ahora = datetime.now()
    for h in range(24):
        dt = ahora - timedelta(hours=23-h)
        c.execute("INSERT OR IGNORE INTO condiciones VALUES (?,?,?,?,?,?)",
                  ("COND-"+str(h).zfill(3), dt.strftime("%Y-%m-%d %H:%M"),
                   round(random.uniform(14,38),1), round(random.uniform(45,85),1),
                   round(random.uniform(10,26),1), round(random.uniform(40,70),1)))

    # Viajes simulados
    for i in range(10):
        rn = random.choice(list(RUTAS.keys()))
        r  = RUTAS[rn]
        demora = random.choices([0, random.randint(2,15)], weights=[70,30])[0]
        t_real = r["tiempo_min"] + demora
        dt_s   = ahora - timedelta(hours=random.randint(1,72))
        c.execute("INSERT OR IGNORE INTO viajes VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                  ("VJ-"+str(i+1).zfill(3), random.choice(["PAT-001","PAT-003"]), rn,
                   random.choice(["operario1","operario2"]),
                   random.choice(list(EXPLOSIVOS_CFG.keys())),
                   random.randint(1,5),
                   dt_s.strftime("%Y-%m-%d %H:%M"),
                   (dt_s+timedelta(minutes=t_real)).strftime("%Y-%m-%d %H:%M"),
                   r["dist_km"], r["tiempo_min"], t_real, demora,
                   "Con demora" if demora>0 else "En tiempo", "Mañana"))

    conn.commit()
    conn.close()

# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════
def puede(permiso):
    perms = ROLES.get(st.session_state.get("rol",""),{}).get("permisos",[])
    return "todo" in perms or permiso in perms

def get_df(sql, params=None):
    conn = get_conn()
    df = pd.read_sql(sql, conn, params=params)
    conn.close()
    return df

def get_inv():     return get_df("SELECT * FROM inventario")
def get_movs():    return get_df("SELECT * FROM movimientos ORDER BY fecha_hora DESC")
def get_viajes():  return get_df("SELECT * FROM viajes ORDER BY inicio DESC")
def get_cond():    return get_df("SELECT * FROM condiciones ORDER BY fecha_hora")
def get_accesos(): return get_df("SELECT * FROM accesos ORDER BY fecha_hora DESC")
def get_kpis():    return get_df("SELECT * FROM kpis")
def get_khist():   return get_df("SELECT * FROM kpi_historial ORDER BY fecha")

def turno_activo():
    conn = get_conn()
    row  = conn.execute("SELECT * FROM turnos WHERE estado='Activo' ORDER BY inicio DESC LIMIT 1").fetchone()
    conn.close()
    return row

def personas_dentro():
    conn  = get_conn()
    hoy_s = str(date.today())
    ing   = conn.execute("SELECT COUNT(*) FROM accesos WHERE tipo='Ingreso' AND fecha_hora LIKE ?", (hoy_s+"%",)).fetchone()[0]
    egr   = conn.execute("SELECT COUNT(*) FROM accesos WHERE tipo='Egreso'  AND fecha_hora LIKE ?", (hoy_s+"%",)).fetchone()[0]
    conn.close()
    return max(0, ing - egr)

def peso_en_almacen(almacen):
    conn = get_conn()
    rows = conn.execute("SELECT peso_kg_total FROM inventario WHERE almacen=? AND estado NOT IN ('Vencido')", (almacen,)).fetchall()
    conn.close()
    return sum(r[0] for r in rows)

def clasificar(row):
    cfg = EXPLOSIVOS_CFG.get(str(row.get("explosivo","")),{})
    est = []
    try:
        fv = date.fromisoformat(str(row["fecha_vencimiento"]))
        d  = (fv-date.today()).days
        if d<0:     est.append("Vencido")
        elif d<=30: est.append("Por vencer")
    except Exception: pass
    try:
        if int(row["cantidad"])<cfg.get("stock_min",0): est.append("Stock bajo")
    except Exception: pass
    if str(row.get("almacen",""))!=cfg.get("almacen",""): est.append("Almacen incorrecto")
    return " | ".join(est) if est else "Vigente"

def generar_alertas():
    inv     = get_inv()
    alertas = []
    hoy     = date.today()
    for _,row in inv.iterrows():
        exp  = str(row["explosivo"])
        cfg  = EXPLOSIVOS_CFG.get(exp,{})
        lote = str(row["id_lote"])
        try:
            fv = date.fromisoformat(str(row["fecha_vencimiento"]))
            d  = (fv-hoy).days
            if d<0:
                alertas.append({"gravedad":"CRITICA","icono":"🚨","lote":lote,"exp":exp,
                    "msg":"Lote VENCIDO hace "+str(abs(d))+" días",
                    "accion":"Destrucción autorizada — Ley Armas Cap. VIII"})
            elif d<=30:
                alertas.append({"gravedad":"ALTA","icono":"⚠️","lote":lote,"exp":exp,
                    "msg":"Vence en "+str(d)+" días",
                    "accion":"Notificar a Autoridad Fiscalizadora (DGMN)"})
        except Exception: pass
        try:
            if int(row["cantidad"])<cfg.get("stock_min",0):
                alertas.append({"gravedad":"MEDIA","icono":"⚡","lote":lote,"exp":exp,
                    "msg":"Stock bajo: "+str(row["cantidad"])+" / mín "+str(cfg.get("stock_min",""))+" "+cfg.get("unidad",""),
                    "accion":"Solicitar reabastecimiento"})
        except Exception: pass
        if str(row.get("almacen",""))!=cfg.get("almacen",""):
            alertas.append({"gravedad":"CRITICA","icono":"🚨","lote":lote,"exp":exp,
                "msg":"Almacén incorrecto","accion":"Reubicar — DS 132 / Ley 17.798"})
    for alm,cap in CAPACIDADES.items():
        pct = peso_en_almacen(alm)/cap["kg_max"]*100
        if pct>=100:
            alertas.append({"gravedad":"CRITICA","icono":"🚨","lote":"-","exp":alm,
                "msg":"Capacidad MÁXIMA superada","accion":"Bloquear ingresos"})
        elif pct>=90:
            alertas.append({"gravedad":"ALTA","icono":"⚠️","lote":"-","exp":alm,
                "msg":"Capacidad al "+str(round(pct,1))+"%","accion":"Planificar despacho"})
    cond = get_cond()
    if not cond.empty:
        ult = cond.iloc[-1]
        for col,alm,lim,tipo,uni in [
            ("temp_sec","Container secundarios",35,"Temperatura","°C"),
            ("hum_sec", "Container secundarios",70,"Humedad","%"),
            ("temp_prim","Bóveda primarios",30,"Temperatura","°C"),
            ("hum_prim", "Bóveda primarios",60,"Humedad","%"),
        ]:
            if ult[col]>lim:
                alertas.append({"gravedad":"ALTA","icono":"⚠️","lote":"-","exp":alm,
                    "msg":tipo+" alta: "+str(ult[col])+uni+" (máx "+str(lim)+uni+")",
                    "accion":"Revisar ventilación del almacén"})
    personas = personas_dentro()
    if personas>=MAX_PERSONAS:
        alertas.append({"gravedad":"ALTA","icono":"⚠️","lote":"-","exp":"Acceso",
            "msg":str(personas)+" personas dentro (máx "+str(MAX_PERSONAS)+")",
            "accion":"Esperar egreso antes de nuevo ingreso"})
    vehs = get_df("SELECT * FROM vehiculos")
    for _,v in vehs.iterrows():
        try:
            if (date.fromisoformat(str(v["rev_tecnica"]))-hoy).days<0:
                alertas.append({"gravedad":"ALTA","icono":"⚠️","lote":v["patente"],"exp":"Vehículo",
                    "msg":"Rev. técnica vencida: "+str(v["modelo"]),
                    "accion":"No asignar traslados"})
        except Exception: pass
    return alertas

def semaforo(alertas):
    if any(a["gravedad"]=="CRITICA" for a in alertas): return "rojo"
    if any(a["gravedad"]=="ALTA"    for a in alertas): return "amarillo"
    return "verde"

def mostrar_alerta(a):
    cls = ("alerta-critica" if a["gravedad"]=="CRITICA" else
           "alerta-alta"    if a["gravedad"]=="ALTA"    else "alerta-media")
    st.markdown(
        '<div class="'+cls+'"><b>'+a["icono"]+" "+a["gravedad"]+
        '</b> · '+a["lote"]+' — '+a["exp"]+'<br>'+
        '<small>'+a["msg"]+'</small><br>'+
        '<small><i>→ '+a["accion"]+'</i></small></div>',
        unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# AUTENTICACIÓN
# ══════════════════════════════════════════════════════════════════════════════
def pantalla_login():
    st.markdown("## 🧨 Sistema de Gestión de Polvorín Minero")
    st.markdown("**Cristóbal Rubio · Memoria de Título · UNAB 2026**")
    st.divider()
    _,col,_ = st.columns([1,1.2,1])
    with col:
        st.markdown("### 🔐 Iniciar sesión")
        with st.form("login"):
            usuario = st.text_input("Usuario")
            pin     = st.text_input("PIN", type="password", placeholder="4-6 dígitos")
            sub     = st.form_submit_button("Ingresar", type="primary", use_container_width=True)
        if sub:
            if not usuario or not pin:
                st.error("Ingresa usuario y PIN.")
                return
            conn = get_conn()
            row  = conn.execute(
                "SELECT * FROM usuarios WHERE usuario=? AND pin_hash=? AND activo=1",
                (usuario.strip(), hash_pin(pin.strip()))
            ).fetchone()
            conn.close()
            if not row:
                st.error("❌ Usuario o PIN incorrectos.")
                return
            u = dict(zip(["id","nombre","usuario","pin_hash","rol","licencia_venc","activo"], row))
            if u["rol"]=="operario":
                try:
                    lv = date.fromisoformat(str(u["licencia_venc"]))
                    if (lv-date.today()).days<0:
                        st.error("🚫 Licencia vencida el "+str(lv)+". Contacte al administrador.")
                        return
                except Exception: pass
            for k,v in [("autenticado",True),("usuario",u["usuario"]),
                        ("nombre",u["nombre"]),("rol",u["rol"]),("id_usuario",u["id"])]:
                st.session_state[k] = v
            st.rerun()
        st.divider()
        st.markdown("**Usuarios de prueba:**")
        st.dataframe(pd.DataFrame({
            "Rol":    ["Administrador","Jefe de Turno","Operario","Inspector","Op. bloqueado"],
            "Usuario":["admin","jefe_turno","operario1","inspector","operario3"],
            "PIN":    ["1234","5678","9012","7890","1111"],
            "Nota":   ["Acceso total","Ops + reportes","Lic. vigente","Solo lectura","Lic. vencida"],
        }), hide_index=True, use_container_width=True)

# ══════════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════════════════════════════
def sidebar():
    with st.sidebar:
        rc = ROLES.get(st.session_state["rol"],{})
        st.markdown("### 🧨 Polvorín Minero")
        st.markdown(
            '<span class="rol-badge '+rc.get("color","")+'">'+rc.get("label","")+'</span> '+
            st.session_state["nombre"], unsafe_allow_html=True)
        turno = turno_activo()
        if turno: st.success("🕐 Turno "+turno[3]+" activo")
        else:     st.warning("⏸ Sin turno activo")
        alertas = generar_alertas()
        nc = len([a for a in alertas if a["gravedad"]=="CRITICA"])
        na = len([a for a in alertas if a["gravedad"]=="ALTA"])
        if nc>0:   st.error("🚨 "+str(nc)+" alerta(s) crítica(s)")
        elif na>0: st.warning("⚠️ "+str(na)+" alerta(s) alta(s)")
        else:      st.success("✅ Sin alertas críticas")
        st.divider()

        # Selector de sección
        seccion = st.radio("Sección", ["⚙️ Parte 1 — Operativo", "📊 Parte 2 — Gestión y Análisis",
                                       "🎮 Parte 3 — Simulador"],
                           label_visibility="collapsed",
                           key="seccion_sel")
        st.markdown("")

        if "Parte 1" in seccion:
            p1 = ["🏠 Estado General","📥 Inventario","🚨 Alertas",
                  "🚪 Accesos","🌡️ Condiciones","🚛 Traslados","📋 Reportes"]
            if puede("todo"):
                p1 += ["🔍 Auditoría","🏢 Administración"]
            p1 += ["📖 Manual"]
            modulo = st.radio("Módulo", p1, label_visibility="collapsed", key="mod_p1")
        elif "Parte 2" in seccion:
            p2 = ["📊 KPIs y Cumplimiento","👁️ Vista por Rol",
                  "📋 Libro Control (AF)","🤖 Asistente IA","ℹ️ Acerca del sistema"]
            modulo = st.radio("Módulo", p2, label_visibility="collapsed", key="mod_p2")
        else:
            p3 = ["🎮 Simulador de escenarios","📚 Historial de simulaciones","📘 Supuestos del modelo"]
            modulo = st.radio("Módulo", p3, label_visibility="collapsed", key="mod_p3")
        st.divider()
        if st.button("🚪 Cerrar sesión", use_container_width=True):
            for k in list(st.session_state.keys()):
                del st.session_state[k]
            st.rerun()
        st.caption("DS 132 · Ley 17.798 · DGMN 003048/2020")
    return modulo

# ══════════════════════════════════════════════════════════════════════════════
# PARTE 1 — MÓDULOS OPERATIVOS
# ══════════════════════════════════════════════════════════════════════════════
def mod_dashboard():
    st.title("🏠 Estado General del Polvorín")
    st.caption("Actualizado: "+datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    alertas  = generar_alertas()
    sem      = semaforo(alertas)
    inv      = get_inv()
    personas = personas_dentro()
    textos   = {"verde":"🟢 TODO EN ORDEN","amarillo":"🟡 ATENCIÓN REQUERIDA","rojo":"🔴 ACCIÓN INMEDIATA"}
    st.markdown('<div class="semaforo-'+sem+'">'+textos[sem]+'</div>', unsafe_allow_html=True)
    st.markdown("")
    nc = len([a for a in alertas if a["gravedad"]=="CRITICA"])
    na = len([a for a in alertas if a["gravedad"]=="ALTA"])
    def ce(kw): return len(inv[inv["estado"].str.contains(kw,na=False)]) if not inv.empty else 0
    c1,c2,c3,c4,c5 = st.columns(5)
    c1.metric("📦 Lotes activos",   len(inv[~inv["estado"].str.contains("Vencido",na=False)]) if not inv.empty else 0)
    c2.metric("👷 Personas dentro", str(personas)+"/"+str(MAX_PERSONAS), delta_color="inverse" if personas>=MAX_PERSONAS else "normal")
    c3.metric("🚨 Críticas",        nc, delta_color="inverse" if nc>0 else "normal")
    c4.metric("⚠️ Altas",           na, delta_color="inverse" if na>0 else "normal")
    c5.metric("🕐 Turno",           turno_activo()[3] if turno_activo() else "Sin turno")
    st.divider()
    col_a, col_b = st.columns(2)
    with col_a:
        st.subheader("⚖️ Capacidad de almacenes")
        for alm,cap in CAPACIDADES.items():
            peso  = peso_en_almacen(alm)
            pct   = min(round(peso/cap["kg_max"]*100,1),100)
            color = "crit" if pct>=100 else ("warn" if pct>=90 else "ok")
            fill_colors = {"ok":"#1F5C1F","warn":"#BF8F00","crit":"#C00000"}
            st.markdown("**"+alm+"**")
            st.markdown(
                '<div style="background:#eee;border-radius:6px;height:22px;">'
                '<div style="background:'+fill_colors[color]+';height:22px;border-radius:6px;width:'+str(pct)+'%"></div></div>',
                unsafe_allow_html=True)
            st.caption(str(round(peso,1))+" kg / "+str(cap["kg_max"])+" kg · "+str(pct)+"%")
        st.subheader("🌡️ Condiciones actuales")
        cond = get_cond()
        if not cond.empty:
            ult = cond.iloc[-1]
            cc1,cc2,cc3,cc4 = st.columns(4)
            cc1.metric("Temp. Container",str(ult["temp_sec"])+"°C", delta="⚠️" if ult["temp_sec"]>35 else "✓", delta_color="inverse" if ult["temp_sec"]>35 else "normal")
            cc2.metric("Hum. Container", str(ult["hum_sec"])+"%",  delta="⚠️" if ult["hum_sec"]>70  else "✓", delta_color="inverse" if ult["hum_sec"]>70  else "normal")
            cc3.metric("Temp. Bóveda",   str(ult["temp_prim"])+"°C",delta="⚠️" if ult["temp_prim"]>30 else "✓",delta_color="inverse" if ult["temp_prim"]>30 else "normal")
            cc4.metric("Hum. Bóveda",    str(ult["hum_prim"])+"%", delta="⚠️" if ult["hum_prim"]>60  else "✓",delta_color="inverse" if ult["hum_prim"]>60  else "normal")
    with col_b:
        st.subheader("🚨 Alertas activas")
        if not alertas: st.markdown('<div class="alerta-ok">✅ Sin alertas activas</div>', unsafe_allow_html=True)
        for a in alertas[:8]: mostrar_alerta(a)
        st.subheader("📊 Stock por explosivo")
        if not inv.empty:
            res = inv.groupby("explosivo").agg(Unidades=("cantidad","sum"),Lotes=("id_lote","count"),Peso_kg=("peso_kg_total","sum")).reset_index()
            st.dataframe(res, use_container_width=True, hide_index=True)

def mod_inventario():
    st.title("📥 Inventario y Kardex")
    if not puede("operar"): st.warning("Solo lectura.")
    tab1,tab2,tab3,tab4 = st.tabs(["📦 Inventario","➕ Ingreso","📤 Despacho","↩️ Devolución"])
    with tab1:
        inv = get_inv()
        inv["estado_calc"] = inv.apply(clasificar, axis=1)
        fil = st.selectbox("Filtrar",["Todos"]+sorted(inv["estado_calc"].unique().tolist()))
        st.dataframe((inv if fil=="Todos" else inv[inv["estado_calc"]==fil]).drop(columns=["qr_data"],errors="ignore"), use_container_width=True, hide_index=True)
        st.subheader("📋 Libro de control")
        st.dataframe(get_movs(), use_container_width=True, hide_index=True)
    with tab2:
        if not puede("operar"): st.info("Sin permiso."); return
        turno = turno_activo()
        if not turno: st.warning("⚠️ No hay turno activo.")
        provs = get_df("SELECT nombre FROM proveedores WHERE habilitado=1")["nombre"].tolist()
        with st.form("form_ing"):
            c1,c2 = st.columns(2)
            exp   = c1.selectbox("Explosivo",list(EXPLOSIVOS_CFG.keys()))
            cant  = c2.number_input("Cantidad",min_value=1,value=5)
            c3,c4 = st.columns(2)
            prov  = c3.selectbox("Proveedor habilitado",provs)
            guia  = c4.text_input("N° Guía","GU-"+str(date.today().year)+"-")
            c5,c6 = st.columns(2)
            f_venc= c5.date_input("Fecha vencimiento",value=date.today()+timedelta(days=365))
            oper  = c6.text_input("Operador",st.session_state["nombre"])
            obs   = st.text_area("Observaciones",height=60)
            sub   = st.form_submit_button("✅ Registrar ingreso",type="primary")
        if sub:
            cfg  = EXPLOSIVOS_CFG[exp]
            pnew = int(cant)*cfg["peso_kg"]
            pact = peso_en_almacen(cfg["almacen"])
            kmax = CAPACIDADES[cfg["almacen"]]["kg_max"]
            if pact+pnew>kmax:
                st.error("🚫 BLOQUEADO: Capacidad máxima superada.\nActual: "+str(round(pact,1))+" kg + Nuevo: "+str(round(pnew,1))+" kg > Máx: "+str(kmax)+" kg.")
            else:
                id_l = exp[:4].upper().replace(" ","_")+"-"+str(date.today().year)+"-"+uuid.uuid4().hex[:4].upper()
                conn = get_conn()
                conn.execute("INSERT INTO inventario VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                             (id_l,exp,cfg["tipo"],int(cant),cfg["unidad"],round(pnew,2),
                              str(date.today()),str(f_venc),prov,guia,oper,cfg["almacen"],"","Vigente"))
                conn.execute("INSERT INTO movimientos VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                             ("MOV-"+uuid.uuid4().hex[:6].upper(),id_l,exp,"Ingreso",int(cant),
                              datetime.now().strftime("%Y-%m-%d %H:%M"),oper,"-",guia,
                              turno[3] if turno else "Sin turno",obs))
                conn.commit(); conn.close()
                st.success("✅ Lote "+id_l+" registrado en "+cfg["almacen"])
                st.rerun()
    with tab3:
        if not puede("operar"): st.info("Sin permiso."); return
        st.info("El sistema selecciona automáticamente el lote más antiguo (FIFO normativo).")
        inv2  = get_inv()
        inv_v = inv2[~inv2["estado"].str.contains("Vencido",na=False)] if not inv2.empty else inv2
        vehs_ok = get_df("SELECT patente FROM vehiculos WHERE estado='Operativo'")["patente"].tolist()
        with st.form("form_desp"):
            c1,c2 = st.columns(2)
            exp_d  = c1.selectbox("Explosivo",list(EXPLOSIVOS_CFG.keys()))
            lotes_e= inv_v[inv_v["explosivo"]==exp_d].sort_values("fecha_ingreso") if not inv_v.empty else pd.DataFrame()
            if lotes_e.empty: c2.warning("Sin stock vigente."); lote_fifo=None
            else:
                lote_fifo = lotes_e.iloc[0]
                c2.info("Lote FIFO: "+str(lote_fifo["id_lote"])+" · "+str(lote_fifo["cantidad"])+" "+str(lote_fifo["unidad"]))
            c3,c4 = st.columns(2)
            cant_d = c3.number_input("Cantidad",min_value=1,max_value=int(lote_fifo["cantidad"]) if lote_fifo is not None else 1)
            dest   = c4.selectbox("Destino",list(RUTAS.keys()))
            c5,c6 = st.columns(2)
            veh    = c5.selectbox("Vehículo",vehs_ok if vehs_ok else ["Sin vehículos operativos"])
            orden  = c6.text_input("N° Orden","ORD-"+str(date.today().year)+"-")
            sub_d  = st.form_submit_button("📤 Confirmar despacho",type="primary")
        if sub_d and lote_fifo is not None:
            t = turno_activo(); r = RUTAS[dest]
            conn = get_conn()
            conn.execute("UPDATE inventario SET cantidad=cantidad-?, peso_kg_total=peso_kg_total-? WHERE id_lote=?",
                         (int(cant_d),round(int(cant_d)*EXPLOSIVOS_CFG[exp_d]["peso_kg"],2),lote_fifo["id_lote"]))
            conn.execute("INSERT INTO movimientos VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                         ("MOV-"+uuid.uuid4().hex[:6].upper(),lote_fifo["id_lote"],exp_d,"Despacho",
                          int(cant_d),datetime.now().strftime("%Y-%m-%d %H:%M"),
                          st.session_state["nombre"],dest,orden,t[3] if t else "Sin turno",""))
            conn.execute("INSERT INTO viajes VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                         ("VJ-"+uuid.uuid4().hex[:5].upper(),veh,dest,st.session_state["nombre"],
                          exp_d,int(cant_d),datetime.now().strftime("%Y-%m-%d %H:%M"),
                          (datetime.now()+timedelta(minutes=r["tiempo_min"])).strftime("%Y-%m-%d %H:%M"),
                          r["dist_km"],r["tiempo_min"],r["tiempo_min"],0,"En tiempo",t[3] if t else "Sin turno"))
            conn.commit(); conn.close()
            st.success("✅ Despacho registrado · Destino: "+dest+" · Tiempo est.: "+str(r["tiempo_min"])+" min")
            st.rerun()
    with tab4:
        if not puede("operar"): st.info("Sin permiso."); return
        st.info("Use este módulo para reingresar material no utilizado en tronadura.")
        lotes = get_inv()["id_lote"].tolist()
        with st.form("form_dev"):
            c1,c2 = st.columns(2)
            lote_d= c1.selectbox("Lote",lotes)
            cant_v= c2.number_input("Cantidad a devolver",min_value=1,value=1)
            motivo= st.text_area("Motivo de devolución",height=70)
            sub_v = st.form_submit_button("↩️ Registrar devolución",type="primary")
        if sub_v:
            t = turno_activo()
            conn = get_conn()
            row_l = conn.execute("SELECT explosivo FROM inventario WHERE id_lote=?",(lote_d,)).fetchone()
            if row_l:
                exp_v = row_l[0]; pku = EXPLOSIVOS_CFG.get(exp_v,{}).get("peso_kg",0)
                conn.execute("UPDATE inventario SET cantidad=cantidad+?, peso_kg_total=peso_kg_total+? WHERE id_lote=?",
                             (int(cant_v),round(int(cant_v)*pku,2),lote_d))
                conn.execute("INSERT INTO movimientos VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                             ("MOV-"+uuid.uuid4().hex[:6].upper(),lote_d,exp_v,"Devolucion",int(cant_v),
                              datetime.now().strftime("%Y-%m-%d %H:%M"),st.session_state["nombre"],
                              "-","DEV-"+uuid.uuid4().hex[:4].upper(),t[3] if t else "Sin turno",motivo))
                conn.commit()
            conn.close()
            st.success("✅ Devolución registrada en lote "+lote_d)
            st.rerun()

def mod_alertas():
    st.title("🚨 Alertas del Sistema")
    alertas = generar_alertas()
    nc=len([a for a in alertas if a["gravedad"]=="CRITICA"])
    na=len([a for a in alertas if a["gravedad"]=="ALTA"])
    nm=len([a for a in alertas if a["gravedad"]=="MEDIA"])
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Total",len(alertas)); c2.metric("🚨 Críticas",nc)
    c3.metric("⚠️ Altas",na); c4.metric("⚡ Medias",nm)
    st.divider()
    fil = st.selectbox("Filtrar",["Todas","CRITICA","ALTA","MEDIA"])
    af  = alertas if fil=="Todas" else [a for a in alertas if a["gravedad"]==fil]
    if not af: st.markdown('<div class="alerta-ok">✅ Sin alertas en esta categoría</div>', unsafe_allow_html=True)
    for a in af: mostrar_alerta(a)

def mod_accesos():
    st.title("🚪 Control de Acceso al Polvorín")
    personas = personas_dentro()
    t1,t2,t3 = st.tabs(["📋 Registro","➕ Nuevo acceso","🔄 Turno"])
    with t1:
        c1,c2,c3 = st.columns(3)
        c1.metric("Personas dentro",str(personas)+"/"+str(MAX_PERSONAS), delta_color="inverse" if personas>=MAX_PERSONAS else "normal")
        hoy_n = str(date.today())
        conn = get_conn()
        n_hoy = conn.execute("SELECT COUNT(*) FROM accesos WHERE fecha_hora LIKE ?",(hoy_n+"%",)).fetchone()[0]
        conn.close()
        c2.metric("Accesos hoy",int(n_hoy)); c3.metric("Límite normativo",str(MAX_PERSONAS))
        if personas>=MAX_PERSONAS: st.error("🚫 Límite alcanzado.")
        st.dataframe(get_accesos(), use_container_width=True, hide_index=True)
    with t2:
        if not puede("operar"): st.info("Sin permiso."); return
        ops = get_df("SELECT nombre FROM usuarios WHERE rol='operario' AND activo=1")["nombre"].tolist()
        with st.form("form_acc"):
            c1,c2 = st.columns(2)
            oper   = c1.selectbox("Operador",ops)
            tipo   = c2.selectbox("Tipo",["Ingreso","Egreso"])
            motivo = st.selectbox("Motivo",["Despacho","Inventario","Inspección","Recepción","Otro"])
            sub    = st.form_submit_button("✅ Registrar",type="primary")
        if sub:
            if tipo=="Ingreso" and personas>=MAX_PERSONAS:
                st.error("🚫 BLOQUEADO: Límite de "+str(MAX_PERSONAS)+" personas alcanzado.")
            else:
                t = turno_activo()
                conn = get_conn()
                conn.execute("INSERT INTO accesos VALUES (?,?,?,?,?,?)",
                             (uuid.uuid4().hex[:8].upper(),oper,tipo,
                              datetime.now().strftime("%Y-%m-%d %H:%M"),motivo,t[3] if t else "Sin turno"))
                conn.commit(); conn.close()
                st.success("✅ "+tipo+" de "+oper+" registrado.")
                st.rerun()
    with t3:
        if st.session_state["rol"] not in ["jefe_turno","administrador"]:
            st.info("Solo el jefe de turno puede gestionar turnos."); return
        t = turno_activo()
        if t:
            st.success("🕐 Turno "+t[3]+" activo desde "+str(t[4]))
            if st.button("⏹ Cerrar turno",type="secondary"):
                conn=get_conn(); conn.execute("UPDATE turnos SET fin=?,estado='Cerrado' WHERE id=?",(datetime.now().strftime("%Y-%m-%d %H:%M"),t[0])); conn.commit(); conn.close()
                st.success("Turno cerrado."); st.rerun()
        else:
            with st.form("form_turno"):
                tipo_t = st.selectbox("Tipo",["Mañana","Tarde","Noche"])
                sub_t  = st.form_submit_button("▶️ Iniciar turno",type="primary")
            if sub_t:
                conn=get_conn(); conn.execute("INSERT INTO turnos VALUES (?,?,?,?,?,?)",(uuid.uuid4().hex[:8].upper(),st.session_state["nombre"],tipo_t,datetime.now().strftime("%Y-%m-%d %H:%M"),"","Activo")); conn.commit(); conn.close()
                st.success("✅ Turno "+tipo_t+" iniciado."); st.rerun()

def mod_condiciones():
    st.title("🌡️ Condiciones Ambientales")
    st.caption("Prototipo: datos simulados. En producción: conectar sensores IoT vía API.")
    if st.button("🔄 Actualizar lecturas"):
        conn=get_conn()
        conn.execute("INSERT INTO condiciones VALUES (?,?,?,?,?,?)",
                     ("COND-"+uuid.uuid4().hex[:6].upper(),datetime.now().strftime("%Y-%m-%d %H:%M"),
                      round(random.uniform(14,38),1),round(random.uniform(45,85),1),
                      round(random.uniform(10,26),1),round(random.uniform(40,70),1)))
        conn.commit(); conn.close(); st.rerun()
    cond = get_cond()
    if cond.empty: st.info("Sin datos."); return
    ult = cond.iloc[-1]
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("🌡️ Temp. Container",str(ult["temp_sec"])+"°C",  delta="⚠️" if ult["temp_sec"]>35  else "✓",delta_color="inverse" if ult["temp_sec"]>35  else "normal")
    c2.metric("💧 Hum. Container", str(ult["hum_sec"])+"%",   delta="⚠️" if ult["hum_sec"]>70   else "✓",delta_color="inverse" if ult["hum_sec"]>70   else "normal")
    c3.metric("🌡️ Temp. Bóveda",  str(ult["temp_prim"])+"°C", delta="⚠️" if ult["temp_prim"]>30 else "✓",delta_color="inverse" if ult["temp_prim"]>30 else "normal")
    c4.metric("💧 Hum. Bóveda",   str(ult["hum_prim"])+"%",  delta="⚠️" if ult["hum_prim"]>60  else "✓",delta_color="inverse" if ult["hum_prim"]>60  else "normal")
    st.divider()
    col_l,col_r = st.columns(2)
    with col_l:
        st.markdown("**Container Secundarios**")
        st.line_chart(cond.set_index("fecha_hora")[["temp_sec","hum_sec"]].tail(24))
    with col_r:
        st.markdown("**Bóveda Primarios**")
        st.line_chart(cond.set_index("fecha_hora")[["temp_prim","hum_prim"]].tail(24))
    st.subheader("📋 Límites normativos")
    st.dataframe(pd.DataFrame([{"Explosivo":k,"Temp.máx(°C)":v["temp_max"],"Hum.máx(%)":v["hum_max"],"Almacén":v["almacen"]} for k,v in EXPLOSIVOS_CFG.items()]), use_container_width=True, hide_index=True)

def mod_traslados():
    st.title("🚛 Flota y Traslados")
    viajes = get_viajes()
    t1,t2,t3 = st.tabs(["📋 Viajes","🚗 Vehículos","📊 Optimización"])
    with t1:
        c1,c2,c3 = st.columns(3)
        c1.metric("Total",len(viajes))
        c2.metric("En tiempo",  len(viajes[viajes["estado"]=="En tiempo"])  if not viajes.empty else 0)
        c3.metric("Con demora", len(viajes[viajes["estado"]=="Con demora"]) if not viajes.empty else 0,delta_color="inverse")
        fil = st.selectbox("Filtrar",["Todos","En tiempo","Con demora"])
        st.dataframe(viajes if fil=="Todos" else viajes[viajes["estado"]==fil], use_container_width=True, hide_index=True)
    with t2:
        vehs = get_df("SELECT * FROM vehiculos")
        st.dataframe(vehs, use_container_width=True, hide_index=True)
        if puede("todo"):
            with st.form("form_veh"):
                pat    = st.selectbox("Patente",vehs["patente"].tolist())
                nrt    = st.date_input("Nueva rev. técnica",value=date.today()+timedelta(days=365))
                sub_v  = st.form_submit_button("Actualizar")
            if sub_v:
                conn=get_conn(); conn.execute("UPDATE vehiculos SET rev_tecnica=?,estado='Operativo' WHERE patente=?",(str(nrt),pat)); conn.commit(); conn.close()
                st.success("✅ Revisión técnica actualizada."); st.rerun()
    with t3:
        if viajes.empty: st.info("Sin datos."); return
        rows=[]
        for rn,r in RUTAS.items():
            vr=viajes[viajes["ruta"]==rn]
            tp=vr["t_real"].mean() if not vr.empty else r["tiempo_min"]
            dp=vr["demora"].mean()  if not vr.empty else 0
            ok=len(vr[vr["estado"]=="En tiempo"])/len(vr)*100 if not vr.empty else 100
            rows.append({"Ruta":rn,"Dist.(km)":r["dist_km"],"T.esp.(min)":r["tiempo_min"],"T.prom.(min)":round(tp,1),"Demora(min)":round(dp,1),"% en tiempo":str(round(ok,0))+"%"})
        df_opt=pd.DataFrame(rows)
        st.dataframe(df_opt, use_container_width=True, hide_index=True)
        idx_min=df_opt["Demora(min)"].idxmin(); idx_max=df_opt["Demora(min)"].idxmax()
        st.success("✅ Ruta más eficiente: "+df_opt.loc[idx_min,"Ruta"])
        st.warning("⚠️ Ruta con mayor demora: "+df_opt.loc[idx_max,"Ruta"])

# ── Generador de Excel (.xlsx) sin librerías externas ────────────────────────
E_NORMAL, E_TITULO, E_SUB, E_HDR, E_CELDA = 0, 1, 2, 3, 4
E_ROJO, E_AMAR, E_VERDE, E_AZUL, E_CREMA, E_NEGRITA = 5, 6, 7, 8, 9, 10

_ESTILOS_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
    '<fonts count="5">'
    '<font><sz val="10"/><name val="Calibri"/></font>'
    '<font><b/><sz val="14"/><color rgb="FF1F3864"/><name val="Calibri"/></font>'
    '<font><i/><sz val="10"/><color rgb="FF595959"/><name val="Calibri"/></font>'
    '<font><b/><sz val="10"/><color rgb="FFFFFFFF"/><name val="Calibri"/></font>'
    '<font><b/><sz val="10"/><name val="Calibri"/></font>'
    '</fonts>'
    '<fills count="8">'
    '<fill><patternFill patternType="none"/></fill>'
    '<fill><patternFill patternType="gray125"/></fill>'
    '<fill><patternFill patternType="solid"><fgColor rgb="FF1F3864"/><bgColor indexed="64"/></patternFill></fill>'
    '<fill><patternFill patternType="solid"><fgColor rgb="FFFFCCCC"/><bgColor indexed="64"/></patternFill></fill>'
    '<fill><patternFill patternType="solid"><fgColor rgb="FFFFEB9C"/><bgColor indexed="64"/></patternFill></fill>'
    '<fill><patternFill patternType="solid"><fgColor rgb="FFC6EFCE"/><bgColor indexed="64"/></patternFill></fill>'
    '<fill><patternFill patternType="solid"><fgColor rgb="FFBDD7EE"/><bgColor indexed="64"/></patternFill></fill>'
    '<fill><patternFill patternType="solid"><fgColor rgb="FFFFF2CC"/><bgColor indexed="64"/></patternFill></fill>'
    '</fills>'
    '<borders count="2">'
    '<border><left/><right/><top/><bottom/><diagonal/></border>'
    '<border><left style="thin"><color auto="1"/></left><right style="thin"><color auto="1"/></right>'
    '<top style="thin"><color auto="1"/></top><bottom style="thin"><color auto="1"/></bottom><diagonal/></border>'
    '</borders>'
    '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
    '<cellXfs count="11">'
    '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
    '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/>'
    '<xf numFmtId="0" fontId="2" fillId="0" borderId="0" xfId="0" applyFont="1"/>'
    '<xf numFmtId="0" fontId="3" fillId="2" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1">'
    '<alignment horizontal="center" vertical="center" wrapText="1"/></xf>'
    '<xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyBorder="1" applyAlignment="1">'
    '<alignment vertical="center" wrapText="1"/></xf>'
    '<xf numFmtId="0" fontId="0" fillId="3" borderId="1" xfId="0" applyFill="1" applyBorder="1" applyAlignment="1"><alignment vertical="center" wrapText="1"/></xf>'
    '<xf numFmtId="0" fontId="0" fillId="4" borderId="1" xfId="0" applyFill="1" applyBorder="1" applyAlignment="1"><alignment vertical="center" wrapText="1"/></xf>'
    '<xf numFmtId="0" fontId="0" fillId="5" borderId="1" xfId="0" applyFill="1" applyBorder="1" applyAlignment="1"><alignment vertical="center" wrapText="1"/></xf>'
    '<xf numFmtId="0" fontId="0" fillId="6" borderId="1" xfId="0" applyFill="1" applyBorder="1" applyAlignment="1"><alignment vertical="center" wrapText="1"/></xf>'
    '<xf numFmtId="0" fontId="0" fillId="7" borderId="1" xfId="0" applyFill="1" applyBorder="1" applyAlignment="1"><alignment vertical="center" wrapText="1"/></xf>'
    '<xf numFmtId="0" fontId="4" fillId="0" borderId="0" xfId="0" applyFont="1"/>'
    '</cellXfs>'
    '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
    '</styleSheet>'
)

def _col_letra(i):
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s

def _celda(v):
    try:
        if hasattr(v, "item"):
            v = v.item()
    except Exception:
        pass
    if v is None:
        return ""
    if isinstance(v, float) and v != v:
        return ""
    return v

def _estilo_valor(v):
    if not isinstance(v, str):
        return E_CELDA
    toks = set(re.findall(r"[A-ZÁÉÍÓÚÑ]+", v.upper()))
    for claves, est in (({"CRITICA", "VENCIDO"}, E_ROJO), ({"ALTA", "VENCER"}, E_AMAR),
                        ({"MEDIA", "DEVOLUCION"}, E_CREMA), ({"VIGENTE", "INGRESO"}, E_VERDE),
                        ({"DESPACHO"}, E_AZUL)):
        if toks & claves:
            return est
    return E_CELDA

def hoja_df(nombre, df, titulo, sub="", norma=""):
    filas = [[(titulo, E_TITULO)],
             [(sub or ("Generado: " + datetime.now().strftime("%Y-%m-%d %H:%M")), E_SUB)]]
    if norma:
        filas.append([(norma, E_SUB)])
    filas.append([])
    cols = [str(c) for c in df.columns]
    filas.append([(c, E_HDR) for c in cols])
    anchos = [len(c) + 4 for c in cols]
    for fila in df.itertuples(index=False):
        out = []
        for i, v in enumerate(fila):
            v = _celda(v)
            out.append((v, _estilo_valor(v)))
            anchos[i] = max(anchos[i], min(len(str(v)) + 4, 40))
        filas.append(out)
    return {"nombre": nombre, "filas": filas, "anchos": [min(a, 40) for a in anchos]}

def _hoja_xml(h):
    p = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
         '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">']
    if h.get("anchos"):
        p.append("<cols>")
        for i, w in enumerate(h["anchos"], 1):
            p.append('<col min="%d" max="%d" width="%d" customWidth="1"/>' % (i, i, int(w)))
        p.append("</cols>")
    p.append("<sheetData>")
    for r, fila in enumerate(h["filas"], 1):
        p.append('<row r="%d">' % r)
        for c, celda in enumerate(fila):
            valor, estilo = celda if isinstance(celda, tuple) else (celda, E_NORMAL)
            valor = _celda(valor)
            ref = _col_letra(c) + str(r)
            if isinstance(valor, bool):
                valor = str(valor)
            if isinstance(valor, (int, float)):
                num = repr(valor) if isinstance(valor, float) else str(valor)
                p.append('<c r="%s" s="%d"><v>%s</v></c>' % (ref, estilo, num))
            elif valor == "":
                p.append('<c r="%s" s="%d"/>' % (ref, estilo))
            else:
                t = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", str(valor))
                p.append('<c r="%s" s="%d" t="inlineStr"><is><t xml:space="preserve">%s</t></is></c>'
                         % (ref, estilo, _xml_escape(t)))
        p.append("</row>")
    p.append("</sheetData></worksheet>")
    return "".join(p)

def xlsx_crear(hojas):
    """Devuelve los bytes de un .xlsx. hojas = [{'nombre','filas','anchos'}, ...]"""
    nombres, usados = [], set()
    for i, h in enumerate(hojas, 1):
        n = re.sub(r"[\[\]:*?/\\]", "", h["nombre"])[:31] or ("Hoja" + str(i))
        while n in usados:
            n = n[:28] + "_" + str(i)
        usados.add(n)
        nombres.append(n)
    n = len(hojas)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        ct = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
              '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
              '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
              '<Default Extension="xml" ContentType="application/xml"/>'
              '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
              '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>']
        for i in range(1, n + 1):
            ct.append('<Override PartName="/xl/worksheets/sheet%d.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' % i)
        ct.append("</Types>")
        z.writestr("[Content_Types].xml", "".join(ct))
        z.writestr("_rels/.rels",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
                   '</Relationships>')
        wb = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
              '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
              'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>']
        for i, nom in enumerate(nombres, 1):
            wb.append('<sheet name="%s" sheetId="%d" r:id="rId%d"/>' % (_xml_escape(nom, {'"': "&quot;"}), i, i))
        wb.append("</sheets></workbook>")
        z.writestr("xl/workbook.xml", "".join(wb))
        rels = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">']
        for i in range(1, n + 1):
            rels.append('<Relationship Id="rId%d" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet%d.xml"/>' % (i, i))
        rels.append('<Relationship Id="rId%d" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>' % (n + 1))
        rels.append("</Relationships>")
        z.writestr("xl/_rels/workbook.xml.rels", "".join(rels))
        z.writestr("xl/styles.xml", _ESTILOS_XML)
        for i, h in enumerate(hojas, 1):
            z.writestr("xl/worksheets/sheet%d.xml" % i, _hoja_xml(h))
    return buf.getvalue()


def mod_reportes():
    st.title("📋 Reportes")
    st.info("Reportes listos para la Autoridad Fiscalizadora (DGMN/SERNAGEOMIN). Se generan en Excel (.xlsx).")
    tipo = st.selectbox("Tipo", ["Reporte mensual completo", "Discrepancias", "Movimientos", "Condiciones", "Flota"])
    periodo = st.date_input("Período", value=date.today())
    if st.button("📥 Generar Excel", type="primary"):
        inv = get_inv()
        inv["estado_calc"] = inv.apply(clasificar, axis=1)
        movs = get_movs()
        viajes = get_viajes()
        cond = get_cond()
        alertas = generar_alertas()
        hojas = [hoja_df("Inventario", inv.drop(columns=["qr_data"], errors="ignore"), "INVENTARIO — " + str(periodo))]
        if tipo in ["Reporte mensual completo", "Movimientos"]:
            hojas.append(hoja_df("Movimientos", movs, "MOVIMIENTOS — " + str(periodo)))
        if tipo in ["Reporte mensual completo", "Discrepancias"]:
            df_a = pd.DataFrame(alertas) if alertas else pd.DataFrame(columns=["gravedad", "icono", "lote", "exp", "msg", "accion"])
            hojas.append(hoja_df("Alertas", df_a, "ALERTAS — " + str(periodo)))
        if tipo in ["Reporte mensual completo", "Condiciones"]:
            hojas.append(hoja_df("Condiciones", cond, "CONDICIONES AMBIENTALES — " + str(periodo)))
        if tipo in ["Reporte mensual completo", "Flota"]:
            hojas.append(hoja_df("Flota", viajes, "FLOTA Y TRASLADOS — " + str(periodo)))
        st.session_state["rep_bytes"] = xlsx_crear(hojas)
        st.session_state["rep_nombre"] = "reporte_polvorin_" + str(periodo) + ".xlsx"
        st.session_state["rep_tipo"] = tipo
    if st.session_state.get("rep_bytes"):
        st.success("✅ Reporte generado: " + st.session_state.get("rep_tipo", ""))
        st.download_button(label="📥 Descargar " + st.session_state.get("rep_tipo", "reporte"),
                           data=st.session_state["rep_bytes"], file_name=st.session_state["rep_nombre"],
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


def mod_auditoria():
    st.title("🔍 Auditoría Física")
    st.info("Conteo físico mensual. El sistema compara con el registro digital y detecta discrepancias.")
    conn=get_conn()
    try: aud=pd.read_sql("SELECT * FROM auditorias ORDER BY fecha DESC",conn)
    except Exception: aud=pd.DataFrame()
    conn.close()
    t1,t2=st.tabs(["📋 Historial","➕ Nuevo conteo"])
    with t1:
        if aud.empty: st.info("Sin auditorías registradas.")
        else: st.dataframe(aud, use_container_width=True, hide_index=True)
    with t2:
        if not puede("todo"): st.info("Solo el administrador puede realizar auditorías."); return
        inv=get_inv()
        with st.form("form_aud"):
            conteos={}
            for exp in EXPLOSIVOS_CFG:
                stock=int(inv[inv["explosivo"]==exp]["cantidad"].sum()) if not inv.empty else 0
                conteos[exp]=st.number_input(exp+" (sistema: "+str(stock)+" "+EXPLOSIVOS_CFG[exp]["unidad"]+")",min_value=0,value=stock)
            obs_a=st.text_area("Observaciones",height=60)
            sub_a=st.form_submit_button("✅ Confirmar conteo",type="primary")
        if sub_a:
            conn=get_conn()
            for exp,cnt_r in conteos.items():
                stock=int(inv[inv["explosivo"]==exp]["cantidad"].sum()) if not inv.empty else 0
                diff=cnt_r-stock
                est="Aprobada" if diff==0 else ("Discrepancia leve" if abs(diff)<=2 else "Discrepancia crítica")
                conn.execute("INSERT INTO auditorias VALUES (?,?,?,?,?,?,?,?,?)",
                             (uuid.uuid4().hex[:8].upper(),str(date.today()),st.session_state["nombre"],exp,stock,cnt_r,diff,est,obs_a))
            conn.commit(); conn.close()
            st.success("✅ Auditoría registrada."); st.rerun()

def mod_admin():
    st.title("🏢 Administración del Sistema")
    if not puede("todo"): st.error("Acceso restringido al administrador."); return
    t1,t2,t3,t4=st.tabs(["👷 Usuarios","🏢 Proveedores","⚙️ Configuración","🔑 Credenciales"])
    with t1:
        users=get_df("SELECT id,nombre,usuario,rol,licencia_venc,activo FROM usuarios")
        st.dataframe(users, use_container_width=True, hide_index=True)
        st.subheader("Actualizar licencia")
        with st.form("form_lic"):
            uid=st.selectbox("Usuario",users["usuario"].tolist())
            nlic=st.date_input("Nueva fecha licencia",value=date.today()+timedelta(days=365))
            sub_l=st.form_submit_button("Actualizar")
        if sub_l:
            conn=get_conn(); conn.execute("UPDATE usuarios SET licencia_venc=? WHERE usuario=?",(str(nlic),uid)); conn.commit(); conn.close()
            st.success("✅ Licencia actualizada."); st.rerun()
        st.subheader("Crear usuario")
        with st.form("form_usr"):
            c1,c2=st.columns(2); n_nom=c1.text_input("Nombre"); n_usr=c2.text_input("Usuario")
            c3,c4=st.columns(2); n_pin=c3.text_input("PIN",type="password"); n_rol=c4.selectbox("Rol",["operario","jefe_turno","solo_lectura"])
            n_lic=st.date_input("Vencimiento licencia",value=date.today()+timedelta(days=365))
            sub_u=st.form_submit_button("Crear")
        if sub_u:
            conn=get_conn(); conn.execute("INSERT INTO usuarios VALUES (?,?,?,?,?,?,1)",("USR-"+uuid.uuid4().hex[:6].upper(),n_nom,n_usr,hash_pin(n_pin),n_rol,str(n_lic))); conn.commit(); conn.close()
            st.success("✅ Usuario creado."); st.rerun()
    with t2:
        provs=get_df("SELECT * FROM proveedores"); st.dataframe(provs, use_container_width=True, hide_index=True)
        with st.form("form_prov"):
            c1,c2=st.columns(2); p_nom=c1.text_input("Nombre"); p_rut=c2.text_input("RUT"); p_c=st.text_input("Contacto")
            sub_p=st.form_submit_button("Agregar")
        if sub_p:
            conn=get_conn(); conn.execute("INSERT INTO proveedores VALUES (?,?,?,?,1)",("PROV-"+uuid.uuid4().hex[:6].upper(),p_nom,p_rut,p_c)); conn.commit(); conn.close()
            st.success("✅ Proveedor agregado."); st.rerun()
    with t3:
        st.dataframe(pd.DataFrame([{"Explosivo":k,"Tipo":v["tipo"],"Unidad":v["unidad"],"Peso/ud(kg)":v["peso_kg"],"Stock mín":v["stock_min"],"Vida útil(d)":v["vida_dias"],"Almacén":v["almacen"],"Temp.máx(°C)":v["temp_max"],"Hum.máx(%)":v["hum_max"]} for k,v in EXPLOSIVOS_CFG.items()]), use_container_width=True, hide_index=True)
        st.subheader("Capacidades máximas (S = 1,5 · ∛W)")
        st.dataframe(pd.DataFrame([{"Almacén":k,"Kg máx":v["kg_max"],"Dist.seg.(m)":v["dist_m"],"Alerta 90%(kg)":round(v["kg_max"]*0.9,1)} for k,v in CAPACIDADES.items()]), use_container_width=True, hide_index=True)
    with t4:
        st.warning("⚠️ Solo visible para el administrador. Cambiar en producción.")
        st.dataframe(pd.DataFrame({"Rol":["Administrador","Jefe Turno","Operario","Inspector","Op.bloqueado"],"Usuario":["admin","jefe_turno","operario1","inspector","operario3"],"PIN":["1234","5678","9012","7890","1111"],"Nota":["Acceso total","Ops+reportes","Lic.vigente","Solo lectura","Lic.vencida"]}), hide_index=True, use_container_width=True)

def mod_manual():
    st.title("📖 Manual de Usuario")
    t1,t2,t3=st.tabs(["🚀 Guía rápida","📚 Tutoriales","📘 Glosario"])
    with t1:
        for titulo,pasos in [
            ("📥 Registrar ingreso",["1. Inventario → Ingreso","2. Seleccionar explosivo y cantidad","3. Elegir proveedor habilitado y N° guía","4. Confirmar fecha de vencimiento","5. El sistema verifica capacidad y registra"]),
            ("📤 Despachar explosivos",["1. Inventario → Despacho","2. Seleccionar tipo de explosivo","3. El sistema elige automáticamente el lote más antiguo (FIFO)","4. Ingresar destino, vehículo y N° orden","5. El sistema registra el viaje y actualiza el inventario"]),
            ("🚪 Registrar acceso al polvorín",["1. Accesos → Nuevo acceso","2. Seleccionar operador y tipo (Ingreso/Egreso)","3. El sistema verifica el límite de 5 personas","4. Confirmar y registrar"]),
            ("📋 Generar reporte para la AF",["1. Reportes → Seleccionar tipo y período","2. Clic en Generar Excel","3. Descargar y entregar a la Autoridad Fiscalizadora"]),
        ]:
            with st.expander(titulo):
                for p in pasos: st.markdown("- "+p)
    with t2:
        for titulo,desc in [
            ("🔐 Autenticación","Cada usuario accede con usuario y PIN. Los operarios deben tener licencia vigente. Si vence, el sistema bloquea el acceso hasta que el administrador la actualice."),
            ("⚖️ Capacidad máxima","El sistema calcula en tiempo real los kg en cada almacén. Al 90% emite alerta amarilla. Al 100% bloquea nuevos ingresos. Fórmula: S = 1,5 × ∛W (DS 132)."),
            ("📦 FIFO normativo","Al despachar, el sistema selecciona automáticamente el lote más antiguo. Evita que material vencido quede almacenado. No se puede saltar el orden."),
            ("🚨 Alertas automáticas","Se generan sin intervención del operario. Críticas (rojo) = acción inmediata. Altas (amarillo) = acción urgente. Medias (anaranjado) = seguimiento."),
            ("🔍 Auditoría física","Mensualmente el administrador realiza un conteo físico. El sistema compara con el registro digital y genera el informe de discrepancias automáticamente."),
        ]:
            with st.expander(titulo): st.markdown(desc)
    with t3:
        for term,defin in [
            ("ANFO","Mezcla de Nitrato de Amonio y Petróleo (94%/6%). Explosivo secundario de uso masivo en tronadura."),
            ("Emulsión","Explosivo industrial de alta potencia y resistencia al agua. Usado en condiciones adversas."),
            ("Fulminante N8","Detonador primario. Inicia la detonación de los explosivos secundarios."),
            ("FIFO","First In, First Out — Primero que entra, primero que sale. Rotación obligatoria de inventario."),
            ("Lote","Conjunto de explosivos del mismo tipo ingresado en una misma recepción, con código único."),
            ("Guía de despacho","Documento del proveedor que acompaña cada entrega. Debe coincidir con lo recibido."),
            ("AF / Autoridad Fiscalizadora","DGMN o SERNAGEOMIN según corresponda. Supervisa y autoriza el uso de explosivos."),
            ("Libro de control","Registro obligatorio de todos los movimientos. Debe presentarse mensualmente a la AF."),
            ("Manipulador de explosivos","Persona certificada por Sernageomin para operar con explosivos. Licencia obligatoria vigente."),
            ("DS 132","Decreto Supremo N°132 de Sernageomin. Reglamento de Seguridad Minera."),
        ]:
            with st.expander("📘 "+term): st.markdown(defin)

# ══════════════════════════════════════════════════════════════════════════════
# PARTE 2 — MÓDULOS DE GESTIÓN Y ANÁLISIS
# ══════════════════════════════════════════════════════════════════════════════
KPI_ESCALA_ESTADO = {"Logrado": "#2E9E5B", "En progreso": "#F2B134", "Rezagado": "#D64545"}
MENOR_ES_MEJOR = ("min", "N°/mes")

def _escala_estado():
    return alt.Scale(domain=list(KPI_ESCALA_ESTADO.keys()), range=list(KPI_ESCALA_ESTADO.values()))

def progreso_kpi(base, meta, valor):
    """Avance hacia la meta en %. 0% = en la línea base, 100% = meta alcanzada.
    Funciona igual cuando más es mejor y cuando menos es mejor."""
    denom = float(meta) - float(base)
    if denom == 0:
        return 100.0 if float(valor) == float(meta) else 0.0
    p = (float(valor) - float(base)) / denom * 100.0
    return float(max(0.0, min(150.0, p)))

def estado_kpi(p):
    if p >= 100:
        return "Logrado"
    if p >= 50:
        return "En progreso"
    return "Rezagado"

def kpi_tabla():
    kpis = get_kpis()
    hist = get_khist()
    if kpis.empty:
        return pd.DataFrame(), pd.DataFrame(), kpis
    if not hist.empty:
        hist = hist.copy()
        hist["prio"] = (hist["registrado_por"] != "sistema").astype(int)
        h = hist.sort_values(["fecha", "prio"]).groupby(["kpi_id", "periodo"], as_index=False).last()
    else:
        h = hist
    rows = []
    for _, k in kpis.iterrows():
        hk = h[h["kpi_id"] == k["id"]].sort_values("periodo") if not h.empty else pd.DataFrame()
        actual = float(hk["valor_real"].iloc[-1]) if not hk.empty else float(k["valor_base"])
        p = progreso_kpi(k["valor_base"], k["meta_6m"], actual)
        rows.append({
            "id": k["id"], "kpi": k["nombre"], "area": k["area"], "unidad": k["unidad"],
            "descripcion": k["descripcion"], "base": float(k["valor_base"]),
            "actual": round(actual, 1), "meta6": float(k["meta_6m"]),
            "meta12": float(k["meta_12m"]), "progreso": round(p, 1), "estado": estado_kpi(p),
        })
    return pd.DataFrame(rows), h, kpis

def kpi_evolucion(h, kpis):
    if h.empty:
        return pd.DataFrame()
    ref = kpis[["id", "valor_base", "meta_6m", "area"]].rename(columns={"id": "kpi_id"})
    m = h.merge(ref, on="kpi_id")
    m["progreso"] = m.apply(
        lambda r: min(100.0, progreso_kpi(r["valor_base"], r["meta_6m"], r["valor_real"])), axis=1)
    return m

# ── Gráficos (funciones puras: devuelven un gráfico Altair) ──────────────────
def ch_donut(dff, glob):
    dist = dff["estado"].value_counts().reset_index()
    dist.columns = ["estado", "n"]
    donut = alt.Chart(dist).mark_arc(innerRadius=60, outerRadius=100).encode(
        theta=alt.Theta("n:Q"),
        color=alt.Color("estado:N", scale=_escala_estado(), legend=alt.Legend(title=None, orient="bottom")),
        tooltip=["estado:N", "n:Q"])
    centro = alt.Chart(pd.DataFrame({"t": [str(round(glob)) + "%"]})).mark_text(
        size=30, fontWeight="bold", color="#1F3864").encode(text="t:N")
    return (donut + centro).properties(height=270)

def ch_barras_avance(dff):
    orden = dff.sort_values("progreso", ascending=False)["kpi"].tolist()
    base_c = alt.Chart(dff)
    barras = base_c.mark_bar(cornerRadiusEnd=4, size=18).encode(
        y=alt.Y("kpi:N", sort=orden, title=None, axis=alt.Axis(labelLimit=300)),
        x=alt.X("progreso:Q", title="Avance hacia la meta (%)", scale=alt.Scale(domain=[0, 150])),
        color=alt.Color("estado:N", scale=_escala_estado(), legend=alt.Legend(title=None, orient="bottom")),
        tooltip=["kpi:N", "area:N", "base:Q", "actual:Q", "meta6:Q", "meta12:Q", "unidad:N", "progreso:Q"])
    etiquetas = base_c.mark_text(align="left", dx=4, color="#333").encode(
        y=alt.Y("kpi:N", sort=orden), x="progreso:Q", text=alt.Text("progreso:Q", format=".0f"))
    linea100 = alt.Chart(pd.DataFrame({"x": [100]})).mark_rule(
        color="#1F3864", strokeDash=[6, 4], size=2).encode(x="x:Q")
    return (barras + etiquetas + linea100).properties(height=max(260, 36 * len(dff)))

def ch_evolucion_global(g):
    g = g.copy()
    g["etq"] = g["progreso"].round(0).astype(int).astype(str) + "%"
    b = alt.Chart(g)
    area = b.mark_area(opacity=0.2, color="#2E75B6").encode(
        x=alt.X("periodo:O", title=None, axis=alt.Axis(labelAngle=0)),
        y=alt.Y("progreso:Q", title="Cumplimiento global (%)", scale=alt.Scale(domain=[0, 115])))
    linea = b.mark_line(color="#1F3864", point=alt.OverlayMarkDef(color="#1F3864", size=60)).encode(
        x="periodo:O", y="progreso:Q",
        tooltip=[alt.Tooltip("periodo:O", title="Período"), alt.Tooltip("progreso:Q", title="Cumplimiento (%)", format=".1f")])
    etq = b.mark_text(dy=-12, fontWeight="bold", color="#1F3864").encode(x="periodo:O", y="progreso:Q", text="etq:N")
    meta = alt.Chart(pd.DataFrame({"y": [100]})).mark_rule(color="#2E9E5B", strokeDash=[6, 4], size=2).encode(y="y:Q")
    meta_t = alt.Chart(pd.DataFrame({"y": [100], "t": ["Meta a 6 meses = 100%"]})).mark_text(
        align="left", dy=-8, color="#2E9E5B", fontWeight="bold").encode(y="y:Q", text="t:N", x=alt.value(4))
    return (area + linea + etq + meta + meta_t).properties(height=290)

def ch_spark(hk, meta6, color):
    vals = list(hk["valor_real"]) + [meta6]
    lo, hi = min(vals), max(vals)
    pad = (hi - lo) * 0.15 or 1.0
    esc = alt.Scale(zero=False, domain=[lo - pad, hi + pad])
    lin = alt.Chart(hk).mark_line(point=alt.OverlayMarkDef(color=color), color=color).encode(
        x=alt.X("periodo:O", axis=None), y=alt.Y("valor_real:Q", axis=None, scale=esc),
        tooltip=[alt.Tooltip("periodo:O", title="Período"), alt.Tooltip("valor_real:Q", title="Valor")])
    meta = alt.Chart(pd.DataFrame({"y": [meta6]})).mark_rule(
        strokeDash=[4, 3], color="#2E9E5B", size=1.5).encode(y=alt.Y("y:Q", axis=None, scale=esc))
    return (lin + meta).properties(height=75)

def ch_comparacion(r):
    etapas = ["Línea base", "Actual", "Meta 6 meses", "Meta 12 meses"]
    comp = pd.DataFrame({"Etapa": etapas, "Valor": [r["base"], r["actual"], r["meta6"], r["meta12"]]})
    esc = alt.Scale(domain=etapas, range=["#9AA5B1", "#2E75B6", "#F2B134", "#2E9E5B"])
    cols = alt.Chart(comp).mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4).encode(
        x=alt.X("Etapa:N", sort=etapas, title=None, axis=alt.Axis(labelAngle=0)),
        y=alt.Y("Valor:Q", title=r["unidad"]),
        color=alt.Color("Etapa:N", scale=esc, legend=None), tooltip=["Etapa:N", "Valor:Q"])
    txt = alt.Chart(comp).mark_text(dy=-8, fontWeight="bold").encode(
        x=alt.X("Etapa:N", sort=etapas), y="Valor:Q", text=alt.Text("Valor:Q", format=".1f"))
    return (cols + txt).properties(height=300)

def ch_evolucion_kpi(hk, r):
    dom = ["Línea base", "Meta 6 meses", "Meta 12 meses"]
    esc = alt.Scale(domain=dom, range=["#9AA5B1", "#F2B134", "#2E9E5B"])
    lin = alt.Chart(hk).mark_line(point=True, color="#2E75B6").encode(
        x=alt.X("periodo:O", title=None, axis=alt.Axis(labelAngle=0)),
        y=alt.Y("valor_real:Q", title=r["unidad"]),
        tooltip=[alt.Tooltip("periodo:O", title="Período"), alt.Tooltip("valor_real:Q", title="Valor")])
    refs = pd.DataFrame({"y": [r["base"], r["meta6"], r["meta12"]], "Referencia": dom})
    reglas = alt.Chart(refs).mark_rule(strokeDash=[5, 4], size=2).encode(
        y="y:Q", color=alt.Color("Referencia:N", scale=esc, legend=None))
    etiq = alt.Chart(refs).mark_text(align="left", dy=-6, fontWeight="bold").encode(
        y="y:Q", x=alt.value(4), text="Referencia:N", color=alt.Color("Referencia:N", scale=esc, legend=None))
    return (lin + reglas + etiq).properties(height=300)

def ch_mov_dia(g):
    esc = alt.Scale(domain=["Ingreso", "Despacho", "Devolucion"], range=["#2E9E5B", "#2E75B6", "#F2B134"])
    tope = int(g.groupby("fecha")["n"].sum().max()) if not g.empty else 1
    return alt.Chart(g).mark_bar(size=34).encode(
        x=alt.X("fecha:O", title="Día", axis=alt.Axis(labelAngle=-30)),
        y=alt.Y("n:Q", title="N° de movimientos", axis=alt.Axis(values=list(range(0, tope + 1)), format="d")),
        color=alt.Color("tipo_mov:N", scale=esc, legend=alt.Legend(title="Tipo", orient="bottom")),
        tooltip=[alt.Tooltip("fecha:O", title="Día"), alt.Tooltip("tipo_mov:N", title="Tipo"), alt.Tooltip("n:Q", title="Movimientos")]
    ).properties(height=280)

def ch_mov_explosivo(u):
    esc = alt.Scale(domain=["Ingreso", "Despacho", "Devolucion"], range=["#2E9E5B", "#2E75B6", "#F2B134"])
    return alt.Chart(u).mark_bar().encode(
        x=alt.X("explosivo:N", title=None, axis=alt.Axis(labelAngle=0)),
        xOffset="tipo_mov:N",
        y=alt.Y("unidades:Q", title="Unidades (sacos / cajas / rollos)"),
        color=alt.Color("tipo_mov:N", scale=esc, legend=alt.Legend(title="Tipo", orient="bottom")),
        tooltip=[alt.Tooltip("explosivo:N", title="Explosivo"), alt.Tooltip("tipo_mov:N", title="Tipo"), alt.Tooltip("unidades:Q", title="Unidades")]
    ).properties(height=280)

def _tarjeta_kpi(r, h):
    color = KPI_ESCALA_ESTADO[r["estado"]]
    direccion = "↓ menor es mejor" if r["unidad"] in MENOR_ES_MEJOR else "↑ mayor es mejor"
    ancho = str(min(100, int(round(r["progreso"]))))
    st.markdown(
        '<div style="font-weight:600;font-size:.92em;color:#1F3864;line-height:1.25;">' + r["kpi"] + '</div>'
        '<div style="font-size:.74em;color:#777;margin-bottom:4px;">' + r["area"] + ' · ' + direccion + '</div>'
        '<div style="font-size:1.9em;font-weight:700;color:' + color + ';line-height:1.1;">' + str(r["actual"]) +
        ' <span style="font-size:.42em;color:#777;font-weight:400;">' + r["unidad"] + '</span></div>'
        '<div style="background:#E6E9ED;border-radius:6px;height:9px;margin:6px 0 3px 0;">'
        '<div style="background:' + color + ';width:' + ancho + '%;height:9px;border-radius:6px;"></div></div>'
        '<div style="font-size:.76em;color:#555;">Avance <b>' + str(round(r["progreso"])) + '%</b> · base ' + str(r["base"]) +
        ' → meta ' + str(r["meta6"]) + ' · <b style="color:' + color + '">' + r["estado"] + '</b></div>',
        unsafe_allow_html=True)
    hk = h[h["kpi_id"] == r["id"]].sort_values("periodo") if not h.empty else pd.DataFrame()
    if not hk.empty:
        st.altair_chart(ch_spark(hk, r["meta6"], color), use_container_width=True)

def mod_kpis():
    st.title("📊 KPIs — Panel de Cumplimiento")
    st.caption("⚠️ Línea base, metas y evolución mensual son valores hipotéticos del caso simulado. "
               "Reemplazar con mediciones reales al implementar en faena (formulario al final de esta página).")
    st.markdown("""<style>
    .pbi-card{background:#fff;border-radius:10px;padding:14px 16px;box-shadow:0 2px 8px rgba(0,0,0,.08);border-top:5px solid #1F3864;}
    .pbi-val{font-size:2.1em;font-weight:700;line-height:1.1;}
    .pbi-lbl{font-size:.8em;color:#666;margin-top:2px;}
    </style>""", unsafe_allow_html=True)

    df, h, kpis = kpi_tabla()
    if df.empty:
        st.warning("Sin KPIs configurados.")
        return

    with st.expander("ℹ️ Cómo leer este panel", expanded=True):
        st.markdown(
            "- **Avance (%)** mide qué tan cerca está cada KPI de su meta a 6 meses: "
            "**0% = igual que la línea base (sin sistema)**, **100% = meta alcanzada**, más de 100% = meta superada.\n"
            "- Sirve igual para KPIs donde **más es mejor** (ej. % de lotes registrados) y donde **menos es mejor** "
            "(ej. minutos de inventario): en ambos casos, más avance = mejor.\n"
            "- **Colores:** 🟢 Logrado (100% o más) · 🟡 En progreso (50% a 99%) · 🔴 Rezagado (menos de 50%).\n"
            "- **Cumplimiento global** = promedio del avance de los KPIs en vista (cada KPI se topa en 100%).")

    areas = sorted(df["area"].unique().tolist())
    sel = st.multiselect("Segmentador · Área", areas, default=areas)
    dff = df[df["area"].isin(sel)] if sel else df.iloc[0:0]
    if dff.empty:
        st.info("Selecciona al menos un área.")
        return
    st.caption("Mostrando " + str(len(dff)) + " de " + str(len(df)) + " KPIs")
    glob = float(dff["progreso"].clip(upper=100).mean())

    def tarjeta(col, valor, etiqueta, color):
        col.markdown('<div class="pbi-card" style="border-top-color:' + color + '">'
                     '<div class="pbi-val" style="color:' + color + '">' + str(valor) + '</div>'
                     '<div class="pbi-lbl">' + etiqueta + '</div></div>', unsafe_allow_html=True)

    c1, c2, c3, c4, c5 = st.columns(5)
    tarjeta(c1, len(dff), "KPIs en vista", "#1F3864")
    tarjeta(c2, len(dff[dff["estado"] == "Logrado"]), "🟢 Logrados", "#2E9E5B")
    tarjeta(c3, len(dff[dff["estado"] == "En progreso"]), "🟡 En progreso", "#F2B134")
    tarjeta(c4, len(dff[dff["estado"] == "Rezagado"]), "🔴 Rezagados", "#D64545")
    tarjeta(c5, str(round(glob)) + "%", "Cumplimiento global", "#2E75B6")
    st.markdown("")

    col_a, col_b = st.columns([1, 2])
    with col_a:
        st.markdown("**Estado de los KPIs**")
        st.altair_chart(ch_donut(dff, glob), use_container_width=True)
    with col_b:
        st.markdown("**Avance de cada KPI hacia su meta a 6 meses** (línea punteada = 100%)")
        st.altair_chart(ch_barras_avance(dff), use_container_width=True)

    st.markdown("**Evolución del cumplimiento global por mes**")
    st.caption("Promedio mensual del avance de los KPIs en vista. Si la línea llega a la meta punteada (100%), "
               "el conjunto de KPIs cumplió lo esperado a 6 meses.")
    evo = kpi_evolucion(h, kpis)
    if not evo.empty:
        evo = evo[evo["area"].isin(sel)]
    if not evo.empty:
        g = evo.groupby("periodo", as_index=False)["progreso"].mean()
        st.altair_chart(ch_evolucion_global(g), use_container_width=True)
    else:
        st.info("Sin historial disponible para las áreas seleccionadas.")

    st.divider()
    st.subheader("🧩 Tablero de todos los KPIs")
    st.caption("Cada tarjeta: valor actual, avance hacia la meta a 6 meses y tendencia mensual "
               "(línea punteada verde = meta a 6 meses).")
    filas_kpi = [dff.iloc[i:i + 3] for i in range(0, len(dff), 3)]
    for bloque in filas_kpi:
        cols = st.columns(3)
        for col, (_, r) in zip(cols, bloque.iterrows()):
            with col:
                with st.container(border=True):
                    _tarjeta_kpi(r, h)

    st.divider()
    st.subheader("🔎 Detalle por KPI")
    kpi_sel = st.selectbox("Selecciona un KPI", dff["kpi"].tolist())
    r = dff[dff["kpi"] == kpi_sel].iloc[0]
    direccion = "menos es mejor: la meta es un valor MÁS BAJO que la base" if r["unidad"] in MENOR_ES_MEJOR \
        else "más es mejor: la meta es un valor MÁS ALTO que la base"
    st.caption(r["descripcion"] + " · Unidad: " + r["unidad"] + " · En este KPI " + direccion + ".")
    d1, d2 = st.columns(2)
    with d1:
        st.markdown("**Línea base vs valor actual vs metas**")
        st.altair_chart(ch_comparacion(r), use_container_width=True)
    with d2:
        st.markdown("**Evolución mensual y líneas de referencia**")
        hk = h[h["kpi_id"] == r["id"]].sort_values("periodo") if not h.empty else pd.DataFrame()
        if hk.empty:
            st.info("Sin historial para este KPI.")
        else:
            st.altair_chart(ch_evolucion_kpi(hk, r), use_container_width=True)

    st.divider()
    st.subheader("📋 Tabla de KPIs")
    tabla = dff[["kpi", "area", "unidad", "base", "actual", "meta6", "meta12", "progreso", "estado"]].rename(
        columns={"kpi": "KPI", "area": "Área", "unidad": "Unidad", "base": "Base", "actual": "Actual",
                 "meta6": "Meta 6m", "meta12": "Meta 12m", "progreso": "Avance (%)", "estado": "Estado"})

    def color_estado(v):
        return {"Logrado": "background-color:#C6EFCE;color:#1F5C1F",
                "En progreso": "background-color:#FFEB9C;color:#7F6000",
                "Rezagado": "background-color:#FFCCCC;color:#C00000"}.get(v, "")

    st.dataframe(tabla.style.map(color_estado, subset=["Estado"]), use_container_width=True, hide_index=True)

    if puede("kpis") or puede("todo"):
        st.divider()
        st.subheader("➕ Registrar medición real")
        with st.form("form_kpi"):
            f1, f2, f3 = st.columns(3)
            kpi_f = f1.selectbox("KPI", kpis["nombre"].tolist())
            val_r = f2.number_input("Valor medido", min_value=0.0, value=0.0, step=0.1)
            periodo = f3.text_input("Período (AAAA-MM)", value=date.today().strftime("%Y-%m"))
            sub_k = st.form_submit_button("✅ Registrar", type="primary")
        if sub_k:
            kid = kpis[kpis["nombre"] == kpi_f]["id"].iloc[0]
            conn = get_conn()
            conn.execute("INSERT OR REPLACE INTO kpi_historial VALUES (?,?,?,?,?,?)",
                         ("KHIST-" + kid + "-" + periodo + "-R", str(date.today()), kid, val_r,
                          periodo, st.session_state["nombre"]))
            conn.commit()
            conn.close()
            st.success("✅ Medición registrada.")
            st.rerun()


def mod_vista_rol():
    st.title("👁️ Vista por Rol")
    rol=st.session_state.get("rol","")
    inv=get_inv()
    if rol in ["administrador","jefe_turno"]:
        st.markdown("### Vista Jefe / Administrador")
        tab1,tab2,tab3,tab4=st.tabs(["📊 Resumen turno","📦 Inventario","🚛 Traslados","🔍 Auditorías"])
        with tab1:
            movs=get_movs(); viajes=get_viajes(); hoy=str(date.today())
            movs_h=movs[movs["fecha_hora"].str.startswith(hoy)] if not movs.empty else movs
            vj_h  =viajes[viajes["inicio"].str.startswith(hoy)] if not viajes.empty else viajes
            c1,c2,c3,c4=st.columns(4)
            c1.metric("Movimientos hoy",len(movs_h))
            c2.metric("Ingresos",len(movs_h[movs_h["tipo_mov"]=="Ingreso"]) if not movs_h.empty else 0)
            c3.metric("Despachos",len(movs_h[movs_h["tipo_mov"]=="Despacho"]) if not movs_h.empty else 0)
            c4.metric("Viajes hoy",len(vj_h))
            st.subheader("Movimientos de explosivos (últimos 60 días)")
            st.caption("Cómo leerlo: cada barra es un día y su altura es el N° de movimientos registrados, "
                       "separados por tipo (ingreso, despacho, devolución). Con pocos datos simulados habrá pocas barras: "
                       "cada ingreso o despacho que registres aparecerá aquí.")
            if movs.empty:
                st.info("Sin movimientos registrados.")
            else:
                m2 = movs.copy()
                m2["fecha"] = m2["fecha_hora"].str[:10]
                m60 = m2[m2["fecha"] >= str(date.today() - timedelta(days=60))]
                if m60.empty:
                    st.info("Sin movimientos en los últimos 60 días.")
                else:
                    g = m60.groupby(["fecha", "tipo_mov"]).size().reset_index(name="n")
                    st.altair_chart(ch_mov_dia(g), use_container_width=True)
                    u = m60.groupby(["explosivo", "tipo_mov"], as_index=False)["cantidad"].sum().rename(columns={"cantidad": "unidades"})
                    st.markdown("**Unidades movidas por explosivo** (comparación ingreso vs despacho vs devolución)")
                    st.altair_chart(ch_mov_explosivo(u), use_container_width=True)
        with tab2:
            if not inv.empty:
                inv_c=inv.copy(); inv_c["estado_calc"]=inv_c.apply(clasificar,axis=1)
                st.dataframe(inv_c.drop(columns=["qr_data"],errors="ignore"), use_container_width=True, hide_index=True)
        with tab3:
            vj2=get_viajes()
            if vj2.empty: st.info("Sin viajes.")
            else:
                st.dataframe(vj2, use_container_width=True, hide_index=True)
                if "ruta" in vj2.columns and "t_real" in vj2.columns:
                    opt=vj2.groupby("ruta").agg(T_prom=("t_real","mean"),Demora=("demora","mean"),Total=("id_viaje","count")).round(1).reset_index()
                    st.dataframe(opt, use_container_width=True, hide_index=True)
        with tab4:
            conn=get_conn()
            try: aud=pd.read_sql("SELECT * FROM auditorias ORDER BY fecha DESC",conn)
            except Exception: aud=pd.DataFrame()
            conn.close()
            if aud.empty: st.info("Sin auditorías.")
            else:
                st.dataframe(aud, use_container_width=True, hide_index=True)
                if "diferencia" in aud.columns:
                    disc_g=aud.groupby("explosivo")["diferencia"].sum().reset_index(); disc_g.columns=["Explosivo","Diferencia total"]
                    st.bar_chart(disc_g.set_index("Explosivo"))
    else:
        st.markdown("### Vista Operario")
        movs=get_movs(); hoy=str(date.today()); nom=st.session_state.get("nombre","")
        mis_m=movs[(movs["fecha_hora"].str.startswith(hoy))&(movs["operador"]==nom)] if not movs.empty else movs
        acc=get_accesos(); mis_a=acc[(acc["fecha_hora"].str.startswith(hoy))&(acc["operador"]==nom)] if not acc.empty else acc
        c1,c2,c3=st.columns(3)
        c1.metric("Mis movimientos hoy",len(mis_m))
        c2.metric("Mis ingresos",len(mis_a[mis_a["tipo"]=="Ingreso"]) if not mis_a.empty else 0)
        c3.metric("Mis egresos",len(mis_a[mis_a["tipo"]=="Egreso"])   if not mis_a.empty else 0)
        st.subheader("Mis operaciones de hoy")
        if mis_m.empty: st.info("Sin operaciones hoy.")
        else: st.dataframe(mis_m, use_container_width=True, hide_index=True)
        st.subheader("📦 Stock disponible para despacho")
        if not inv.empty:
            inv_c=inv.copy(); inv_c["estado_calc"]=inv_c.apply(clasificar,axis=1)
            st.dataframe(inv_c[inv_c["estado_calc"]=="Vigente"][["id_lote","explosivo","cantidad","unidad","fecha_vencimiento","almacen"]], use_container_width=True, hide_index=True)

def mod_libro_control():
    st.title("📋 Libro de Control — Exportación Oficial AF")
    st.info("Genera el libro de control mensual en formato para la Autoridad Fiscalizadora (DGMN/SERNAGEOMIN).")
    c1, c2 = st.columns(2)
    mes_sel = c1.selectbox("Mes", ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto",
                                   "Septiembre", "Octubre", "Noviembre", "Diciembre"], index=date.today().month - 1)
    anio_sel = c2.number_input("Año", min_value=2024, max_value=2030, value=date.today().year)
    if st.button("📥 Generar Libro Control Excel", type="primary"):
        movs = get_movs()
        inv = get_inv()
        acc = get_accesos()
        norma = "Normativa: DS N°132 SERNAGEOMIN · Ley N°17.798 · Resolución DGMN N°003048/2020"
        mov_c = ["id_mov", "id_lote", "explosivo", "tipo_mov", "cantidad", "fecha_hora", "operador",
                 "destino", "n_orden", "turno", "observaciones"]
        acc_c = ["id", "operador", "tipo", "fecha_hora", "motivo", "turno"]
        h1 = hoja_df("Libro de Movimientos", movs[[c for c in mov_c if c in movs.columns]] if not movs.empty else movs,
                     "LIBRO DE CONTROL DE EXPLOSIVOS — " + mes_sel.upper() + " " + str(anio_sel),
                     "Faena hipotética · Consumidor Habitual · Ley N°17.798", norma)
        h2 = hoja_df("Inventario al Cierre", inv.drop(columns=["qr_data"], errors="ignore"),
                     "INVENTARIO AL CIERRE DEL PERÍODO", "Estado al " + str(date.today()), norma)
        h3 = hoja_df("Control de Accesos", acc[[c for c in acc_c if c in acc.columns]] if not acc.empty else acc,
                     "REGISTRO DE ACCESOS AL POLVORÍN", "Control de personal — máx. 5 personas simultáneas (DS 132)", norma)

        def ce(kw):
            if inv.empty or "estado" not in inv.columns:
                return 0
            return len(inv[inv["estado"].str.upper().str.contains(kw, na=False)])

        def n_tipo(t):
            return len(movs[movs["tipo_mov"] == t]) if not movs.empty else 0

        sec = lambda t: [(t, E_NEGRITA)]
        filas = [
            [("RESUMEN EJECUTIVO — LIBRO DE CONTROL MENSUAL", E_TITULO)],
            ["Período", mes_sel + " " + str(anio_sel)],
            ["Fecha", datetime.now().strftime("%Y-%m-%d %H:%M")],
            ["Generado por", st.session_state.get("nombre", "")], [],
            sec("INVENTARIO"), ["Total lotes", len(inv)],
            ["Peso total (kg)", round(float(inv["peso_kg_total"].sum()), 2) if not inv.empty else 0],
            ["Vigentes", ce("VIGENTE")], ["Vencidos", ce("VENCIDO")], [],
            sec("MOVIMIENTOS"), ["Total", len(movs)], ["Ingresos", n_tipo("Ingreso")],
            ["Despachos", n_tipo("Despacho")], ["Devoluciones", n_tipo("Devolucion")], [],
            sec("ACCESOS"), ["Total accesos", len(acc)], [],
            sec("NORMATIVA"),
            ["DS N°132 SERNAGEOMIN", "Reglamento de Seguridad Minera"],
            ["Ley N°17.798", "Control de Armas y Explosivos"],
            ["Resolución DGMN N°003048/2020", "Almacenamiento productos Ley 17.798"],
            [], [],
            ["Firma: ___________________________"],
            ["Nombre: " + str(st.session_state.get("nombre", ""))],
            ["Cargo: Encargado de Polvorín"],
            ["Fecha: " + str(date.today())],
        ]
        h4 = {"nombre": "Resumen Ejecutivo", "filas": filas, "anchos": [38, 50]}
        st.session_state["libro_bytes"] = xlsx_crear([h1, h2, h3, h4])
        st.session_state["libro_nombre"] = "libro_control_" + mes_sel + "_" + str(anio_sel) + ".xlsx"
        st.session_state["libro_label"] = mes_sel + " " + str(anio_sel)
    if st.session_state.get("libro_bytes"):
        st.success("✅ Libro de control generado · 4 hojas: Movimientos, Inventario, Accesos, Resumen.")
        st.download_button(label="📥 Descargar Libro Control — " + st.session_state.get("libro_label", ""),
                           data=st.session_state["libro_bytes"], file_name=st.session_state["libro_nombre"],
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


def mod_asistente_ia():
    st.title("🤖 Asistente IA — Apoyo Operativo")
    st.markdown('<div class="aviso-ia">⚠️ <b>Aviso:</b> Este asistente entrega solo orientación de apoyo. Toda decisión operativa, de seguridad o normativa debe ser tomada por el operador responsable certificado. No reemplaza el criterio del manipulador de explosivos ni la autoridad de la AF.</div>', unsafe_allow_html=True)
    if "chat_ia" not in st.session_state: st.session_state["chat_ia"]=[]
    SISTEMA="""Eres un asistente de apoyo para operadores de polvorines mineros en Chile.
Tu rol es orientar sobre operaciones, normativa y uso del sistema de gestión de polvorín.
Normativa: DS N°132 SERNAGEOMIN (2002), Ley N°17.798 (2007), Resolución DGMN N°003048 (2020).
Explosivos: ANFO (secundario, saco 25kg), Emulsión (secundario, caja 20kg), Mecha de seguridad (secundario, rollo 5kg), Fulminante N8 (primario, caja 0.5kg).
Capacidades: Container secundarios=3.500kg (dist.50m), Bóveda primarios=400kg (dist.25m). Fórmula: W=(S/1.5)³.
Máx. personas simultáneas: 5. FIFO obligatorio. Licencia manipulador vigente obligatoria.
Responde en español, claro y breve. Siempre recuerda que toda decisión la toma el operador responsable."""
    RESPUESTAS_BASE={
        ("vencido","vencida","destruir","destrucción"):"Según la Ley 17.798 (Cap. VIII), un lote vencido debe ser destruido por combustión, explosión o detonación controlada, autorizada por la AF. El manipulador debe dejar constancia en un acta.",
        ("personas","ingresar","simultáneas","cuántas"):"El límite es 5 personas simultáneas dentro del polvorín (DS 132). El sistema bloquea nuevos ingresos al alcanzar ese límite. Ninguna persona debe permanecer sola dentro.",
        ("fifo","primero","antiguo","rotación"):"FIFO significa que el lote más antiguo se despacha primero. El sistema lo aplica automáticamente. Evita que material vencido quede almacenado.",
        ("capacidad","máxima","peso","kg","almacen"):"Fórmula: W=(S/1,5)³. Container secundarios=3.500kg (S=50m), Bóveda primarios=400kg (S=25m). El sistema alerta al 90% y bloquea al 100%.",
        ("af","autoridad","fiscalizadora","notificar","dgmn"):"Notifique a la AF ante: lotes próximos a vencer (<30 días), destrucción de explosivos vencidos, discrepancias en inventario, y entrega del libro de control mensual.",
        ("devolución","devolver","sobra","no usado"):"Use Inventario → Devolución. Ingrese el lote, la cantidad y el motivo. Queda registrado en el libro de control como 'Devolucion'.",
        ("temperatura","calor","ventilación","ambiental"):"Si la temperatura supera el límite (35°C container, 30°C bóveda), active la ventilación y notifique al jefe de turno. Ref: DS 132.",
        ("juntos","separados","primarios","secundarios","incompatibilidad"):"Los fulminantes NUNCA deben estar junto a ANFO, emulsión o mecha. Deben estar en recintos separados: bóveda para primarios, container para secundarios. Ref: DS 132 y Ley 17.798.",
    }
    def get_respuesta_base(preg):
        pl=preg.lower()
        for claves,resp in RESPUESTAS_BASE.items():
            if any(c in pl for c in claves):
                return resp+"\n\n*⚠️ Respuesta de referencia. Consulte al jefe de turno para decisiones operativas.*"
        return "No tengo información específica sobre esa consulta. Consulte el Manual o al jefe de turno.\n\n*⚠️ Toda decisión debe tomarla el operador responsable.*"
    def llamar_api(pregunta):
        try:
            import urllib.request
            mensajes=[]
            for msg in st.session_state["chat_ia"][-6:]:
                mensajes.append({"role":"user" if msg["rol"]=="usuario" else "assistant","content":msg["texto"]})
            mensajes.append({"role":"user","content":pregunta})
            payload=json.dumps({"model":"claude-sonnet-4-6","max_tokens":600,"system":SISTEMA,"messages":mensajes}).encode("utf-8")
            req=urllib.request.Request("https://api.anthropic.com/v1/messages",data=payload,headers={"Content-Type":"application/json","anthropic-version":"2023-06-01"},method="POST")
            with urllib.request.urlopen(req,timeout=15) as resp:
                data=json.loads(resp.read().decode("utf-8"))
                texto=data.get("content",[{}])[0].get("text","Sin respuesta.")
                return texto+"\n\n*⚠️ Solo orientación. Toda decisión debe tomarla el operador responsable.*"
        except Exception:
            return get_respuesta_base(pregunta)
    col1,col2=st.columns([2.5,1])
    with col2:
        st.markdown("**💡 Preguntas frecuentes:**")
        for pq in ["¿Qué hago con un lote vencido?","¿Cuántas personas pueden ingresar?","¿Cómo funciona el FIFO?","¿Qué es la capacidad máxima?","¿Cuándo notificar a la AF?","¿Cómo registrar una devolución?","¿Qué explosivos no pueden ir juntos?"]:
            if st.button(pq,use_container_width=True,key="pq_"+pq[:15]):
                st.session_state["chat_ia"].append({"rol":"usuario","texto":pq})
                with st.spinner("Consultando..."): resp=llamar_api(pq)
                st.session_state["chat_ia"].append({"rol":"asistente","texto":resp}); st.rerun()
        st.divider()
        if st.button("🗑️ Limpiar conversación",use_container_width=True): st.session_state["chat_ia"]=[]; st.rerun()
    with col1:
        if not st.session_state["chat_ia"]:
            st.markdown('<div class="chat-asistente">👋 Hola. Soy el asistente de apoyo del sistema de polvorín. ¿En qué te puedo ayudar?</div>', unsafe_allow_html=True)
        for msg in st.session_state["chat_ia"]:
            if msg["rol"]=="usuario": st.markdown('<div class="chat-usuario">👷 <b>Tú:</b> '+msg["texto"]+'</div>', unsafe_allow_html=True)
            else: st.markdown('<div class="chat-asistente">🤖 <b>Asistente:</b> '+msg["texto"]+'</div>', unsafe_allow_html=True)
        st.markdown("")
        with st.form("form_ia",clear_on_submit=True):
            preg=st.text_area("Tu pregunta:",height=80,placeholder="Ej: ¿Qué debo hacer si la temperatura supera los 35°C?")
            sub_ia=st.form_submit_button("Enviar →",type="primary",use_container_width=True)
        if sub_ia and preg.strip():
            st.session_state["chat_ia"].append({"rol":"usuario","texto":preg.strip()})
            with st.spinner("Consultando..."): resp=llamar_api(preg.strip())
            st.session_state["chat_ia"].append({"rol":"asistente","texto":resp}); st.rerun()

def mod_acerca():
    st.title("ℹ️ Acerca del Sistema")
    c1,c2=st.columns(2)
    with c1:
        st.markdown("""
### Sistema de Gestión de Polvorín Minero — v2.0
**Autor:** Cristóbal Rubio
**Institución:** Universidad Andrés Bello
**Carrera:** Ingeniería en Minería Subterránea
**Profesor guía:** Manuel Reyes · **Año:** 2026

---
### Normativa base
- DS N°132 SERNAGEOMIN (2002)
- Ley N°17.798 (2007) — Control de Armas
- Resolución DGMN N°003048 (2020)
- Ley N°17.798 Cap. VIII — Destrucción explosivos

---
### Estado actual
- **Versión:** Prototipo funcional
- **Datos:** Simulados (caso hipotético)
- **GPS:** Hipotético — arquitectura lista para GPS real
- **Sensores:** Simulados — lista para IoT real
- **Asistente IA:** API Claude (requiere internet, fallback offline)
""")
    with c2:
        st.markdown("""
### Módulos — Parte 1 (Operativo)
🔐 Autenticación con PIN y licencia · 🏠 Estado general con semáforo · 📥 Inventario con FIFO
🚨 Alertas automáticas · 🚪 Control de acceso · 🌡️ Condiciones ambientales
🚛 Flota y traslados · 📋 Reportes Excel · 🔍 Auditoría física · 🏢 Administración · 📖 Manual

### Módulos — Parte 2 (Gestión y Análisis)
📊 KPIs con curva de cumplimiento mensual · 👁️ Vista diferenciada por rol
📋 Libro de control formato AF · 🤖 Asistente IA con API Claude

### Módulos — Parte 3 (Simulador)
🎮 Simulador de escenarios y tiempo (con vs sin sistema) · 📚 Historial de simulaciones (registro, promedios en Excel y borrado) · 📘 Supuestos del modelo

---
### Trabajo futuro
- Conexión a sensores IoT reales
- GPS en vehículos de traslado
- Autenticación biométrica
- Sincronización en red local de faena
- Encriptación de base de datos
- App móvil para tablet en terreno
""")

# ══════════════════════════════════════════════════════════════════════════════
# PARTE 3 — SIMULADOR DE ESCENARIOS Y TIEMPO (motor, sin dependencias de Streamlit)
# ══════════════════════════════════════════════════════════════════════════════
SIM_DIAS_MES = 30
SIM_MESES_MAX = 12
SIM_DIAS_MAX = SIM_DIAS_MES * SIM_MESES_MAX
SIM_A12 = 0.90   # nivel de adopción a partir del cual el modelo alcanza su "meseta" (x = 1)

SIM_TARGET = {"ANFO": 60, "Emulsion": 40, "Mecha de seguridad": 10, "Fulminante N8": 15}
SIM_PESOS_DESP = {"ANFO": 0.45, "Emulsion": 0.30, "Mecha de seguridad": 0.10, "Fulminante N8": 0.15}
SIM_QTY = {"ANFO": (1, 4), "Emulsion": (1, 3), "Mecha de seguridad": (1, 1), "Fulminante N8": (1, 2)}
SIM_OPS_REF = 38      # operaciones/mes de referencia (para calibrar discrepancias)
SIM_ENV_REF = 6       # alertas ambientales/mes de referencia

def _sim_esc(nombre, desc, **kw):
    p = {"nombre": nombre, "desc": desc, "a0": 0.05, "a_inf": 0.90, "t_half": 4.0, "k": 0.7,
         "desp_dia": 1.0, "ing_sem": 1.6, "env_mes": SIM_ENV_REF, "p_demora_extra": 0.0,
         "stock_mult": 1.0, "retrocesos": []}
    p.update(kw)
    return p

SIM_ESCENARIOS = {
    "Adopción gradual (esperable)": _sim_esc(
        "Adopción gradual (esperable)",
        "El personal adopta el sistema de forma progresiva: ~73% de adopción al mes 6 y ~90% al mes 12. "
        "Demanda y clima normales."),
    "Adopción exitosa": _sim_esc(
        "Adopción exitosa",
        "Capacitación intensiva y apoyo de la jefatura: ~92% de adopción al mes 6.",
        a_inf=0.98, t_half=3.0, k=0.9),
    "Adopción lenta": _sim_esc(
        "Adopción lenta",
        "Resistencia al cambio: solo ~35% de adopción al mes 6 y ~62% al mes 12.",
        a_inf=0.65, t_half=6.0, k=0.5),
    "Rotación de personal": _sim_esc(
        "Rotación de personal",
        "Adopción buena, pero entran operarios nuevos en los meses 4 y 8 y el uso del sistema cae temporalmente.",
        a_inf=0.92, t_half=3.5, k=0.8, retrocesos=[(4.0, 1.0, 0.65), (8.0, 1.0, 0.65)]),
    "Alta demanda de tronadura": _sim_esc(
        "Alta demanda de tronadura",
        "La faena duplica los despachos y mantiene más stock (se acerca a la capacidad máxima del container).",
        desp_dia=2.2, ing_sem=3.2, stock_mult=1.6),
    "Clima adverso / sensores": _sim_esc(
        "Clima adverso / sensores",
        "Muchas alertas ambientales (15 al mes) y más demoras de traslado por mal clima.",
        env_mes=15, p_demora_extra=0.12),
    "Sin sistema (control)": _sim_esc(
        "Sin sistema (control)",
        "El sistema no se usa: sirve como línea base para comparar.",
        a0=0.0, a_inf=0.0),
    "Personalizado": _sim_esc(
        "Personalizado", "Define tú los parámetros con los controles que aparecen abajo."),
}

def sim_params_aleatorios(rng, seed):
    p = _sim_esc("Aleatorio #" + str(seed), "Parámetros sorteados con la semilla " + str(seed) + ".")
    p.update({"a0": round(rng.uniform(0.0, 0.15), 2), "a_inf": round(rng.uniform(0.5, 0.99), 2),
              "t_half": round(rng.uniform(1.5, 7.0), 1), "k": round(rng.uniform(0.4, 1.3), 2),
              "desp_dia": round(rng.uniform(0.6, 2.4), 1), "ing_sem": round(rng.uniform(1.0, 3.5), 1),
              "env_mes": rng.randint(3, 16), "p_demora_extra": round(rng.uniform(0.0, 0.15), 2),
              "stock_mult": round(rng.uniform(0.8, 1.6), 1)})
    if rng.random() < 0.4:
        p["retrocesos"] = [(round(rng.uniform(2.0, 10.0), 1), 1.0, round(rng.uniform(0.5, 0.8), 2))]
    return p

def sim_adopcion(p, dia):
    """Nivel de adopción del sistema (0-1) en un día dado: curva logística + retrocesos opcionales."""
    if p["a_inf"] <= 0:
        return 0.0
    t = dia / float(SIM_DIAS_MES)
    logi = 1.0 / (1.0 + math.exp(-p["k"] * (t - p["t_half"])))
    logi0 = 1.0 / (1.0 + math.exp(p["k"] * p["t_half"]))
    a = p["a0"] + (p["a_inf"] - p["a0"]) * (logi - logi0) / (1.0 - logi0)
    for ini, dur, fac in p.get("retrocesos", []):
        if ini <= t < ini + dur:
            a *= fac
    return max(0.0, min(1.0, a))

def sim_modelo(a):
    """Relaciones ASUMIDAS entre el nivel de adopción y el comportamiento operativo."""
    x = min(1.0, a / SIM_A12)
    return {
        "x": x,
        "p_venc": 0.60 + 0.40 * x,                 # lotes con vencimiento registrado
        "p_orden": 0.40 + 0.60 * x,                # despachos con orden de retiro
        "p_error": (8.0 / SIM_OPS_REF) * (1 - x),  # operaciones con discrepancia
        "p_libro": 0.50 + 0.50 * x,                # movimientos bien registrados en libro control
        "p_det": 0.30 + 0.70 * x,                  # vencimientos detectados a tiempo
        "p_tiempo": 0.55 + 0.40 * x,               # viajes dentro del tiempo esperado
        "t_desp": 25.0 - 18.4 * x,                 # minutos por despacho
        "p_resp": 1.0 / 6.0 + (5.0 / 6.0) * x,     # alertas ambientales con respuesta
        "t_inv": 45.0 - 37.8 * x,                  # minutos de inventario físico
        "t_rep": 3.0 + 117.0 * (1 - x) ** 2,       # minutos para el reporte a la AF
    }

def sim_esperado(kid, x):
    """Valor esperado (sin ruido) de cada KPI para un nivel x de adopción efectiva."""
    f = {"KPI-001": 100 * (0.60 + 0.40 * x), "KPI-002": 100 * (0.40 + 0.60 * x),
         "KPI-003": 45.0 - 37.8 * x, "KPI-004": 8.0 * (1 - x),
         "KPI-005": 100 * (0.30 + 0.70 * x), "KPI-006": 3.0 + 117.0 * (1 - x) ** 2,
         "KPI-007": 100 * (0.50 + 0.50 * x), "KPI-008": 100 * (0.55 + 0.40 * x),
         "KPI-009": 25.0 - 18.4 * x, "KPI-010": 5.0 * (1 - x)}
    return f[kid]

def sim_cumple(unidad, valor, meta):
    if valor is None or valor != valor:
        return None
    return valor <= meta if unidad in MENOR_ES_MEJOR else valor >= meta

def sim_adopcion_requerida(kid, unidad, meta):
    """Adopción mínima (0-1) con la que el valor ESPERADO del modelo cumple la meta; None si no se alcanza."""
    for i in range(0, 1001):
        x = i / 1000.0
        if sim_cumple(unidad, sim_esperado(kid, x), meta):
            return round(x * SIM_A12, 3)
    return None

# ── Estado y utilidades ──────────────────────────────────────────────────────
def _poisson(rng, lam):
    if lam <= 0:
        return 0
    L, k, p = math.exp(-lam), 0, 1.0
    while True:
        k += 1
        p *= rng.random()
        if p <= L:
            return k - 1

def _cnt0():
    return {"ing": 0, "ing_venc": 0, "desp": 0, "desp_orden": 0, "mov": 0, "mov_libro": 0, "err": 0,
            "viajes": 0, "viajes_ok": 0, "t_desp_sum": 0.0, "env": 0, "env_sin": 0}

def _sim_hoy(s):
    return s["fecha0"] + timedelta(days=s["dia"])

def _sim_log(s, tipo, detalle):
    s["eventos"].append({"fecha": str(_sim_hoy(s)), "dia": s["dia"], "tipo": tipo, "detalle": detalle})
    if len(s["eventos"]) > 4000:
        del s["eventos"][:500]

def _sim_stock(s, exp):
    return sum(l["cant"] for l in s["lotes"] if l["exp"] == exp and l["estado"] != "destruido")

def _sim_peso(s, alm):
    return sum(l["cant"] * EXPLOSIVOS_CFG[l["exp"]]["peso_kg"] for l in s["lotes"]
               if l["estado"] != "destruido" and EXPLOSIVOS_CFG[l["exp"]]["almacen"] == alm)

def _sim_elegir(rng, pesos):
    r = rng.random() * sum(pesos.values())
    acc = 0.0
    ultimo = None
    for k, w in pesos.items():
        acc += w
        ultimo = k
        if r <= acc:
            return k
    return ultimo

def _sim_nuevo_lote(s, exp, cant, ingreso, venc):
    s["n_lotes"] += 1
    lote = {"id": exp[:4].upper().replace(" ", "_") + "-S" + str(s["n_lotes"]).zfill(3), "exp": exp,
            "cant": cant, "ingreso": ingreso, "venc": venc, "estado": "vigente"}
    s["lotes"].append(lote)
    return lote

def _sim_estado(params, seed):
    s = {"params": params, "seed": seed, "rng": random.Random(seed), "fecha0": date.today(), "dia": 0,
         "lotes": [], "n_lotes": 0, "urg": {}, "cnt": _cnt0(), "kpi_mensual": [], "exp_ev": [],
         "snap": [], "eventos": [], "tot": {"quiebres": 0, "ing_bloq": 0, "desp_venc": 0, "err": 0,
                                           "env": 0, "env_sin": 0, "exp_n": 0, "exp_no_det": 0}}
    rng = s["rng"]
    for exp, cfg in EXPLOSIVOS_CFG.items():
        for _ in range(3 if exp == "ANFO" else 2):
            edad = rng.randint(5, 90)
            cant = max(1, int(SIM_TARGET[exp] * params["stock_mult"] * rng.uniform(0.25, 0.5)))
            rem = rng.randint(25, max(40, cfg["vida_dias"] - edad))
            _sim_nuevo_lote(s, exp, cant, s["fecha0"] - timedelta(days=edad), s["fecha0"] + timedelta(days=rem))
    for alm, cap in CAPACIDADES.items():      # el stock inicial nunca debe superar el 90% de la capacidad
        peso = _sim_peso(s, alm)
        if peso > 0.9 * cap["kg_max"]:
            f = 0.9 * cap["kg_max"] / peso
            for l in s["lotes"]:
                if EXPLOSIVOS_CFG[l["exp"]]["almacen"] == alm:
                    l["cant"] = max(1, int(l["cant"] * f))
    _sim_snapshot(s, sim_adopcion(params, 0), {"ing": 0, "desp": 0, "viajes": 0, "viajes_tarde": 0, "env": 0})
    return s

def sim_crear(params, seed):
    """Crea la simulación del escenario y su gemela 'sin sistema' (control) con la misma demanda y semilla."""
    p = dict(params)
    p["retrocesos"] = list(p.get("retrocesos", []))
    ctrl = dict(p)
    ctrl.update({"a0": 0.0, "a_inf": 0.0, "retrocesos": [], "nombre": "Sin sistema (control)"})
    return _sim_estado(p, seed), _sim_estado(ctrl, seed)

def sim_avanzar(s, c, dias):
    n = max(0, min(int(dias), SIM_DIAS_MAX - s["dia"]))
    for _ in range(n):
        _sim_dia(s)
        _sim_dia(c)
    return n

# ── Operaciones ──────────────────────────────────────────────────────────────
def _sim_entrega(s, m, exp, dia_c):
    rng, c, p = s["rng"], s["cnt"], s["params"]
    cfg = EXPLOSIVOS_CFG[exp]
    falt = SIM_TARGET[exp] * p["stock_mult"] - _sim_stock(s, exp)
    if falt < 1:
        return
    cant = max(1, int(falt * rng.uniform(0.6, 1.0)))
    alm = cfg["almacen"]
    if _sim_peso(s, alm) + cant * cfg["peso_kg"] > CAPACIDADES[alm]["kg_max"]:
        s["tot"]["ing_bloq"] += 1
        _sim_log(s, "Ingreso bloqueado", exp + ": " + str(cant) + " " + cfg["unidad"] +
                 " superarían la capacidad de " + alm)
        return
    hoy = _sim_hoy(s)
    rem = rng.randint(15, 90) if rng.random() < 0.30 else max(40, cfg["vida_dias"] - rng.randint(0, 30))
    lote = _sim_nuevo_lote(s, exp, cant, hoy, hoy + timedelta(days=rem))
    c["ing"] += 1
    c["mov"] += 1
    dia_c["ing"] += 1
    if rng.random() < m["p_venc"]:
        c["ing_venc"] += 1
    if rng.random() < m["p_libro"]:
        c["mov_libro"] += 1
    if rng.random() < m["p_error"]:
        c["err"] += 1
        s["tot"]["err"] += 1
        _sim_log(s, "Discrepancia", "Error de registro en el ingreso del lote " + lote["id"])
    _sim_log(s, "Ingreso", lote["id"] + ": " + str(cant) + " " + cfg["unidad"] + " de " + exp +
             " (vence en " + str(rem) + " días)")

def _sim_necesidad(s):
    mult = s["params"]["stock_mult"]
    pesos = {}
    for exp in SIM_TARGET:
        obj = SIM_TARGET[exp] * mult
        falt = obj - _sim_stock(s, exp)
        if falt >= 1:
            pesos[exp] = falt / obj + 0.05
    return _sim_elegir(s["rng"], pesos) if pesos else None

def _sim_despacho(s, a, m, dia_c):
    rng, c, p = s["rng"], s["cnt"], s["params"]
    hoy = _sim_hoy(s)
    exp = _sim_elegir(rng, SIM_PESOS_DESP)
    cfg = EXPLOSIVOS_CFG[exp]
    elegibles = [l for l in s["lotes"] if l["exp"] == exp and l["cant"] > 0 and l["estado"] != "destruido"]
    lote = None
    if elegibles:
        if rng.random() < a:   # el sistema impone FIFO y bloquea material vencido
            vigentes = [l for l in elegibles if hoy < l["venc"]]
            lote = min(vigentes, key=lambda l: l["ingreso"]) if vigentes else None
        else:                  # sin control: se toma cualquier lote (puede estar vencido)
            lote = rng.choice(elegibles)
    if lote is None:
        s["tot"]["quiebres"] += 1
        _sim_log(s, "Quiebre de stock", "No hay " + exp + " vigente para despachar")
        if exp not in s["urg"]:
            s["urg"][exp] = hoy + timedelta(days=rng.randint(1, 3))
        return
    lo, hi = SIM_QTY[exp]
    q = min(lote["cant"], rng.randint(lo, hi))
    lote["cant"] -= q
    c["desp"] += 1
    c["mov"] += 1
    dia_c["desp"] += 1
    if hoy >= lote["venc"]:
        s["tot"]["desp_venc"] += 1
        _sim_log(s, "Incidente de seguridad", "Se despachó material VENCIDO del lote " + lote["id"])
    if rng.random() < m["p_orden"]:
        c["desp_orden"] += 1
    if rng.random() < m["p_libro"]:
        c["mov_libro"] += 1
    if rng.random() < m["p_error"]:
        c["err"] += 1
        s["tot"]["err"] += 1
        _sim_log(s, "Discrepancia", "Error de registro en el despacho del lote " + lote["id"])
    c["t_desp_sum"] += min(60.0, max(4.0, rng.gauss(m["t_desp"], 3.0)))
    c["viajes"] += 1
    dia_c["viajes"] += 1
    if rng.random() < max(0.05, m["p_tiempo"] - p["p_demora_extra"]):
        c["viajes_ok"] += 1
    else:
        dia_c["viajes_tarde"] += 1
        _sim_log(s, "Viaje con demora", "Traslado de " + exp + " fuera del tiempo esperado")
    if _sim_stock(s, exp) < cfg["stock_min"] and exp not in s["urg"]:
        s["urg"][exp] = hoy + timedelta(days=rng.randint(1, 3))

def _sim_vencimientos(s, m):
    rng, hoy = s["rng"], _sim_hoy(s)
    mes = (s["dia"] - 1) // SIM_DIAS_MES + 1
    for l in s["lotes"]:
        if l["estado"] == "vigente" and l["cant"] > 0 and hoy >= l["venc"]:
            det = rng.random() < m["p_det"]
            s["exp_ev"].append({"mes": mes, "det": det})
            s["tot"]["exp_n"] += 1
            if det:
                _sim_log(s, "Vencimiento detectado", "Lote " + l["id"] + " vencido: destrucción autorizada")
                l["estado"], l["cant"] = "destruido", 0
            else:
                s["tot"]["exp_no_det"] += 1
                _sim_log(s, "Vencimiento NO detectado", "Lote " + l["id"] + " venció y sigue en el almacén")
                l["estado"] = "vencido_no_detectado"

def _sim_snapshot(s, a, dia_c):
    hoy = _sim_hoy(s)
    reg = {"fecha": str(hoy), "dia": s["dia"], "adopcion": round(a, 4)}
    for e in SIM_TARGET:
        reg[e] = _sim_stock(s, e)
    kg_c, kg_b = _sim_peso(s, "Container secundarios"), _sim_peso(s, "Boveda enterrada (primarios)")
    reg["pct_container"] = round(100.0 * kg_c / CAPACIDADES["Container secundarios"]["kg_max"], 1)
    reg["pct_boveda"] = round(100.0 * kg_b / CAPACIDADES["Boveda enterrada (primarios)"]["kg_max"], 1)
    reg["venc_pres"] = sum(1 for l in s["lotes"] if l["estado"] == "vencido_no_detectado" and l["cant"] > 0)
    reg["por_vencer"] = sum(1 for l in s["lotes"] if l["estado"] == "vigente" and l["cant"] > 0
                            and 0 < (l["venc"] - hoy).days <= 30)
    reg["stock_bajo"] = sum(1 for e in SIM_TARGET if reg[e] < EXPLOSIVOS_CFG[e]["stock_min"])
    reg["env_dia"] = dia_c["env"]
    reg["ing"], reg["desp"] = dia_c["ing"], dia_c["desp"]
    reg["viajes"], reg["viajes_tarde"] = dia_c["viajes"], dia_c["viajes_tarde"]
    reg["quiebres_acum"] = s["tot"]["quiebres"]
    reg["bloq_acum"] = s["tot"]["ing_bloq"]
    reg["venc_desp_acum"] = s["tot"]["desp_venc"]
    s["snap"].append(reg)

def _sim_cerrar_mes(s, a):
    c, rng, m = s["cnt"], s["rng"], sim_modelo(a)
    mes = s["dia"] // SIM_DIAS_MES

    def pct(n, d):
        return None if d == 0 else round(100.0 * n / d, 1)

    ev = [e for e in s["exp_ev"] if mes - 2 <= e["mes"] <= mes]    # ventana móvil de 3 meses
    activos = sum(1 for l in s["lotes"] if l["cant"] > 0 and l["estado"] != "destruido")
    f_lotes = 0.9 + 0.2 * min(1.5, activos / 14.0)
    vals = {
        "KPI-001": pct(c["ing_venc"], c["ing"]),
        "KPI-002": pct(c["desp_orden"], c["desp"]),
        "KPI-003": round(max(3.0, m["t_inv"] * f_lotes + rng.gauss(0, 1.5)), 1),
        "KPI-004": float(c["err"]),
        "KPI-005": pct(sum(1 for e in ev if e["det"]), len(ev)),
        "KPI-006": round(max(2.0, m["t_rep"] + rng.gauss(0, 2.0)), 1),
        "KPI-007": pct(c["mov_libro"], c["mov"]),
        "KPI-008": pct(c["viajes_ok"], c["viajes"]),
        "KPI-009": round(c["t_desp_sum"] / c["desp"], 1) if c["desp"] else None,
        "KPI-010": float(c["env_sin"]),
    }
    s["kpi_mensual"].append({"mes": mes, "adopcion": round(a, 3), "valores": vals,
                             "ops": c["mov"], "desp": c["desp"], "ing": c["ing"]})
    _sim_log(s, "Cierre de mes", "Mes " + str(mes) + " cerrado · adopción " + str(round(100 * a)) + "% · " +
             str(c["mov"]) + " operaciones")
    for l in s["lotes"]:   # la auditoría del cierre retira los vencidos que nadie detectó
        if l["estado"] == "vencido_no_detectado":
            _sim_log(s, "Auditoría", "Lote vencido " + l["id"] + " hallado en auditoría y destruido")
            l["estado"], l["cant"] = "destruido", 0
    s["cnt"] = _cnt0()

def _sim_dia(s):
    p, rng = s["params"], s["rng"]
    s["dia"] += 1
    hoy = _sim_hoy(s)
    a = sim_adopcion(p, s["dia"])
    m = sim_modelo(a)
    c = s["cnt"]
    dia_c = {"ing": 0, "desp": 0, "viajes": 0, "viajes_tarde": 0, "env": 0}
    for exp, f in list(s["urg"].items()):                 # reposiciones urgentes
        if f <= hoy:
            del s["urg"][exp]
            _sim_entrega(s, m, exp, dia_c)
    if rng.random() < min(1.0, p["ing_sem"] / 7.0):       # entrega programada
        exp = _sim_necesidad(s)
        if exp:
            _sim_entrega(s, m, exp, dia_c)
    for _ in range(_poisson(rng, p["desp_dia"])):         # despachos del día
        _sim_despacho(s, a, m, dia_c)
    _sim_vencimientos(s, m)
    for _ in range(_poisson(rng, p["env_mes"] / float(SIM_DIAS_MES))):   # alertas ambientales
        c["env"] += 1
        dia_c["env"] += 1
        s["tot"]["env"] += 1
        if rng.random() >= m["p_resp"]:
            c["env_sin"] += 1
            s["tot"]["env_sin"] += 1
            _sim_log(s, "Alerta ambiental sin respuesta", "Temperatura/humedad fuera de rango sin acción")
    _sim_snapshot(s, a, dia_c)
    if s["dia"] % SIM_DIAS_MES == 0:
        _sim_cerrar_mes(s, a)


# ══════════════════════════════════════════════════════════════════════════════
# PARTE 3 — SIMULADOR: tablas, gráficos y pantallas
# ══════════════════════════════════════════════════════════════════════════════
SIM_SERIES = ["Con sistema (escenario)", "Sin sistema (control)"]
SIM_COL_SERIES = ["#1F3864", "#7B4FA3"]

def sim_tabla(kdf, s):
    filas = []
    for _, k in kdf.iterrows():
        serie = [(m["mes"], m["valores"].get(k["id"])) for m in s["kpi_mensual"]]
        serie = [(mm, v) for mm, v in serie if v is not None and v == v]
        if not serie:
            continue
        actual = serie[-1][1]
        p = progreso_kpi(k["valor_base"], k["meta_6m"], actual)
        filas.append({"id": k["id"], "kpi": k["nombre"], "area": k["area"], "unidad": k["unidad"],
                      "descripcion": k["descripcion"], "base": float(k["valor_base"]),
                      "actual": round(float(actual), 1), "meta6": float(k["meta_6m"]),
                      "meta12": float(k["meta_12m"]), "progreso": round(p, 1), "estado": estado_kpi(p)})
    return pd.DataFrame(filas)

def sim_hist_df(s):
    filas = []
    for m in s["kpi_mensual"]:
        for kid, v in m["valores"].items():
            if v is None or v != v:
                continue
            filas.append({"kpi_id": kid, "periodo": "M" + str(m["mes"]).zfill(2), "mes": m["mes"],
                          "valor_real": float(v)})
    return pd.DataFrame(filas, columns=["kpi_id", "periodo", "mes", "valor_real"])

def _sim_prog_raw(base, meta, valor):
    """Avance hacia la meta SIN recorte inferior: negativo = peor que la línea base."""
    d = float(meta) - float(base)
    if d == 0:
        return 100.0 if float(valor) == float(meta) else 0.0
    return float(max(-50.0, min(100.0, (float(valor) - float(base)) / d * 100.0)))

def sim_global_df(s, ctrl, kdf):
    filas = []
    for etiqueta, eng in zip(SIM_SERIES, (s, ctrl)):
        for m in eng["kpi_mensual"]:
            ps = []
            for _, k in kdf.iterrows():
                v = m["valores"].get(k["id"])
                if v is None or v != v:
                    continue
                ps.append(_sim_prog_raw(k["valor_base"], k["meta_6m"], v))
            if ps:
                filas.append({"mes": m["mes"], "serie": etiqueta, "progreso": round(sum(ps) / len(ps), 1)})
    return pd.DataFrame(filas, columns=["mes", "serie", "progreso"])

def sim_kpi_series_df(kid, s, ctrl):
    filas = []
    for etiqueta, eng in zip(SIM_SERIES, (s, ctrl)):
        for m in eng["kpi_mensual"]:
            v = m["valores"].get(kid)
            if v is not None and v == v:
                filas.append({"mes": m["mes"], "valor": float(v), "serie": etiqueta})
    return pd.DataFrame(filas, columns=["mes", "valor", "serie"])

def sim_snap_df(s):
    d = pd.DataFrame(s["snap"])
    d["fecha"] = pd.to_datetime(d["fecha"])
    d["mes_sim"] = d["dia"] / float(SIM_DIAS_MES)
    return d

# ── Gráficos del simulador ───────────────────────────────────────────────────
_MESES = list(range(1, SIM_MESES_MAX + 1))

def chs_global(df):
    esc = alt.Scale(domain=SIM_SERIES, range=SIM_COL_SERIES)
    lin = alt.Chart(df).mark_line(point=True, strokeWidth=3).encode(
        x=alt.X("mes:O", title="Mes simulado", scale=alt.Scale(domain=_MESES), axis=alt.Axis(labelAngle=0)),
        y=alt.Y("progreso:Q", title="Cumplimiento global (%)", scale=alt.Scale(domain=[-30, 115])),
        color=alt.Color("serie:N", scale=esc, legend=alt.Legend(title=None, orient="bottom")),
        tooltip=[alt.Tooltip("mes:O", title="Mes"), alt.Tooltip("serie:N", title="Serie"),
                 alt.Tooltip("progreso:Q", title="Cumplimiento (%)", format=".1f")])
    etq = alt.Chart(df[df["serie"] == SIM_SERIES[0]]).mark_text(dy=-12, fontWeight="bold", color="#1F3864").encode(
        x=alt.X("mes:O", scale=alt.Scale(domain=_MESES)), y="progreso:Q",
        text=alt.Text("progreso:Q", format=".0f"))
    meta = alt.Chart(pd.DataFrame({"y": [100]})).mark_rule(color="#2E9E5B", strokeDash=[6, 4], size=2).encode(y="y:Q")
    meta_t = alt.Chart(pd.DataFrame({"y": [100], "t": ["Meta a 6 meses = 100%"]})).mark_text(
        align="left", dy=-8, color="#2E9E5B", fontWeight="bold").encode(y="y:Q", text="t:N", x=alt.value(4))
    cero = alt.Chart(pd.DataFrame({"y": [0], "t": ["Línea base (0% = sin mejora)"]})).mark_rule(color="#9AA5B1", strokeDash=[3, 3]).encode(y="y:Q")
    cero_t = alt.Chart(pd.DataFrame({"y": [0], "t": ["Línea base (0% = sin mejora)"]})).mark_text(
        align="left", dy=14, color="#7B8794", fontWeight="bold").encode(y="y:Q", text="t:N", x=alt.value(4))
    return (lin + etq + meta + meta_t + cero + cero_t).properties(height=300)

def chs_kpi(df, r):
    esc = alt.Scale(domain=SIM_SERIES, range=["#2E75B6", "#7B4FA3"])
    lin = alt.Chart(df).mark_line(point=True, strokeWidth=2.5).encode(
        x=alt.X("mes:O", title="Mes simulado", scale=alt.Scale(domain=_MESES), axis=alt.Axis(labelAngle=0)),
        y=alt.Y("valor:Q", title=r["unidad"]),
        color=alt.Color("serie:N", scale=esc, legend=alt.Legend(title=None, orient="bottom")),
        tooltip=[alt.Tooltip("mes:O", title="Mes"), alt.Tooltip("serie:N", title="Serie"),
                 alt.Tooltip("valor:Q", title="Valor", format=".1f")])
    dom = ["Línea base", "Meta 6 meses", "Meta 12 meses"]
    escr = alt.Scale(domain=dom, range=["#9AA5B1", "#F2B134", "#2E9E5B"])
    refs = pd.DataFrame({"y": [r["base"], r["meta6"], r["meta12"]], "Referencia": dom})
    reglas = alt.Chart(refs).mark_rule(strokeDash=[5, 4], size=2).encode(
        y="y:Q", color=alt.Color("Referencia:N", scale=escr, legend=None))
    etiq = alt.Chart(refs).mark_text(align="left", dy=-6, fontWeight="bold").encode(
        y="y:Q", x=alt.value(4), text="Referencia:N", color=alt.Color("Referencia:N", scale=escr, legend=None))
    return alt.layer(lin, reglas, etiq).resolve_scale(color="independent").properties(height=300)

def chs_adopcion(snap):
    d = snap.copy()
    d["pct"] = d["adopcion"] * 100
    area = alt.Chart(d).mark_area(opacity=0.2, color="#2E75B6").encode(
        x=alt.X("mes_sim:Q", title="Mes simulado", scale=alt.Scale(domain=[0, SIM_MESES_MAX]),
                axis=alt.Axis(values=list(range(0, SIM_MESES_MAX + 1)), format="d")),
        y=alt.Y("pct:Q", title="Adopción del sistema (%)", scale=alt.Scale(domain=[0, 100])))
    lin = alt.Chart(d).mark_line(color="#1F3864", size=2.5).encode(
        x="mes_sim:Q", y="pct:Q",
        tooltip=[alt.Tooltip("mes_sim:Q", title="Mes", format=".1f"), alt.Tooltip("pct:Q", title="Adopción (%)", format=".0f")])
    plan = alt.Chart(pd.DataFrame({"y": [100 * SIM_A12]})).mark_rule(color="#2E9E5B", strokeDash=[6, 4]).encode(y="y:Q")
    plan_t = alt.Chart(pd.DataFrame({"y": [100 * SIM_A12], "t": ["Adopción desde la cual el modelo llega a la meta a 12 meses (90%)"]})).mark_text(
        align="left", dy=-7, color="#2E9E5B", fontWeight="bold", fontSize=11).encode(y="y:Q", text="t:N", x=alt.value(4))
    return (area + lin + plan + plan_t).properties(height=230)

def chs_ocupacion(snap):
    d = snap.melt(id_vars=["fecha"], value_vars=["pct_container", "pct_boveda"], var_name="alm", value_name="pct")
    d["Almacén"] = d["alm"].map({"pct_container": "Container secundarios", "pct_boveda": "Bóveda primarios"})
    lin = alt.Chart(d).mark_line(size=2.5).encode(
        x=alt.X("fecha:T", title=None), y=alt.Y("pct:Q", title="% de la capacidad máxima", scale=alt.Scale(domain=[0, 115])),
        color=alt.Color("Almacén:N", scale=alt.Scale(domain=["Container secundarios", "Bóveda primarios"],
                                                      range=["#2E75B6", "#7B4FA3"]),
                        legend=alt.Legend(title=None, orient="bottom")),
        tooltip=[alt.Tooltip("fecha:T", title="Fecha"), alt.Tooltip("Almacén:N"), alt.Tooltip("pct:Q", title="% capacidad", format=".1f")])
    r90 = alt.Chart(pd.DataFrame({"y": [90]})).mark_rule(color="#F2B134", strokeDash=[5, 4], size=2).encode(y="y:Q")
    r100 = alt.Chart(pd.DataFrame({"y": [100]})).mark_rule(color="#D64545", strokeDash=[5, 4], size=2).encode(y="y:Q")
    t = alt.Chart(pd.DataFrame({"y": [90, 100], "t": ["Alerta 90%", "Bloqueo 100%"], "c": ["#B8860B", "#D64545"]})).mark_text(
        align="left", dy=-6, fontWeight="bold").encode(y="y:Q", text="t:N", x=alt.value(4), color=alt.Color("c:N", scale=None))
    return (lin + r90 + r100 + t).properties(height=260)

def chs_stock(snap):
    cols = list(SIM_TARGET.keys())
    d = snap.melt(id_vars=["fecha"], value_vars=cols, var_name="Explosivo", value_name="unidades")
    return alt.Chart(d).mark_line(size=2.2).encode(
        x=alt.X("fecha:T", title=None), y=alt.Y("unidades:Q", title="Unidades en stock (sacos/cajas/rollos)"),
        color=alt.Color("Explosivo:N", legend=alt.Legend(title=None, orient="bottom")),
        tooltip=[alt.Tooltip("fecha:T", title="Fecha"), "Explosivo:N", alt.Tooltip("unidades:Q", title="Unidades")]
    ).properties(height=260)

def chs_semanal(snap):
    d = snap.copy()
    d["semana"] = (d["dia"] - 1).clip(lower=0) // 7 + 1
    d = d[d["dia"] > 0].groupby("semana")[["desp", "ing"]].sum().reset_index()
    d = d.melt(id_vars="semana", value_vars=["desp", "ing"], var_name="t", value_name="n")
    d["Tipo"] = d["t"].map({"desp": "Despachos", "ing": "Ingresos de material"})
    return alt.Chart(d).mark_bar().encode(
        x=alt.X("semana:O", title="Semana simulada", axis=alt.Axis(labelAngle=0, labelOverlap=True)),
        xOffset="Tipo:N", y=alt.Y("n:Q", title="N° de operaciones", axis=alt.Axis(tickMinStep=1)),
        color=alt.Color("Tipo:N", scale=alt.Scale(domain=["Despachos", "Ingresos de material"], range=["#2E75B6", "#2E9E5B"]),
                        legend=alt.Legend(title=None, orient="bottom")),
        tooltip=[alt.Tooltip("semana:O", title="Semana"), "Tipo:N", alt.Tooltip("n:Q", title="Operaciones")]
    ).properties(height=260)

def chs_incidentes(snap, snap_ctrl):
    filas = []
    for etiqueta, d in zip(SIM_SERIES, (snap, snap_ctrl)):
        for _, r in d.iterrows():
            filas.append({"fecha": r["fecha"], "serie": etiqueta, "n": r["venc_desp_acum"]})
    d = pd.DataFrame(filas)
    return alt.Chart(d).mark_line(size=2.5, interpolate="step-after").encode(
        x=alt.X("fecha:T", title=None),
        y=alt.Y("n:Q", title="Despachos con material vencido (acumulado)", axis=alt.Axis(tickMinStep=1)),
        color=alt.Color("serie:N", scale=alt.Scale(domain=SIM_SERIES, range=SIM_COL_SERIES),
                        legend=alt.Legend(title=None, orient="bottom")),
        tooltip=[alt.Tooltip("fecha:T", title="Fecha"), "serie:N", alt.Tooltip("n:Q", title="Acumulado")]
    ).properties(height=240)

def chs_riesgos(snap):
    d = snap.melt(id_vars=["fecha"], value_vars=["venc_pres", "por_vencer", "stock_bajo"], var_name="c", value_name="n")
    etiquetas = {"venc_pres": "Lotes vencidos sin gestionar", "por_vencer": "Lotes por vencer (<30 días)",
                 "stock_bajo": "Explosivos bajo stock mínimo"}
    d["Condición"] = d["c"].map(etiquetas)
    return alt.Chart(d).mark_area(opacity=0.85).encode(
        x=alt.X("fecha:T", title=None), y=alt.Y("n:Q", title="N° de condiciones de riesgo", stack=True),
        color=alt.Color("Condición:N", scale=alt.Scale(domain=list(etiquetas.values()), range=["#D64545", "#F2B134", "#9AA5B1"]),
                        legend=alt.Legend(title=None, orient="bottom")),
        tooltip=[alt.Tooltip("fecha:T", title="Fecha"), "Condición:N", alt.Tooltip("n:Q", title="N°")]
    ).properties(height=250)

# ── Control y estado de la simulación ────────────────────────────────────────
def _sim_params_ui(nombre):
    p = dict(SIM_ESCENARIOS[nombre])
    p["nombre"] = nombre
    if nombre == "Personalizado":
        g = st.session_state.get
        p.update({"a_inf": g("sim_p_ainf", p["a_inf"]), "t_half": g("sim_p_thalf", p["t_half"]),
                  "k": g("sim_p_k", p["k"]), "desp_dia": g("sim_p_desp", p["desp_dia"]),
                  "ing_sem": g("sim_p_ing", p["ing_sem"]), "env_mes": g("sim_p_env", p["env_mes"]),
                  "p_demora_extra": g("sim_p_dem", p["p_demora_extra"]), "stock_mult": g("sim_p_stock", p["stock_mult"])})
    p["retrocesos"] = list(p.get("retrocesos", []))
    return p

def _sim_guardar(params, seed):
    s, c = sim_crear(params, seed)
    st.session_state["sim_s"] = s
    st.session_state["sim_c"] = c
    st.session_state["sim_params"] = params
    st.session_state["sim_seed"] = seed

def _cb_sim_crear():
    nombre = st.session_state.get("sim_esc_sel", "Adopción gradual (esperable)")
    _sim_guardar(_sim_params_ui(nombre), int(st.session_state.get("sim_semilla_in", 42)))

def _cb_sim_aleatorio():
    seed = random.randint(1, 99999)
    st.session_state["sim_semilla_in"] = seed
    _sim_guardar(sim_params_aleatorios(random.Random(seed), seed), seed)

def _cb_sim_reiniciar():
    _sim_guardar(st.session_state["sim_params"], st.session_state["sim_seed"])

def _cb_sim_avanzar(dias):
    sim_avanzar(st.session_state["sim_s"], st.session_state["sim_c"], dias)

def _sim_asegurar():
    if "sim_semilla_in" not in st.session_state:
        st.session_state["sim_semilla_in"] = 42
    if "sim_s" not in st.session_state:
        nombre = "Adopción gradual (esperable)"
        p = dict(SIM_ESCENARIOS[nombre])
        p["nombre"] = nombre
        _sim_guardar(p, 42)

def _sim_tabla_params(p):
    filas = [("Escenario", p["nombre"]), ("Adopción inicial", str(round(100 * p["a0"])) + "%"),
             ("Adopción final (techo)", str(round(100 * p["a_inf"])) + "%"),
             ("Mes de mayor ritmo de adopción", str(p["t_half"])), ("Rapidez de la curva", str(p["k"])),
             ("Despachos por día", str(p["desp_dia"])), ("Entregas de material por semana", str(p["ing_sem"])),
             ("Alertas ambientales por mes", str(p["env_mes"])),
             ("Demora extra en traslados", str(round(100 * p["p_demora_extra"])) + "%"),
             ("Stock objetivo (× normal)", str(p["stock_mult"])),
             ("Caídas de adopción (mes, duración, factor)", str(p["retrocesos"]) if p["retrocesos"] else "ninguna")]
    return pd.DataFrame(filas, columns=["Parámetro", "Valor"])

def _sim_veredicto(kdf, s, ctrl, mes):
    ms = next((x for x in s["kpi_mensual"] if x["mes"] == mes), None)
    mc = next((x for x in ctrl["kpi_mensual"] if x["mes"] == mes), None)
    if ms is None:
        return None, None
    filas, n_ok, n_tot = [], 0, 0
    for _, k in kdf.iterrows():
        meta = k["meta_6m"] if mes == 6 else k["meta_12m"]
        v = ms["valores"].get(k["id"])
        vc = mc["valores"].get(k["id"]) if mc else None
        ok = sim_cumple(k["unidad"], v, meta)
        req = sim_adopcion_requerida(k["id"], k["unidad"], meta)
        if ok is not None:
            n_tot += 1
            n_ok += 1 if ok else 0
        filas.append({"KPI": k["nombre"], "Unidad": k["unidad"],
                      "Meta": meta, "Simulado (con sistema)": None if v is None else round(v, 1),
                      "Cumple": "—" if ok is None else ("✅ Sí" if ok else "❌ No"),
                      "Sin sistema (control)": None if vc is None else round(vc, 1),
                      "Adopción requerida*": "inalcanzable" if req is None else str(round(100 * req)) + "%"})
    return pd.DataFrame(filas), (n_ok, n_tot, ms["adopcion"])

def mod_simulador():
    st.title("🎮 Simulador de Escenarios y Tiempo")
    if not (puede("kpis") or puede("todo")):
        st.warning("El simulador está disponible para el jefe de turno y el administrador.")
        return
    st.markdown("""<style>
    .pbi-card{background:#fff;border-radius:10px;padding:14px 16px;box-shadow:0 2px 8px rgba(0,0,0,.08);border-top:5px solid #1F3864;}
    .pbi-val{font-size:2.1em;font-weight:700;line-height:1.1;}
    .pbi-lbl{font-size:.8em;color:#666;margin-top:2px;}
    </style>""", unsafe_allow_html=True)
    st.info("**Cómo funciona:** el simulador crea una faena virtual (inventario, despachos, traslados, vencimientos y "
            "alertas ambientales) y la hace operar día a día. Los KPIs se **calculan a partir de esos eventos**. "
            "Corre aparte de los datos operativos de la app, así que no los modifica. "
            "⚠️ Es un modelo **what-if**: muestra qué pasaría **si** el sistema se adopta con el ritmo del escenario, "
            "bajo supuestos explícitos (ver 📘 *Supuestos del modelo*). No es evidencia medida en faena.")
    _sim_asegurar()
    kdf = get_kpis()

    # ── 1 · Escenario ───────────────────────────────────────────────────────
    with st.container(border=True):
        st.markdown("**1 · Escenario**")
        c1, c2, c3, c4 = st.columns([2.4, 1, 1.4, 1.4])
        nombre = c1.selectbox("Escenario", list(SIM_ESCENARIOS.keys()), key="sim_esc_sel")
        c2.number_input("Semilla", min_value=0, max_value=999999, step=1, key="sim_semilla_in",
                        help="Misma semilla + mismo escenario = misma simulación (reproducible).")
        c3.markdown("<div style='height:1.7em'></div>", unsafe_allow_html=True)
        c3.button("🧪 Crear simulación", use_container_width=True, on_click=_cb_sim_crear)
        c4.markdown("<div style='height:1.7em'></div>", unsafe_allow_html=True)
        c4.button("🎲 Escenario aleatorio", use_container_width=True, on_click=_cb_sim_aleatorio)
        st.caption(SIM_ESCENARIOS[nombre]["desc"] + " (Pulsa «Crear simulación» para aplicar el escenario elegido.)")
        if nombre == "Personalizado":
            b = SIM_ESCENARIOS["Personalizado"]
            k1, k2, k3, k4 = st.columns(4)
            k1.slider("Adopción final", 0.0, 1.0, float(b["a_inf"]), 0.01, key="sim_p_ainf")
            k2.slider("Mes de mayor ritmo", 1.0, 10.0, float(b["t_half"]), 0.5, key="sim_p_thalf")
            k3.slider("Rapidez de la curva", 0.3, 1.5, float(b["k"]), 0.05, key="sim_p_k")
            k4.slider("Stock objetivo (× normal)", 0.6, 2.0, float(b["stock_mult"]), 0.1, key="sim_p_stock")
            k5, k6, k7, k8 = st.columns(4)
            k5.slider("Despachos por día", 0.3, 3.0, float(b["desp_dia"]), 0.1, key="sim_p_desp")
            k6.slider("Entregas por semana", 0.5, 5.0, float(b["ing_sem"]), 0.1, key="sim_p_ing")
            k7.slider("Alertas ambientales/mes", 0, 30, int(b["env_mes"]), 1, key="sim_p_env")
            k8.slider("Demora extra en traslados", 0.0, 0.3, float(b["p_demora_extra"]), 0.01, key="sim_p_dem")

    s, ctrl, params = st.session_state["sim_s"], st.session_state["sim_c"], st.session_state["sim_params"]
    terminado = s["dia"] >= SIM_DIAS_MAX
    simh_auto_registrar(s, ctrl)          # registra sola la simulación al completar los 12 meses

    # ── 2 · Tiempo ──────────────────────────────────────────────────────────
    with st.container(border=True):
        st.markdown("**2 · Tiempo simulado**")
        t1, t2, t3, t4, t5, t6, t7 = st.columns(7)
        t1.button("▶️ +1 día", use_container_width=True, disabled=terminado, on_click=_cb_sim_avanzar, args=(1,))
        t2.button("⏩ +1 semana", use_container_width=True, disabled=terminado, on_click=_cb_sim_avanzar, args=(7,))
        t3.button("⏭️ +1 mes", use_container_width=True, disabled=terminado, on_click=_cb_sim_avanzar, args=(SIM_DIAS_MES,))
        t4.button("📅 +3 meses", use_container_width=True, disabled=terminado, on_click=_cb_sim_avanzar, args=(3 * SIM_DIAS_MES,))
        t5.button("🏁 Hasta el mes 12", use_container_width=True, disabled=terminado, on_click=_cb_sim_avanzar, args=(SIM_DIAS_MAX,))
        anim = t6.button("🎬 Reproducir", use_container_width=True, disabled=terminado,
                         help="Avanza mes a mes mostrando cómo evoluciona el cumplimiento.")
        t7.button("↺ Reiniciar", use_container_width=True, on_click=_cb_sim_reiniciar,
                  help="Vuelve al día 0 con el mismo escenario y la misma semilla.")
        anim_ph = st.empty()
        st.divider()
        h1, h2, h3, h4 = st.columns([2, 1.4, 2, 1.4])
        h1.text_input("Etiqueta para el historial (opcional)", key="simh_etq", max_chars=40,
                      placeholder="p. ej. Serie A", help="Sirve para agrupar simulaciones por serie y filtrarlas al calcular promedios.")
        h2.markdown("<div style='height:1.7em'></div>", unsafe_allow_html=True)
        h2.button("💾 Guardar en historial", use_container_width=True, on_click=_cb_simh_guardar,
                  disabled=(len(s["kpi_mensual"]) < 1),
                  help="Guarda el resultado hasta el último mes cerrado. Necesita al menos 1 mes cerrado.")
        h3.markdown("<div style='height:1.7em'></div>", unsafe_allow_html=True)
        h3.checkbox("Registro automático al mes 12", value=True, key="simh_auto")
        h4.markdown("<div style='height:1.7em'></div>", unsafe_allow_html=True)
        h4.caption("📚 En historial: **" + (s["_hist_id"] if s.get("_hist_id") else "no") + "**")
        _fl = st.session_state.pop("simh_flash", None)
        if _fl:
            st.success(_fl)

    if anim and not terminado:
        while s["dia"] < SIM_DIAS_MAX:
            sim_avanzar(s, ctrl, SIM_DIAS_MES)
            with anim_ph.container():
                st.markdown("🎬 **Reproduciendo… mes " + str(s["dia"] // SIM_DIAS_MES) + " de " + str(SIM_MESES_MAX) + "**")
                dfg = sim_global_df(s, ctrl, kdf)
                if not dfg.empty:
                    st.altair_chart(chs_global(dfg), use_container_width=True)
            time.sleep(0.3)
        st.rerun()

    # ── Estado ──────────────────────────────────────────────────────────────
    a_hoy = sim_adopcion(params, s["dia"])
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("📅 Fecha simulada", str(_sim_hoy(s)))
    m2.metric("Día / mes", "día " + str(s["dia"]) + " · mes " + str(len(s["kpi_mensual"])) + " cerrado" +
              ("s" if len(s["kpi_mensual"]) != 1 else "") + " de " + str(SIM_MESES_MAX))
    m3.metric("Escenario", params["nombre"])
    m4.metric("Adopción del sistema hoy", str(round(100 * a_hoy)) + "%")
    st.progress(min(1.0, s["dia"] / float(SIM_DIAS_MAX)), text="Avance de la simulación: " +
                str(round(100.0 * s["dia"] / SIM_DIAS_MAX)) + "% del horizonte de 12 meses")
    if terminado:
        st.success("🏁 Simulación completa (12 meses). Revisa la pestaña «Veredicto». Usa «Reiniciar» o crea otro escenario.")

    with st.expander("Ver los parámetros de este escenario"):
        st.dataframe(_sim_tabla_params(params), use_container_width=True, hide_index=True)

    tabs = st.tabs(["📊 KPIs", "📦 Inventario y capacidad", "🚛 Operación", "⚠️ Riesgos", "📜 Bitácora", "🏁 Veredicto"])
    snap, snap_c = sim_snap_df(s), sim_snap_df(ctrl)

    with tabs[0]:
        st.markdown("**Nivel de adopción del sistema en el tiempo** (es el motor del escenario: a mayor adopción, mejores KPIs)")
        st.altair_chart(chs_adopcion(snap), use_container_width=True)
        if not s["kpi_mensual"]:
            st.info("Aún no hay ningún mes cerrado. Usa **⏭️ +1 mes** (o 🏁 / 🎬) para que se calculen los primeros KPIs.")
        else:
            tabla = sim_tabla(kdf, s)
            if tabla.empty:
                st.info("Aún no hay datos suficientes para calcular los KPIs.")
            else:
                glob = float(tabla["progreso"].clip(upper=100).mean())
                cc = st.columns(5)
                for col, (val, et, colr) in zip(cc, [
                        (len(tabla), "KPIs con datos", "#1F3864"),
                        (len(tabla[tabla["estado"] == "Logrado"]), "🟢 Logrados", "#2E9E5B"),
                        (len(tabla[tabla["estado"] == "En progreso"]), "🟡 En progreso", "#F2B134"),
                        (len(tabla[tabla["estado"] == "Rezagado"]), "🔴 Rezagados", "#D64545"),
                        (str(round(glob)) + "%", "Cumplimiento global", "#2E75B6")]):
                    col.markdown('<div class="pbi-card" style="border-top-color:' + colr + '"><div class="pbi-val" style="color:' +
                                 colr + '">' + str(val) + '</div><div class="pbi-lbl">' + et + '</div></div>', unsafe_allow_html=True)
                st.caption("Estado = avance del último mes con datos hacia la meta a 6 meses (100% = meta alcanzada). "
                           "El mes en curso aún no cuenta: los KPIs se calculan al cerrar cada mes de 30 días.")
                st.markdown("**Cumplimiento global por mes: con sistema vs sin sistema**")
                st.caption("0% = igual que la línea base; 100% = metas a 6 meses alcanzadas. La línea «sin sistema» debe oscilar "
                           "alrededor de 0% (puede bajar de 0% algunos meses por simple variación del azar).")
                dfg = sim_global_df(s, ctrl, kdf)
                if not dfg.empty:
                    st.altair_chart(chs_global(dfg), use_container_width=True)
                st.divider()
                st.subheader("🧩 Todos los KPIs")
                hist = sim_hist_df(s)
                for i in range(0, len(tabla), 3):
                    cols = st.columns(3)
                    for col, (_, r) in zip(cols, tabla.iloc[i:i + 3].iterrows()):
                        with col:
                            with st.container(border=True):
                                _tarjeta_kpi(r, hist)
                st.divider()
                st.subheader("🔎 Detalle de un KPI: con sistema vs sin sistema")
                kpi_sel = st.selectbox("KPI", tabla["kpi"].tolist(), key="sim_kpi_det")
                r = tabla[tabla["kpi"] == kpi_sel].iloc[0]
                st.caption(r["descripcion"] + " · " + ("Menos es mejor." if r["unidad"] in MENOR_ES_MEJOR else "Más es mejor."))
                st.altair_chart(chs_kpi(sim_kpi_series_df(r["id"], s, ctrl), r), use_container_width=True)

    with tabs[1]:
        st.markdown("**Ocupación de los almacenes** (% de la capacidad máxima; al llegar a 100% se bloquean los ingresos)")
        st.altair_chart(chs_ocupacion(snap), use_container_width=True)
        st.markdown("**Stock por explosivo en el tiempo**")
        st.altair_chart(chs_stock(snap), use_container_width=True)
        lotes_act = [l for l in s["lotes"] if l["cant"] > 0 and l["estado"] != "destruido"]
        st.markdown("**Lotes en el polvorín hoy** (" + str(len(lotes_act)) + ")")
        if lotes_act:
            tl = pd.DataFrame([{"Lote": l["id"], "Explosivo": l["exp"], "Cantidad": l["cant"],
                                "Ingreso": str(l["ingreso"]), "Vence": str(l["venc"]),
                                "Días para vencer": (l["venc"] - _sim_hoy(s)).days, "Estado": l["estado"]} for l in lotes_act])
            st.dataframe(tl.sort_values("Ingreso"), use_container_width=True, hide_index=True)

    with tabs[2]:
        if s["dia"] == 0:
            st.info("Avanza el tiempo para ver la operación.")
        else:
            st.markdown("**Despachos e ingresos de material por semana**")
            st.altair_chart(chs_semanal(snap), use_container_width=True)
            tot = s["tot"]
            n_desp, n_viaj = int(snap["desp"].sum()), int(snap["viajes"].sum())
            o1, o2, o3, o4 = st.columns(4)
            o1.metric("Despachos realizados", n_desp)
            o2.metric("Traslados con demora", int(snap["viajes_tarde"].sum()))
            o3.metric("Quiebres de stock", tot["quiebres"])
            o4.metric("Ingresos bloqueados por capacidad", tot["ing_bloq"])
            st.caption("Quiebre de stock = se pidió un explosivo que no había vigente. Ingreso bloqueado = la entrega "
                       "habría superado la capacidad máxima del almacén.")

    with tabs[3]:
        if s["dia"] == 0:
            st.info("Avanza el tiempo para ver los riesgos.")
        else:
            st.markdown("**Condiciones de riesgo presentes cada día** (lo que el sistema marcaría como alerta)")
            st.altair_chart(chs_riesgos(snap), use_container_width=True)
            st.markdown("**Despachos con material vencido (acumulado): con sistema vs sin sistema**")
            st.altair_chart(chs_incidentes(snap, snap_c), use_container_width=True)
            comp = pd.DataFrame([
                {"Indicador": "Despachos con material vencido", "Con sistema": s["tot"]["desp_venc"], "Sin sistema": ctrl["tot"]["desp_venc"]},
                {"Indicador": "Vencimientos no detectados a tiempo", "Con sistema": s["tot"]["exp_no_det"], "Sin sistema": ctrl["tot"]["exp_no_det"]},
                {"Indicador": "Discrepancias de registro", "Con sistema": s["tot"]["err"], "Sin sistema": ctrl["tot"]["err"]},
                {"Indicador": "Alertas ambientales sin respuesta", "Con sistema": s["tot"]["env_sin"], "Sin sistema": ctrl["tot"]["env_sin"]},
                {"Indicador": "Quiebres de stock", "Con sistema": s["tot"]["quiebres"], "Sin sistema": ctrl["tot"]["quiebres"]}])
            st.dataframe(comp, use_container_width=True, hide_index=True)

    with tabs[4]:
        ev = pd.DataFrame(s["eventos"])
        if ev.empty:
            st.info("Sin eventos todavía.")
        else:
            tipos = sorted(ev["tipo"].unique().tolist())
            sel = st.multiselect("Filtrar por tipo de evento", tipos, default=tipos, key="sim_ev_tipos")
            ev = ev[ev["tipo"].isin(sel)].sort_values("dia", ascending=False).head(300)
            st.dataframe(ev[["fecha", "tipo", "detalle"]], use_container_width=True, hide_index=True)
            st.caption("Se muestran los 300 eventos más recientes.")

    with tabs[5]:
        st.markdown("**¿Se cumplen las metas?** Se evalúa cada meta contra el KPI simulado del mes correspondiente.")
        hay = False
        for mes, et in ((6, "Meta a 6 meses"), (12, "Meta a 12 meses")):
            tabla_v, resumen = _sim_veredicto(kdf, s, ctrl, mes)
            if tabla_v is None:
                st.info("**" + et + ":** aún no se llega al mes " + str(mes) + ". Avanza el tiempo para evaluarla.")
                continue
            hay = True
            n_ok, n_tot, a_m = resumen
            st.subheader("🎯 " + et + " (mes " + str(mes) + ")")
            v1, v2, v3 = st.columns(3)
            v1.metric("Metas cumplidas", str(n_ok) + " de " + str(n_tot))
            v2.metric("Adopción alcanzada en ese mes", str(round(100 * a_m)) + "%")
            v3.metric("Resultado", "✅ Cumple todo" if n_ok == n_tot else ("🟡 Cumple parcialmente" if n_ok >= n_tot / 2.0 else "🔴 No cumple"))
            st.dataframe(tabla_v, use_container_width=True, hide_index=True)
        if hay:
            st.caption("*Adopción requerida: nivel de adopción desde el cual el modelo, en promedio, cumple esa meta "
                       "(con ~38 operaciones y ~6 alertas ambientales al mes). Si la adopción alcanzada es menor, es esperable que no se cumpla. "
                       "Un valor cercano a la meta puede cumplir o no según el azar del mes.")

def mod_simulador_supuestos():
    st.title("📘 Supuestos del modelo de simulación")
    st.warning("**Lectura obligatoria antes de citar resultados.** Las relaciones entre adopción y KPIs de abajo son "
               "**supuestos** del modelo, calibrados para que (a) con 0% de adopción los KPIs sean iguales a su línea base y "
               "(b) con adopción casi total se alcancen las metas. Por eso el simulador sirve para **explorar** cuánta adopción y cuánto "
               "tiempo se necesitan, y cómo lo afectan la demanda, la rotación de personal o el clima. **No demuestra** que el sistema "
               "produzca esas mejoras: eso solo puede verificarse midiendo en una faena real.")
    st.subheader("Cómo se construye cada KPI")
    st.markdown("Cada mes de 30 días se cierra y el KPI se calcula con los eventos ocurridos. La **adopción** `a` (0 a 1) "
                "sigue una curva logística según el escenario; el **efecto efectivo** es `x = min(1, a / 0.90)`.")
    filas = [
        ("KPI-001", "% lotes con vencimiento registrado", "Cada ingreso registra el vencimiento con prob. 0,60 + 0,40·x"),
        ("KPI-002", "% despachos con orden de retiro", "Cada despacho tiene orden con prob. 0,40 + 0,60·x"),
        ("KPI-003", "Tiempo de inventario físico (min)", "(45 − 37,8·x) × factor por N° de lotes + ruido"),
        ("KPI-004", "Discrepancias por auditoría (N°/mes)", "Cada operación tiene error con prob. (8/38)·(1 − x): crece con el volumen de operaciones"),
        ("KPI-005", "% lotes vencidos detectados a tiempo", "Cada lote que vence se detecta con prob. 0,30 + 0,70·x (ventana móvil de 3 meses)"),
        ("KPI-006", "Tiempo de reporte a la AF (min)", "3 + 117·(1 − x)²  + ruido (baja de golpe cuando el flujo está operativo)"),
        ("KPI-007", "% cumplimiento libro de control", "Cada movimiento queda bien registrado con prob. 0,50 + 0,50·x"),
        ("KPI-008", "% viajes en tiempo", "Cada traslado llega a tiempo con prob. 0,55 + 0,40·x − demora extra del escenario"),
        ("KPI-009", "Tiempo promedio de despacho (min)", "Promedio de tiempos ~ N(25 − 18,4·x ; 3)"),
        ("KPI-010", "Alertas ambientales sin respuesta (N°/mes)", "Cada alerta se responde con prob. 1/6 + (5/6)·x; el N° de alertas depende del escenario"),
    ]
    st.dataframe(pd.DataFrame(filas, columns=["KPI", "Indicador", "Relación asumida con la adopción"]),
                 use_container_width=True, hide_index=True)
    st.subheader("Adopción mínima que necesita el modelo para cumplir cada meta")
    kdf = get_kpis()
    req = []
    for _, k in kdf.iterrows():
        r6 = sim_adopcion_requerida(k["id"], k["unidad"], k["meta_6m"])
        r12 = sim_adopcion_requerida(k["id"], k["unidad"], k["meta_12m"])
        req.append({"KPI": k["nombre"], "Meta 6 meses": k["meta_6m"], "Adopción requerida (6m)": "inalcanzable" if r6 is None else str(round(100 * r6)) + "%",
                    "Meta 12 meses": k["meta_12m"], "Adopción requerida (12m)": "inalcanzable" if r12 is None else str(round(100 * r12)) + "%"})
    st.dataframe(pd.DataFrame(req), use_container_width=True, hide_index=True)
    st.caption("Valores esperados del modelo con ~38 operaciones y ~6 alertas ambientales por mes. "
               "Esta tabla es una consecuencia de los supuestos de arriba, no un resultado empírico.")
    st.subheader("Qué se simula")
    st.markdown("- **Inventario:** 4 explosivos con lotes, vencimientos y reposición automática; capacidad máxima 3.500 kg (container) y 400 kg (bóveda), con bloqueo de ingresos al llegar al 100%.\n"
                "- **Despachos:** llegan al azar (Poisson). Con el sistema se impone FIFO y se bloquea material vencido; sin él se toma cualquier lote, incluso uno vencido.\n"
                "- **Traslados y alertas ambientales:** con probabilidad de demora y de respuesta que dependen de la adopción.\n"
                "- **Escenario «sin sistema (control)»:** corre en paralelo con la misma demanda y semilla, para comparar *con* vs *sin* sistema.\n"
                "- **Azar:** la misma semilla reproduce exactamente la misma simulación.")
    st.subheader("Escenarios disponibles")
    st.dataframe(pd.DataFrame([{"Escenario": k, "Qué representa": v["desc"]} for k, v in SIM_ESCENARIOS.items()]),
                 use_container_width=True, hide_index=True)


# ══════════════════════════════════════════════════════════════════
# PARTE 3 — HISTORIAL DE SIMULACIONES (registro, promedios, descarga y borrado)
# ══════════════════════════════════════════════════════════════════
import statistics as _stats

SIMH_TOT = [("desp_venc", "Despachos con material vencido"),
            ("exp_no_det", "Vencimientos no detectados a tiempo"),
            ("err", "Discrepancias de registro"),
            ("env_sin", "Alertas ambientales sin respuesta"),
            ("quiebres", "Quiebres de stock"),
            ("ing_bloq", "Ingresos bloqueados por capacidad")]
SIMH_TODAS = "TODAS las simulaciones"

def simh_grupo(nombre):
    """Los escenarios aleatorios (Aleatorio #123) se agrupan en uno solo para poder promediarlos."""
    return "Aleatorio (varios)" if str(nombre).startswith("Aleatorio #") else str(nombre)

def simh_huella(params, seed):
    """Identifica una simulación por escenario + parámetros + semilla (la etiqueta no cuenta)."""
    p = {k: v for k, v in params.items() if k != "desc"}
    txt = json.dumps([p, int(seed)], sort_keys=True, default=str)
    return hashlib.sha1(txt.encode()).hexdigest()[:16]

def _num(v):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return None if v != v else v

def simh_resumen(s, ctrl, params, seed, kdf):
    """Resume la simulación en curso (hasta el último mes cerrado) en un diccionario listo para guardar."""
    meses = len(s["kpi_mensual"])
    det = {"kpi": {}, "kpi_ctrl": {}, "adop": {}, "prog": {}, "prog_ctrl": {}}
    for clave, eng in (("kpi", s), ("kpi_ctrl", ctrl)):
        for m in eng["kpi_mensual"]:
            for kid, v in m["valores"].items():
                if _num(v) is not None:
                    det[clave].setdefault(kid, {})[str(m["mes"])] = round(float(v), 3)
    for m in s["kpi_mensual"]:
        det["adop"][str(m["mes"])] = round(float(m["adopcion"]), 4)
    dfg = sim_global_df(s, ctrl, kdf)
    for _, r in dfg.iterrows():
        det["prog" if r["serie"] == SIM_SERIES[0] else "prog_ctrl"][str(int(r["mes"]))] = float(r["progreso"])
    det["tot"] = {k: int(v) for k, v in s["tot"].items()}
    det["tot_ctrl"] = {k: int(v) for k, v in ctrl["tot"].items()}
    det["n_ops"] = int(sum(m["ops"] for m in s["kpi_mensual"]))
    det["n_desp"] = int(sum(m["desp"] for m in s["kpi_mensual"]))
    det["n_ing"] = int(sum(m["ing"] for m in s["kpi_mensual"]))
    metas = {}
    for mes in (6, 12):
        _, r = _sim_veredicto(kdf, s, ctrl, mes)
        metas[mes] = (r[0], r[1]) if r else (None, None)
    pg = det["prog"].get(str(meses))
    pgc = det["prog_ctrl"].get(str(meses))
    return {"meses": meses, "adop": det["adop"].get(str(meses)), "metas": metas, "pg": pg, "pgc": pgc, "det": det}

def simh_registrar(s, ctrl, params, seed, etiqueta="", usuario=""):
    """Guarda (o actualiza si ya existía la misma simulación) en el historial.
    Devuelve (estado, id) con estado: 'nueva' | 'actualizada' | 'ya_estaba' | 'sin_cambio' | 'vacia'."""
    if len(s["kpi_mensual"]) < 1:
        return "vacia", None
    kdf = get_kpis()
    r = simh_resumen(s, ctrl, params, seed, kdf)
    hu = simh_huella(params, seed)
    ahora = datetime.now().strftime("%Y-%m-%d %H:%M")
    pj = json.dumps({k: v for k, v in params.items() if k != "desc"}, default=str, ensure_ascii=False)
    dj = json.dumps(r["det"], ensure_ascii=False)
    conn = get_conn()
    try:
        fila = conn.execute("SELECT id, meses, etiqueta FROM sim_historial WHERE huella=?", (hu,)).fetchone()
        if fila:
            if r["meses"] < (fila[1] or 0):
                return "sin_cambio", fila[0]
            et = (etiqueta or "").strip() or (fila[2] or "")
            conn.execute("""UPDATE sim_historial SET etiqueta=?, meses=?, adopcion_final=?, metas6_ok=?, metas6_tot=?,
                            metas12_ok=?, metas12_tot=?, prog_global=?, prog_global_ctrl=?, detalle_json=?,
                            fecha_registro=?, registrado_por=? WHERE id=?""",
                         (et, r["meses"], r["adop"], r["metas"][6][0], r["metas"][6][1], r["metas"][12][0],
                          r["metas"][12][1], r["pg"], r["pgc"], dj, ahora, usuario, fila[0]))
            conn.commit()
            return ("ya_estaba" if r["meses"] == (fila[1] or 0) else "actualizada"), fila[0]
        nid = "SIM-" + uuid.uuid4().hex[:6].upper()
        conn.execute("INSERT INTO sim_historial VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     (nid, hu, (etiqueta or "").strip(), params["nombre"], int(seed), r["meses"], r["adop"],
                      r["metas"][6][0], r["metas"][6][1], r["metas"][12][0], r["metas"][12][1], r["pg"], r["pgc"],
                      pj, dj, ahora, usuario))
        conn.commit()
        return "nueva", nid
    finally:
        conn.close()

def simh_cargar():
    return get_df("SELECT * FROM sim_historial ORDER BY fecha_registro DESC, id")

def simh_borrar(ids=None, todo=False):
    conn = get_conn()
    try:
        if todo:
            n = conn.execute("SELECT COUNT(*) FROM sim_historial").fetchone()[0]
            conn.execute("DELETE FROM sim_historial")
        else:
            ids = list(ids or [])
            if not ids:
                return 0
            n = 0
            for i in ids:
                n += conn.execute("DELETE FROM sim_historial WHERE id=?", (i,)).rowcount
        conn.commit()
        return n
    finally:
        conn.close()

def simh_etiquetar(sim_id, etiqueta):
    conn = get_conn()
    conn.execute("UPDATE sim_historial SET etiqueta=? WHERE id=?", ((etiqueta or "").strip(), sim_id))
    conn.commit()
    conn.close()

def _msg_registro(est, sid):
    return {"nueva": "📚 Simulación registrada en el historial (" + str(sid) + ").",
            "actualizada": "📚 La simulación ya estaba en el historial y se actualizó con más meses (" + str(sid) + ").",
            "ya_estaba": "📚 Esta simulación ya estaba registrada (" + str(sid) + "): misma semilla y mismos parámetros, no se duplicó.",
            "sin_cambio": "📚 En el historial ya hay una versión más avanzada de esta simulación (" + str(sid) + "). No se cambió.",
            "vacia": "Aún no hay ningún mes cerrado: avanza el tiempo antes de guardar."}[est]

def _cb_simh_guardar():
    s, c = st.session_state["sim_s"], st.session_state["sim_c"]
    est, sid = simh_registrar(s, c, st.session_state["sim_params"], st.session_state["sim_seed"],
                              st.session_state.get("simh_etq", ""), st.session_state.get("nombre", ""))
    if sid:
        s["_reg_meses"] = len(s["kpi_mensual"])
        s["_hist_id"] = sid
    st.session_state["simh_flash"] = _msg_registro(est, sid)

def simh_auto_registrar(s, c):
    """Registra automáticamente la simulación al completarse el mes 12 (una sola vez por simulación)."""
    if s["dia"] >= SIM_DIAS_MAX and s.get("_reg_meses", 0) < SIM_MESES_MAX and st.session_state.get("simh_auto", True):
        est, sid = simh_registrar(s, c, st.session_state["sim_params"], st.session_state["sim_seed"],
                                  st.session_state.get("simh_etq", ""), st.session_state.get("nombre", ""))
        s["_reg_meses"] = len(s["kpi_mensual"])
        s["_hist_id"] = sid
        st.session_state["simh_flash"] = "Registro automático al completar los 12 meses. " + _msg_registro(est, sid)

# ── Tablas de registro y de promedios ────────────────────────────────────────
def _dets(df):
    out = []
    for r in df.itertuples():
        try:
            det = json.loads(r.detalle_json)
        except Exception:
            det = {}
        out.append({"r": r, "grupo": simh_grupo(r.escenario), "det": det})
    return out

def simh_tabla_registro(df):
    cols = ["ID", "Fecha de registro", "Etiqueta", "Escenario", "Semilla", "Meses simulados", "Adopción final (%)",
            "Metas cumplidas mes 6 (de 10)", "Metas cumplidas mes 12 (de 10)",
            "Cumplimiento global con sistema (%)", "Cumplimiento global sin sistema (%)"]
    for _, et in SIMH_TOT:
        cols += [et + " (con sistema)", et + " (sin sistema)"]
    cols += ["Operaciones registradas"]
    filas = []
    for x in _dets(df):
        r, d = x["r"], x["det"]
        f = {"ID": r.id, "Fecha de registro": r.fecha_registro, "Etiqueta": r.etiqueta or "", "Escenario": r.escenario,
             "Semilla": int(r.semilla), "Meses simulados": int(r.meses),
             "Adopción final (%)": None if _num(r.adopcion_final) is None else round(100 * float(r.adopcion_final), 1),
             "Metas cumplidas mes 6 (de 10)": None if _num(r.metas6_ok) is None else int(r.metas6_ok),
             "Metas cumplidas mes 12 (de 10)": None if _num(r.metas12_ok) is None else int(r.metas12_ok),
             "Cumplimiento global con sistema (%)": None if _num(r.prog_global) is None else round(float(r.prog_global), 1),
             "Cumplimiento global sin sistema (%)": None if _num(r.prog_global_ctrl) is None else round(float(r.prog_global_ctrl), 1),
             "Operaciones registradas": d.get("n_ops")}
        for k, et in SIMH_TOT:
            f[et + " (con sistema)"] = d.get("tot", {}).get(k)
            f[et + " (sin sistema)"] = d.get("tot_ctrl", {}).get(k)
        filas.append(f)
    return pd.DataFrame(filas, columns=cols)

def _prom(vals, dec=1):
    v = [float(x) for x in vals if _num(x) is not None]
    return round(sum(v) / len(v), dec) if v else None

def _desv(vals, dec=2):
    v = [float(x) for x in vals if _num(x) is not None]
    return round(_stats.stdev(v), dec) if len(v) >= 2 else None

def simh_promedios(df, kdf):
    """Calcula los promedios sobre las simulaciones recibidas. Devuelve dict de DataFrames."""
    regs = _dets(df)
    grupos = sorted({x["grupo"] for x in regs})
    conjuntos = [(SIMH_TODAS, regs)] + [(g, [x for x in regs if x["grupo"] == g]) for g in grupos]

    # 1 · Resumen por escenario
    filas = []
    for nombre, c in conjuntos:
        f = {"Escenario": nombre, "N° de simulaciones": len(c),
             "N° completas (12 meses)": sum(1 for x in c if int(x["r"].meses) >= SIM_MESES_MAX),
             "Adopción final promedio (%)": _prom([None if _num(x["r"].adopcion_final) is None else 100 * x["r"].adopcion_final for x in c]),
             "Metas cumplidas a 6 meses (promedio de 10)": _prom([x["r"].metas6_ok for x in c]),
             "Metas cumplidas a 12 meses (promedio de 10)": _prom([x["r"].metas12_ok for x in c]),
             "Cumplimiento global con sistema (%)": _prom([x["r"].prog_global for x in c]),
             "Cumplimiento global sin sistema (%)": _prom([x["r"].prog_global_ctrl for x in c])}
        a, b = f["Cumplimiento global con sistema (%)"], f["Cumplimiento global sin sistema (%)"]
        f["Diferencia (puntos %)"] = None if a is None or b is None else round(a - b, 1)
        for k, et in SIMH_TOT:
            f[et + " (con sistema)"] = _prom([x["det"].get("tot", {}).get(k) for x in c])
            f[et + " (sin sistema)"] = _prom([x["det"].get("tot_ctrl", {}).get(k) for x in c])
        filas.append(f)
    resumen = pd.DataFrame(filas)

    # 2 · KPIs promedio (mes 6 y mes 12)
    filas = []
    for nombre, c in conjuntos:
        for _, k in kdf.iterrows():
            kid = k["id"]
            f = {"Escenario": nombre, "KPI": kid, "Nombre": k["nombre"], "Unidad": k["unidad"],
                 "Línea base": float(k["valor_base"]), "Meta 6 meses": float(k["meta_6m"]),
                 "Meta 12 meses": float(k["meta_12m"])}
            for mes, meta, et in ((6, k["meta_6m"], "mes 6"), (12, k["meta_12m"], "mes 12")):
                con = [x["det"].get("kpi", {}).get(kid, {}).get(str(mes)) for x in c]
                sin = [x["det"].get("kpi_ctrl", {}).get(kid, {}).get(str(mes)) for x in c]
                con = [v for v in con if _num(v) is not None]
                sin = [v for v in sin if _num(v) is not None]
                f["N (" + et + ")"] = len(con)
                f["Promedio " + et + " con sistema"] = _prom(con, 2)
                f["Desv. estándar " + et] = _desv(con)
                f["Promedio " + et + " sin sistema"] = _prom(sin, 2)
                f["% de simulaciones que cumplen meta " + str(mes) + "m"] = (
                    round(100.0 * sum(1 for v in con if sim_cumple(k["unidad"], v, meta)) / len(con), 1) if con else None)
            filas.append(f)
    kpis = pd.DataFrame(filas)

    # 3 · Evolución mensual
    filas = []
    for nombre, c in conjuntos:
        for mes in range(1, SIM_MESES_MAX + 1):
            pc = [x["det"].get("prog", {}).get(str(mes)) for x in c]
            ps = [x["det"].get("prog_ctrl", {}).get(str(mes)) for x in c]
            ad = [None if x["det"].get("adop", {}).get(str(mes)) is None else 100 * x["det"]["adop"][str(mes)] for x in c]
            n = sum(1 for v in pc if _num(v) is not None)
            if n == 0:
                continue
            filas.append({"Escenario": nombre, "Mes": mes, "N": n, "Adopción promedio (%)": _prom(ad),
                          "Cumplimiento global con sistema (%)": _prom(pc), "Cumplimiento global sin sistema (%)": _prom(ps)})
    mensual = pd.DataFrame(filas, columns=["Escenario", "Mes", "N", "Adopción promedio (%)",
                                           "Cumplimiento global con sistema (%)", "Cumplimiento global sin sistema (%)"])
    return {"resumen": resumen, "kpis": kpis, "mensual": mensual}

# ── Excel / CSV ──────────────────────────────────────────────────────────────
def simh_hoja(nombre, df, titulo, sub=""):
    """Como hoja_df, pero sin colorear texto por palabras clave (los nombres de escenario no son alertas)."""
    filas = [[(titulo, E_TITULO)], [(sub, E_SUB)], []]
    cols = [str(c) for c in df.columns]
    filas.append([(c, E_HDR) for c in cols])
    anchos = [min(40, max(13, len(c) * 2 // 3 + 2)) for c in cols]
    for fila in df.itertuples(index=False):
        out = []
        for i, v in enumerate(fila):
            v = _celda(v)
            out.append((v, E_NEGRITA if (i == 0 and v == SIMH_TODAS) else E_CELDA))
            anchos[i] = max(anchos[i], min(len(str(v)) + 3, 40))
        filas.append(out)
    return {"nombre": nombre, "filas": filas, "anchos": anchos}

def simh_excel(df, kdf, filtro_txt):
    prom = simh_promedios(df, kdf)
    sub = "Generado: " + datetime.now().strftime("%Y-%m-%d %H:%M") + " · " + filtro_txt
    notas = [[("NOTAS PARA INTERPRETAR ESTE ARCHIVO", E_TITULO)], [(sub, E_SUB)], []]
    for t in [
        "1. Todos los valores provienen del SIMULADOR de la app: un modelo what-if con supuestos explícitos (hoja «Supuestos del modelo» de la app).",
        "2. No son mediciones en una faena real; sirven para comparar escenarios y para explorar cuánta adopción y tiempo requiere el sistema.",
        "3. «Con sistema» = escenario simulado. «Sin sistema» = misma faena, misma demanda y misma semilla, pero sin adopción del sistema (control).",
        "4. Cada simulación se identifica por escenario + parámetros + semilla; la misma combinación no se cuenta dos veces.",
        "5. Los escenarios aleatorios se agrupan como «Aleatorio (varios)». «TODAS las simulaciones» mezcla escenarios distintos: úsalo con cuidado.",
        "6. Metas cumplidas: de los 10 KPIs, cuántos alcanzan la meta del mes 6 o del mes 12. Cumplimiento global: 0% = igual a la línea base, 100% = metas a 6 meses alcanzadas.",
        "7. Totales (despachos con material vencido, discrepancias, etc.): suma de todo el período simulado de cada simulación, luego promediada.",
        "8. Si hay una sola simulación en un grupo, la desviación estándar queda vacía (se necesitan al menos 2).",
        "9. El número de simulaciones (N) siempre se informa: un promedio de pocas simulaciones es poco confiable.",
        "10. El cumplimiento global se mide contra las metas a 6 meses y se topa en 100%; por eso en el mes 12 muchos escenarios marcan 100%.",
        "11. En el escenario «Sin sistema (control)» no hay adopción: sus columnas «con sistema» y «sin sistema» son la misma situación."]:
        notas.append([(t, E_NORMAL)])
    hojas = [simh_hoja("Resumen por escenario", prom["resumen"], "SIMULACIONES — PROMEDIOS POR ESCENARIO", sub),
             simh_hoja("KPIs promedio", prom["kpis"], "KPIs PROMEDIO POR ESCENARIO (MES 6 Y MES 12)", sub),
             simh_hoja("Evolución mensual", prom["mensual"], "EVOLUCIÓN MENSUAL PROMEDIO", sub),
             simh_hoja("Registro", simh_tabla_registro(df), "REGISTRO DE SIMULACIONES INCLUIDAS", sub),
             {"nombre": "Notas", "filas": notas, "anchos": [140]}]
    return xlsx_crear(hojas), prom

def _csv(df):
    return df.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig")

# ── Gráfico ──────────────────────────────────────────────────────────────────
def chs_hist_mensual(mensual):
    d = mensual[mensual["Escenario"] != SIMH_TODAS]
    if d.empty:
        d = mensual
    return alt.Chart(d).mark_line(point=True, strokeWidth=2.5).encode(
        x=alt.X("Mes:O", title="Mes simulado", axis=alt.Axis(labelAngle=0)),
        y=alt.Y("Cumplimiento global con sistema (%):Q", title="Cumplimiento global promedio (%)",
                scale=alt.Scale(domain=[-30, 115])),
        color=alt.Color("Escenario:N", legend=alt.Legend(title=None, orient="right", labelLimit=240)),
        tooltip=["Escenario", "Mes", "N", alt.Tooltip("Cumplimiento global con sistema (%):Q", format=".1f"),
                 alt.Tooltip("Cumplimiento global sin sistema (%):Q", format=".1f")]).properties(height=320)

# ── Módulo ───────────────────────────────────────────────────────────────────
def mod_sim_historial():
    st.title("📚 Historial de simulaciones")
    if not (puede("kpis") or puede("todo")):
        st.warning("El historial de simulaciones está disponible para el jefe de turno y el administrador.")
        return
    flash = st.session_state.pop("simh_flash_del", None)
    if flash:
        st.success(flash)
    st.info("Aquí queda el **registro de las simulaciones** hechas en el simulador (se guardan solas al completar los 12 meses, "
            "o con el botón «💾 Guardar en historial»). Puedes **descargar los promedios** para la memoria y "
            "**borrar el historial** para empezar de cero con otros datos. Los valores son de un modelo what-if, no mediciones en faena.")
    df_all = simh_cargar()
    if df_all.empty:
        st.warning("Todavía no hay simulaciones registradas. Ve a **🎮 Simulador de escenarios**, corre una simulación hasta el mes 12 "
                   "(se registra sola) o pulsa «💾 Guardar en historial».")
        return
    kdf = get_kpis()
    df_all = df_all.copy()
    df_all["_grupo"] = df_all["escenario"].map(simh_grupo)
    df_all["_et"] = df_all["etiqueta"].fillna("").map(lambda x: x if x else "(sin etiqueta)")

    # ── Filtros (afectan a Promedios y Descargar)
    with st.container(border=True):
        st.markdown("**Qué simulaciones entran en los promedios** (afecta a «Promedios» y «Descargar»)")
        f1, f2, f3 = st.columns([2, 2, 1.6])
        grupos = sorted(df_all["_grupo"].unique().tolist())
        etqs = sorted(df_all["_et"].unique().tolist())
        sel_g = f1.multiselect("Escenarios", grupos, default=grupos, key="simh_f_g")
        sel_e = f2.multiselect("Etiqueta / serie", etqs, default=etqs, key="simh_f_e")
        f3.markdown("<div style='height:1.7em'></div>", unsafe_allow_html=True)
        solo = f3.checkbox("Solo completas (12 meses)", value=True, key="simh_f_solo",
                           help="Recomendado: mezclar simulaciones cortas y completas distorsiona los promedios.")
    m = df_all["_grupo"].isin(sel_g) & df_all["_et"].isin(sel_e)
    if solo:
        m &= df_all["meses"] >= SIM_MESES_MAX
    df = df_all[m].drop(columns=["_grupo", "_et"])
    filtro_txt = ("Escenarios: " + (", ".join(sel_g) if sel_g else "ninguno") + " · Etiquetas: " +
                  (", ".join(sel_e) if sel_e else "ninguna") + " · " +
                  ("solo completas (12 meses)" if solo else "incluye parciales"))

    tabs = st.tabs(["📋 Registro", "📊 Promedios", "⬇️ Descargar", "🗑️ Borrar historial"])

    with tabs[0]:
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Simulaciones registradas", len(df_all))
        k2.metric("Completas (12 meses)", int((df_all["meses"] >= SIM_MESES_MAX).sum()))
        k3.metric("Parciales", int((df_all["meses"] < SIM_MESES_MAX).sum()))
        k4.metric("Escenarios distintos", len(grupos))
        reg = simh_tabla_registro(df_all.drop(columns=["_grupo", "_et"]))
        reg.insert(6, "En promedios", ["✅" if i in set(df["id"]) else "—" for i in df_all["id"]])
        vista = reg[["ID", "Fecha de registro", "Etiqueta", "Escenario", "Semilla", "Meses simulados", "En promedios",
                     "Adopción final (%)", "Metas cumplidas mes 6 (de 10)", "Metas cumplidas mes 12 (de 10)",
                     "Cumplimiento global con sistema (%)", "Cumplimiento global sin sistema (%)"]]
        vista = vista.copy()
        for c in ("Metas cumplidas mes 6 (de 10)", "Metas cumplidas mes 12 (de 10)"):
            vista[c] = vista[c].map(lambda v: "—" if _num(v) is None else str(int(v)))
        st.dataframe(vista, use_container_width=True, hide_index=True)
        st.caption("La misma combinación escenario + parámetros + semilla no se registra dos veces (se actualiza). "
                   "Para obtener datos nuevos cambia la semilla, el escenario o los parámetros.")
        with st.expander("✏️ Ponerle etiqueta a una simulación (para agrupar series, p. ej. «Serie A»)"):
            ids = df_all["id"].tolist()
            e1, e2, e3 = st.columns([2, 2, 1])
            sid = e1.selectbox("Simulación", ids, key="simh_et_id",
                               format_func=lambda i: i + " · " + str(df_all.loc[df_all["id"] == i, "escenario"].iloc[0]) +
                               " · semilla " + str(df_all.loc[df_all["id"] == i, "semilla"].iloc[0]))
            nueva = e2.text_input("Etiqueta", key="simh_et_txt", max_chars=40)
            e3.markdown("<div style='height:1.7em'></div>", unsafe_allow_html=True)
            if e3.button("Guardar etiqueta", use_container_width=True):
                simh_etiquetar(sid, nueva)
                st.rerun()
        with st.expander("🔎 Ver el detalle de una simulación"):
            sid2 = st.selectbox("Simulación", df_all["id"].tolist(), key="simh_det_id")
            fila = df_all[df_all["id"] == sid2].iloc[0]
            det = json.loads(fila["detalle_json"])
            filas = []
            for _, k in kdf.iterrows():
                f = {"KPI": k["nombre"], "Unidad": k["unidad"], "Línea base": k["valor_base"]}
                for mes in (6, 12):
                    f["Meta " + str(mes) + "m"] = k["meta_" + str(mes) + "m"]
                    f["Con sistema mes " + str(mes)] = det.get("kpi", {}).get(k["id"], {}).get(str(mes))
                    f["Sin sistema mes " + str(mes)] = det.get("kpi_ctrl", {}).get(k["id"], {}).get(str(mes))
                filas.append(f)
            st.dataframe(pd.DataFrame(filas), use_container_width=True, hide_index=True)
            st.caption("Parámetros: " + str(fila["params_json"]))

    with tabs[1]:
        if df.empty:
            st.warning("Con los filtros elegidos no hay simulaciones. Cambia los filtros de arriba.")
        else:
            prom = simh_promedios(df, kdf)
            n_tot = len(df)
            st.markdown("**Promedios por escenario** (" + str(n_tot) + " simulación" + ("es" if n_tot != 1 else "") + " incluida" +
                        ("s" if n_tot != 1 else "") + ")")
            res = prom["resumen"]
            st.dataframe(res, use_container_width=True, hide_index=True)
            if (res["N° de simulaciones"] < 3).any():
                st.caption("⚠️ Hay escenarios con menos de 3 simulaciones: su promedio es poco confiable. "
                           "Corre más semillas distintas del mismo escenario para afinarlo.")
            st.markdown("**Cumplimiento global promedio por mes**")
            if not prom["mensual"].empty:
                st.altair_chart(chs_hist_mensual(prom["mensual"]), use_container_width=True)
            st.markdown("**KPIs promedio en el mes 6 y el mes 12**")
            conj = st.selectbox("Escenario", prom["kpis"]["Escenario"].unique().tolist(), key="simh_prom_conj")
            st.dataframe(prom["kpis"][prom["kpis"]["Escenario"] == conj].drop(columns=["Escenario"]),
                         use_container_width=True, hide_index=True)

    with tabs[2]:
        if df.empty:
            st.warning("Con los filtros elegidos no hay simulaciones para descargar.")
        else:
            xl, prom = simh_excel(df, kdf, filtro_txt)
            st.markdown("**Excel para la memoria** — incluye 5 hojas: *Resumen por escenario* (la tabla de promedios), "
                        "*KPIs promedio*, *Evolución mensual*, *Registro* de las simulaciones incluidas y *Notas*.")
            st.caption(filtro_txt + " · " + str(len(df)) + " simulaciones")
            d1, d2, d3 = st.columns(3)
            nom = "promedios_simulaciones_" + datetime.now().strftime("%Y%m%d_%H%M")
            d1.download_button("📥 Descargar Excel (.xlsx)", data=xl, file_name=nom + ".xlsx", type="primary",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                               use_container_width=True)
            d2.download_button("📄 Solo tabla de promedios (.csv)", data=_csv(prom["resumen"]), file_name=nom + "_resumen.csv",
                               mime="text/csv", use_container_width=True)
            d3.download_button("📄 Registro completo (.csv)", data=_csv(simh_tabla_registro(df)), file_name=nom + "_registro.csv",
                               mime="text/csv", use_container_width=True)
            st.markdown("**Vista previa de la tabla de promedios**")
            st.dataframe(prom["resumen"], use_container_width=True, hide_index=True)

    with tabs[3]:
        st.warning("Borrar el historial **no afecta** a la simulación que tienes en pantalla, ni a los datos operativos "
                   "del polvorín, ni a los KPIs. Solo elimina los registros guardados aquí. **No se puede deshacer**: "
                   "descarga antes el Excel si lo necesitas.")
        st.caption("Tras borrar puedes crear nuevas simulaciones con otros datos (otra semilla, otro escenario u otros parámetros). "
                   "Si borras una simulación y vuelves a correr la misma, se registrará otra vez.")
        with st.container(border=True):
            st.markdown("**A · Borrar simulaciones elegidas**")
            elegidas = st.multiselect("Simulaciones a borrar", df_all["id"].tolist(), key="simh_del_ids",
                                      format_func=lambda i: i + " · " + str(df_all.loc[df_all["id"] == i, "escenario"].iloc[0]) +
                                      " · semilla " + str(df_all.loc[df_all["id"] == i, "semilla"].iloc[0]) +
                                      " · " + str(df_all.loc[df_all["id"] == i, "_et"].iloc[0]))
            ok_a = st.checkbox("Confirmo que quiero borrar las simulaciones elegidas", key="simh_del_ok_a")
            if st.button("🗑️ Borrar elegidas", disabled=not (elegidas and ok_a), key="simh_del_btn_a"):
                n = simh_borrar(ids=elegidas)
                st.session_state["simh_flash_del"] = "Se borraron " + str(n) + " simulación(es) del historial."
                for k in ("simh_del_ids", "simh_del_ok_a"):
                    st.session_state.pop(k, None)
                st.rerun()
        with st.container(border=True):
            st.markdown("**B · Borrar una serie completa (por etiqueta)**")
            b1, b2 = st.columns([2, 1])
            et_sel = b1.selectbox("Etiqueta", etqs, key="simh_del_et")
            n_et = int((df_all["_et"] == et_sel).sum())
            ok_b = b1.checkbox("Confirmo borrar las " + str(n_et) + " simulación(es) con esa etiqueta", key="simh_del_ok_b")
            b2.markdown("<div style='height:1.7em'></div>", unsafe_allow_html=True)
            if b2.button("🗑️ Borrar serie", disabled=not ok_b, key="simh_del_btn_b", use_container_width=True):
                n = simh_borrar(ids=df_all.loc[df_all["_et"] == et_sel, "id"].tolist())
                st.session_state["simh_flash_del"] = "Se borraron " + str(n) + " simulación(es) de la serie «" + et_sel + "»."
                st.session_state.pop("simh_del_ok_b", None)
                st.rerun()
        with st.container(border=True):
            st.markdown("**C · Borrar TODO el historial**")
            txt = st.text_input("Escribe BORRAR para confirmar (" + str(len(df_all)) + " simulaciones se eliminarán)",
                                key="simh_del_txt")
            if st.button("🗑️ Borrar todo el historial", type="primary", disabled=(txt.strip() != "BORRAR"),
                         key="simh_del_btn_c"):
                n = simh_borrar(todo=True)
                st.session_state["simh_flash_del"] = "Historial vaciado: se borraron " + str(n) + " simulación(es). Ya puedes empezar de nuevo."
                st.session_state.pop("simh_del_txt", None)
                st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════
init_db()

if not st.session_state.get("autenticado"):
    pantalla_login()
else:
    modulo = sidebar()
    # Parte 1
    if   "Estado General" in modulo: mod_dashboard()
    elif "Inventario"     in modulo: mod_inventario()
    elif "Alertas"        in modulo: mod_alertas()
    elif "Accesos"        in modulo: mod_accesos()
    elif "Condiciones"    in modulo: mod_condiciones()
    elif "Traslados"      in modulo: mod_traslados()
    elif "Reportes"       in modulo: mod_reportes()
    elif "Auditoría"      in modulo: mod_auditoria()
    elif "Administración" in modulo: mod_admin()
    elif "Manual"         in modulo: mod_manual()
    # Parte 2
    elif "KPIs"           in modulo: mod_kpis()
    elif "Vista por Rol"  in modulo: mod_vista_rol()
    elif "Libro Control"  in modulo: mod_libro_control()
    elif "Asistente IA"   in modulo: mod_asistente_ia()
    elif "Acerca"         in modulo: mod_acerca()
    # Parte 3
    elif "Simulador"      in modulo: mod_simulador()
    elif "Historial"      in modulo: mod_sim_historial()
    elif "Supuestos"      in modulo: mod_simulador_supuestos()
