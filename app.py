import streamlit as st
import pandas as pd
from datetime import datetime
import io
from supabase import create_client, Client
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(
    page_title="Caja Diaria - Venta Café",
    page_icon="☕",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# --- CONEXIÓN A SUPABASE ---
@st.cache_resource
def init_supabase() -> Client:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase = init_supabase()

# --- CONFIGURACIÓN DE USUARIOS Y PINS ---
USUARIOS = {
    "6666": {"id": "usr1", "nombre": "Mikel"},
    "8888": {"id": "usr2", "nombre": "Comercial 2"}
}

# --- CONTROL DE ACCESO MEDIANTE PIN ---
if "autenticado" not in st.session_state:
    st.session_state.autenticado = False
    st.session_state.usuario_actual = None

if not st.session_state.autenticado:
    st.title("☕ Venta Café — Control de Acceso")
    st.caption("Introduce tu PIN de seguridad para acceder a tu caja.")
    
    with st.form("form_login"):
        pin_input = st.text_input("PIN de Acceso", type="password", placeholder="****")
        btn_login = st.form_submit_button("🔓 Entrar", use_container_width=True)
        
        if btn_login:
            if pin_input in USUARIOS:
                st.session_state.autenticado = True
                st.session_state.usuario_actual = USUARIOS[pin_input]
                st.success(f"Bienvenido, {USUARIOS[pin_input]['nombre']}")
                st.rerun()
            else:
                st.error("PIN incorrecto. Inténtalo de nuevo.")
    st.stop()

user_id = st.session_state.usuario_actual["id"]
user_nombre = st.session_state.usuario_actual["nombre"]

# --- FUNCIONES DE BASE DE DATOS (Caja Activa Multidía) ---
def obtener_cobros_activos(u_id):
    res = supabase.table("cobros").select("*").eq("usuario_id", u_id).execute()
    data = res.data
    if data:
        df = pd.DataFrame(data)
        df["importe"] = df["importe"].astype(float)
        return df
    return pd.DataFrame(columns=["id", "usuario_id", "fecha", "hora", "cliente", "albaran", "importe"])

def guardar_cliente_habitual(nombre_cliente, u_id):
    if nombre_cliente and nombre_cliente.strip():
        nombre_clean = nombre_cliente.strip()
        exist = supabase.table("clientes").select("id").eq("usuario_id", u_id).eq("nombre", nombre_clean).execute()
        if not exist.data:
            supabase.table("clientes").insert({"usuario_id": u_id, "nombre": nombre_clean}).execute()

def obtener_todos_los_clientes(u_id):
    res = supabase.table("clientes").select("id, nombre").eq("usuario_id", u_id).order("nombre", desc=False).execute()
    if res.data:
        return [(r["id"], r["nombre"]) for r in res.data]
    return []

def eliminar_cliente_habitual(id_cliente, u_id):
    supabase.table("clientes").delete().eq("id", id_cliente).eq("usuario_id", u_id).execute()

def agregar_cobro(fecha, hora, cliente, albaran, importe, u_id):
    guardar_cliente_habitual(cliente, u_id)
    supabase.table("cobros").insert({
        "usuario_id": u_id,
        "fecha": fecha,
        "hora": hora,
        "cliente": cliente,
        "albaran": albaran,
        "importe": float(importe)
    }).execute()

def actualizar_cobro(id_cobro, cliente, albaran, importe, u_id):
    guardar_cliente_habitual(cliente, u_id)
    supabase.table("cobros").update({
        "cliente": cliente,
        "albaran": albaran,
        "importe": float(importe)
    }).eq("id", id_cobro).eq("usuario_id", u_id).execute()

def eliminar_cobro(id_cobro, u_id):
    supabase.table("cobros").delete().eq("id", id_cobro).eq("usuario_id", u_id).execute()

def obtener_gastos_activos(u_id):
    res = supabase.table("gastos").select("*").eq("usuario_id", u_id).execute()
    data = res.data
    if data:
        df = pd.DataFrame(data)
        df["importe"] = df["importe"].astype(float)
        return df
    return pd.DataFrame(columns=["id", "usuario_id", "fecha", "hora", "concepto", "importe"])

def agregar_gasto(fecha, hora, concepto, importe, u_id):
    supabase.table("gastos").insert({
        "usuario_id": u_id,
        "fecha": fecha,
        "hora": hora,
        "concepto": concepto,
        "importe": float(importe)
    }).execute()

def eliminar_gasto(id_gasto, u_id):
    supabase.table("gastos").delete().eq("id", id_gasto).eq("usuario_id", u_id).execute()

# --- FUNCIONES DE ARQUEO Y BORRADOR PERSISTENTE ---
def obtener_arqueo_guardado(u_id):
    res = supabase.table("caja_activa").select("*").eq("usuario_id", u_id).execute()
    if res.data:
        return res.data[0]
    return None

def guardar_arqueo_bd(u_id, datos_dict, obs_text):
    payload = {"usuario_id": u_id, "observaciones": obs_text}
    payload.update(datos_dict)
    res = supabase.table("caja_activa").select("usuario_id").eq("usuario_id", u_id).execute()
    if res.data:
        supabase.table("caja_activa").update(payload).eq("usuario_id", u_id).execute()
    else:
        supabase.table("caja_activa").insert(payload).execute()

def vaciar_arqueo_bd(u_id):
    supabase.table("caja_activa").delete().eq("usuario_id", u_id).execute()

def cerrar_y_guardar_caja(u_id, t_ventas, t_gastos, t_efectivo, dif, obs, desglose_dict):
    now = datetime.now()
    fecha_c = now.strftime("%d/%m/%Y")
    hora_c = now.strftime("%H:%M")
    
    payload = {
        "usuario_id": u_id,
        "fecha_cierre": fecha_c,
        "hora_cierre": hora_c,
        "total_ventas": float(t_ventas),
        "total_gastos": float(t_gastos),
        "total_efectivo": float(t_efectivo),
        "diferencia": float(dif),
        "observaciones": obs
    }
    if desglose_dict:
        for k, v in desglose_dict.items():
            payload[k] = int(v[0])
            
    supabase.table("cierres").insert(payload).execute()
    supabase.table("cobros").delete().eq("usuario_id", u_id).execute()
    supabase.table("gastos").delete().eq("usuario_id", u_id).execute()
    vaciar_arqueo_bd(u_id)

def obtener_historial_cierres(u_id):
    res = supabase.table("cierres").select("*").eq("usuario_id", u_id).order("id", desc=True).execute()
    return res.data if res.data else []

# --- GENERADORES DE PDF ---
def generar_pdf_a4(cobros_df, gastos_df, t_cobros, t_gastos, t_billetes, t_monedas, t_fisico, dif, persona, desglose, obs, fecha_h_custom=None):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    story = []
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle('DocTitle', parent=styles['Title'], fontSize=15, leading=18, textColor=colors.HexColor('#1E293B'), alignment=0)
    sub_style = ParagraphStyle('DocSub', parent=styles['Normal'], fontSize=9, textColor=colors.HexColor('#475569'))
    cell_style = ParagraphStyle('Cell', parent=styles['Normal'], fontSize=8, leading=10)
    cell_bold = ParagraphStyle('CellB', parent=styles['Normal'], fontSize=8, leading=10, fontName='Helvetica-Bold')

    fecha_h_gen = fecha_h_custom if fecha_h_custom else datetime.now().strftime("%d/%m/%Y a las %H:%M")

    story.append(Paragraph("<b>VENTA CAFÉ — HOJA DE CIERRE DE CAJA</b>", title_style))
    story.append(Spacer(1, 4))
    story.append(Paragraph(f"<b>Fecha/Hora Cierre:</b> {fecha_h_gen} &nbsp;&nbsp;|&nbsp;&nbsp; <b>Entregado por:</b> {persona}", sub_style))
    story.append(Spacer(1, 10))

    story.append(Paragraph("<b>VENTAS CAFÉ (ALBARANES)</b>", cell_bold))
    story.append(Spacer(1, 4))
    
    data_c = [[Paragraph("<b>Nº Albarán</b>", cell_bold), Paragraph("<b>Cliente</b>", cell_bold), Paragraph("<b>Fecha/Hora</b>", cell_bold), Paragraph("<b>Importe (€)</b>", cell_bold)]]
    
    if cobros_df is not None and not cobros_df.empty:
        for _, r in cobros_df.iterrows():
            fh = f"{r['fecha']} {r['hora']}" if 'fecha' in r else str(r['hora'])
            data_c.append([
                Paragraph(str(r['albaran']) if r['albaran'] else "-", cell_style),
                Paragraph(str(r['cliente']), cell_style),
                Paragraph(fh, cell_style),
                Paragraph(f"{float(r['importe']):.2f} €", cell_bold)
            ])
    data_c.append([Paragraph("<b>TOTAL VENTAS</b>", cell_bold), "", "", Paragraph(f"<b>{t_cobros:.2f} €</b>", cell_bold)])

    t_cobros_table = Table(data_c, colWidths=[80, 230, 90, 90])
    t_cobros_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#E2E8F0')),
        ('GRID', (0, 0), (-1, -2), 0.5, colors.HexColor('#CBD5E1')),
        ('SPAN', (0, -1), (2, -1)),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#F1F5F9')),
        ('ALIGN', (-1, 0), (-1, -1), 'RIGHT'),
        ('PADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(t_cobros_table)
    story.append(Spacer(1, 10))

    if gastos_df is not None and not gastos_df.empty:
        story.append(Paragraph("<b>GASTOS / SALIDAS DE CAJA</b>", cell_bold))
        story.append(Spacer(1, 4))
        data_g = [[Paragraph("<b>Concepto</b>", cell_bold), Paragraph("<b>Fecha/Hora</b>", cell_bold), Paragraph("<b>Importe (€)</b>", cell_bold)]]
        for _, r in gastos_df.iterrows():
            fh_g = f"{r['fecha']} {r['hora']}" if 'fecha' in r else str(r['hora'])
            data_g.append([Paragraph(str(r['concepto']), cell_style), Paragraph(fh_g, cell_style), Paragraph(f"{float(r['importe']):.2f} €", cell_bold)])
        data_g.append([Paragraph("<b>TOTAL GASTOS</b>", cell_bold), "", Paragraph(f"<b>{t_gastos:.2f} €</b>", cell_bold)])

        t_gastos_table = Table(data_g, colWidths=[320, 90, 80])
        t_gastos_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#FEE2E2')),
            ('GRID', (0, 0), (-1, -2), 0.5, colors.HexColor('#FCA5A5')),
            ('SPAN', (0, -1), (1, -1)),
            ('ALIGN', (-1, 0), (-1, -1), 'RIGHT'),
            ('PADDING', (0, 0), (-1, -1), 4),
        ]))
        story.append(t_gastos_table)
        story.append(Spacer(1, 10))

    if desglose:
        story.append(Paragraph("<b>DESGLOSE DETALLADO DE EFECTIVO (DESGLOSE CONTABLE)</b>", cell_bold))
        story.append(Spacer(1, 4))

        data_desglose = [
            [Paragraph("<b>BILLETES</b>", cell_bold), Paragraph("<b>Cant.</b>", cell_bold), Paragraph("<b>Total</b>", cell_bold),
             Paragraph("<b>MONEDAS</b>", cell_bold), Paragraph("<b>Cant.</b>", cell_bold), Paragraph("<b>Total</b>", cell_bold)],
            
            [Paragraph("100 €", cell_style), Paragraph(str(desglose["b100"][0]), cell_style), Paragraph(f"{desglose['b100'][1]:.2f} €", cell_style),
             Paragraph("2,00 €", cell_style), Paragraph(str(desglose["m200"][0]), cell_style), Paragraph(f"{desglose['m200'][1]:.2f} €", cell_style)],
            
            [Paragraph("50 €", cell_style), Paragraph(str(desglose["b50"][0]), cell_style), Paragraph(f"{desglose['b50'][1]:.2f} €", cell_style),
             Paragraph("1,00 €", cell_style), Paragraph(str(desglose["m100"][0]), cell_style), Paragraph(f"{desglose['m100'][1]:.2f} €", cell_style)],
            
            [Paragraph("20 €", cell_style), Paragraph(str(desglose["b20"][0]), cell_style), Paragraph(f"{desglose['b20'][1]:.2f} €", cell_style),
             Paragraph("0,50 €", cell_style), Paragraph(str(desglose["m050"][0]), cell_style), Paragraph(f"{desglose['m050'][1]:.2f} €", cell_style)],
            
            [Paragraph("10 €", cell_style), Paragraph(str(desglose["b10"][0]), cell_style), Paragraph(f"{desglose['b10'][1]:.2f} €", cell_style),
             Paragraph("0,20 €", cell_style), Paragraph(str(desglose["m020"][0]), cell_style), Paragraph(f"{desglose['m020'][1]:.2f} €", cell_style)],
            
            [Paragraph("5 €", cell_style), Paragraph(str(desglose["b5"][0]), cell_style), Paragraph(f"{desglose['b5'][1]:.2f} €", cell_style),
             Paragraph("0,10 €", cell_style), Paragraph(str(desglose["m010"][0]), cell_style), Paragraph(f"{desglose['m010'][1]:.2f} €", cell_style)],
            
            [Paragraph("", cell_style), Paragraph("", cell_style), Paragraph("", cell_style),
             Paragraph("0,05 €", cell_style), Paragraph(str(desglose["m005"][0]), cell_style), Paragraph(f"{desglose['m005'][1]:.2f} €", cell_style)],
            
            [Paragraph("", cell_style), Paragraph("", cell_style), Paragraph("", cell_style),
             Paragraph("0,02 €", cell_style), Paragraph(str(desglose["m002"][0]), cell_style), Paragraph(f"{desglose['m002'][1]:.2f} €", cell_style)],
            
            [Paragraph("", cell_style), Paragraph("", cell_style), Paragraph("", cell_style),
             Paragraph("0,01 €", cell_style), Paragraph(str(desglose["m001"][0]), cell_style), Paragraph(f"{desglose['m001'][1]:.2f} €", cell_style)],
            
            [Paragraph("<b>TOTAL BILLETES</b>", cell_bold), "", Paragraph(f"<b>{t_billetes:.2f} €</b>", cell_bold),
             Paragraph("<b>TOTAL MONEDAS</b>", cell_bold), "", Paragraph(f"<b>{t_monedas:.2f} €</b>", cell_bold)]
        ]

        t_desglose_table = Table(data_desglose, colWidths=[80, 45, 120, 80, 45, 130])
        t_desglose_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#F1F5F9')),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
            ('SPAN', (0, -1), (1, -1)),
            ('SPAN', (3, -1), (4, -1)),
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#E2E8F0')),
            ('ALIGN', (1, 0), (2, -1), 'RIGHT'),
            ('ALIGN', (4, 0), (5, -1), 'RIGHT'),
            ('PADDING', (0, 0), (-1, -1), 3),
        ]))
        story.append(t_desglose_table)
        story.append(Spacer(1, 10))

    t_teorico = t_cobros - t_gastos
    texto_dif = f"+{dif:.2f} € (Sobrante)" if dif > 0 else (f"{dif:.2f} € (Faltante)" if dif < 0 else "0.00 € (Cuadra)")
    data_a = [
        [Paragraph("<b>Total Ventas Albaranes:</b>", cell_style), Paragraph(f"{t_cobros:.2f} €", cell_style), Paragraph("<b>Total Billetes Contados:</b>", cell_style), Paragraph(f"{t_billetes:.2f} €", cell_style)],
        [Paragraph("<b>(-) Gastos en Metálico:</b>", cell_style), Paragraph(f"-{t_gastos:.2f} €", cell_style), Paragraph("<b>Total Monedas Contadas:</b>", cell_style), Paragraph(f"{t_monedas:.2f} €", cell_style)],
        [Paragraph("<b>TOTAL TEÓRICO CAJA:</b>", cell_bold), Paragraph(f"<b>{t_teorico:.2f} €</b>", cell_bold), Paragraph("<b>TOTAL EFECTIVO CONTADO:</b>", cell_bold), Paragraph(f"<b>{t_fisico:.2f} €</b>", cell_bold)],
        [Paragraph("<b>DIFERENCIA DE ARQUEO:</b>", cell_bold), Paragraph(f"<b>{texto_dif}</b>", cell_bold), "", ""]
    ]

    t_arqueo_table = Table(data_a, colWidths=[130, 120, 130, 120])
    t_arqueo_table.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
        ('SPAN', (1, 3), (3, 3)),
        ('BACKGROUND', (0, 2), (-1, 3), colors.HexColor('#F8FAFC')),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('ALIGN', (3, 0), (3, -1), 'RIGHT'),
        ('PADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(t_arqueo_table)

    if obs and obs.strip():
        story.append(Spacer(1, 10))
        story.append(Paragraph("<b>OBSERVACIONES:</b>", cell_bold))
        story.append(Spacer(1, 2))
        story.append(Paragraph(obs.strip(), cell_style))

    doc.build(story)
    buffer.seek(0)
    return buffer

def generar_pdf_ticket_termico(cobros_df, gastos_df, t_cobros, t_gastos, t_billetes, t_monedas, t_fisico, dif, persona, desglose, obs, fecha_h_custom=None):
    buffer = io.BytesIO()
    PAGE_WIDTH = 317.0
    
    n_cobros = len(cobros_df) if cobros_df is not None and not cobros_df.empty else 1
    n_gastos = len(gastos_df) if gastos_df is not None and not gastos_df.empty else 0
    n_desglose = sum(1 for v in desglose.values() if v[0] > 0) if desglose else 0
    
    estimated_height = 250 + (n_cobros * 18) + (n_gastos * 18) + (n_desglose * 16) + (80 if obs else 0)
    
    doc = SimpleDocTemplate(
        buffer, 
        pagesize=(PAGE_WIDTH, float(estimated_height)), 
        rightMargin=10, 
        leftMargin=10, 
        topMargin=12, 
        bottomMargin=12
    )
    story = []
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle('TTitle', parent=styles['Title'], fontSize=14, leading=16, alignment=1)
    body_style = ParagraphStyle('TBody', parent=styles['Normal'], fontSize=10, leading=12)
    bold_style = ParagraphStyle('TBold', parent=styles['Normal'], fontSize=10, leading=12, fontName='Helvetica-Bold')

    fecha_h_gen = fecha_h_custom if fecha_h_custom else datetime.now().strftime("%d/%m/%Y %H:%M")

    story.append(Paragraph("<b>VENTA CAFÉ - CIERRE CAJA</b>", title_style))
    story.append(Spacer(1, 6))
    story.append(Paragraph(f"<b>Fecha:</b> {fecha_h_gen}", body_style))
    story.append(Paragraph(f"<b>Comercial:</b> {persona}", body_style))
    story.append(Spacer(1, 8))

    if cobros_df is not None and not cobros_df.empty:
        story.append(Paragraph("<b>COBROS / ALBARANES</b>", bold_style))
        story.append(Spacer(1, 3))
        data_c = []
        for _, r in cobros_df.iterrows():
            alb = f"#{r['albaran']}" if r['albaran'] else f"#{r['id']}"
            cli = str(r['cliente'])[:14]
            data_c.append([
                Paragraph(alb, body_style),
                Paragraph(cli, body_style),
                Paragraph(f"{float(r['importe']):.2f} €", bold_style)
            ])
        data_c.append([Paragraph("<b>TOTAL VENTAS</b>", bold_style), "", Paragraph(f"<b>{t_cobros:.2f} €</b>", bold_style)])

        t_cobros_tbl = Table(data_c, colWidths=[65, 150, 82])
        t_cobros_tbl.setStyle(TableStyle([
            ('LINEBELOW', (0, -1), (-1, -1), 0.8, colors.black),
            ('ALIGN', (-1, 0), (-1, -1), 'RIGHT'),
            ('SPAN', (0, -1), (1, -1)),
            ('PADDING', (0, 0), (-1, -1), 3),
        ]))
        story.append(t_cobros_tbl)
        story.append(Spacer(1, 8))

    if gastos_df is not None and not gastos_df.empty:
        story.append(Paragraph("<b>GASTOS DE CAJA</b>", bold_style))
        story.append(Spacer(1, 3))
        data_g = []
        for _, r in gastos_df.iterrows():
            data_g.append([
                Paragraph(str(r['concepto'])[:18], body_style),
                Paragraph(f"{float(r['importe']):.2f} €", bold_style)
            ])
        data_g.append([Paragraph("<b>TOTAL GASTOS</b>", bold_style), Paragraph(f"<b>{t_gastos:.2f} €</b>", bold_style)])
        t_gastos_tbl = Table(data_g, colWidths=[215, 82])
        t_gastos_tbl.setStyle(TableStyle([
            ('LINEBELOW', (0, -1), (-1, -1), 0.8, colors.black),
            ('ALIGN', (-1, 0), (-1, -1), 'RIGHT'),
            ('PADDING', (0, 0), (-1, -1), 3),
        ]))
        story.append(t_gastos_tbl)
        story.append(Spacer(1, 8))

    if desglose:
        story.append(Paragraph("<b>DESGLOSE DE EFECTIVO CONTADO</b>", bold_style))
        story.append(Spacer(1, 3))
        data_d = []
        etiquetas = {
            "b100": "100€", "b50": "50€", "b20": "20€", "b10": "10€", "b5": "5€",
            "m200": "2,00€", "m100": "1,00€", "m050": "0,50€", "m020": "0,20€",
            "m010": "0,10€", "m005": "0,05€", "m002": "0,02€", "m001": "0,01€"
        }
        for k, v in desglose.items():
            cant, tot = v
            if cant > 0:
                data_d.append([
                    Paragraph(etiquetas[k], body_style),
                    Paragraph(f"x{cant}", body_style),
                    Paragraph(f"{tot:.2f} €", body_style)
                ])
        data_d.append([Paragraph("<b>TOTAL CONTADO</b>", bold_style), "", Paragraph(f"<b>{t_fisico:.2f} €</b>", bold_style)])
        
        t_desglose_tbl = Table(data_d, colWidths=[110, 50, 137])
        t_desglose_tbl.setStyle(TableStyle([
            ('LINEBELOW', (0, -1), (-1, -1), 0.8, colors.black),
            ('ALIGN', (-1, 0), (-1, -1), 'RIGHT'),
            ('SPAN', (0, -1), (1, -1)),
            ('PADDING', (0, 0), (-1, -1), 3),
        ]))
        story.append(t_desglose_tbl)
        story.append(Spacer(1, 8))

    t_teorico = t_cobros - t_gastos
    texto_dif = f"+{dif:.2f} € (Sobrante)" if dif > 0 else (f"{dif:.2f} € (Faltante)" if dif < 0 else "0.00 € (OK)")
    
    story.append(Paragraph(f"<b>Total Ventas:</b> {t_cobros:.2f} €", body_style))
    story.append(Paragraph(f"<b>Total Gastos:</b> {t_gastos:.2f} €", body_style))
    story.append(Paragraph(f"<b>Total Teórico:</b> {t_teorico:.2f} €", body_style))
    story.append(Paragraph(f"<b>Efectivo Contado:</b> {t_fisico:.2f} €", body_style))
    story.append(Spacer(1, 2))
    story.append(Paragraph(f"<b>Diferencia:</b> {texto_dif}", bold_style))

    if obs and obs.strip():
        story.append(Spacer(1, 6))
        story.append(Paragraph(f"<b>Obs:</b> {obs.strip()}", body_style))

    doc.build(story)
    buffer.seek(0)
    return buffer

# --- CARGAR ESTADO Y RECUPERAR BORRADOR DE SUPABASE ---
denominaciones = ["b100", "b50", "b20", "b10", "b5", "m200", "m100", "m050", "m020", "m010", "m005", "m002", "m001"]

if "caja_activa_cargada" not in st.session_state:
    st.session_state.caja_activa_cargada = {}

if user_id not in st.session_state.caja_activa_cargada:
    bd_arqueo = obtener_arqueo_guardado(user_id)
    if bd_arqueo:
        for d in denominaciones:
            st.session_state[f"{user_id}_{d}"] = int(bd_arqueo.get(d, 0))
        st.session_state[f"{user_id}_observaciones"] = bd_arqueo.get("observaciones", "") or ""
    else:
        for d in denominaciones:
            if f"{user_id}_{d}" not in st.session_state:
                st.session_state[f"{user_id}_{d}"] = 0
        if f"{user_id}_observaciones" not in st.session_state:
            st.session_state[f"{user_id}_observaciones"] = ""
    st.session_state.caja_activa_cargada[user_id] = True

# Cabecera
col_tit, col_logout = st.columns([3, 1])
with col_tit:
    st.title("☕ Venta Café — Caja Activa")
    st.caption(f"👤 Comercial: **{user_nombre}** | Estado: **Caja en Curso**")
with col_logout:
    if st.button("🔒 Salir"):
        st.session_state.autenticado = False
        st.session_state.usuario_actual = None
        st.rerun()

df_cobros = obtener_cobros_activos(user_id)
df_gastos = obtener_gastos_activos(user_id)
lista_clientes = obtener_todos_los_clientes(user_id)
nombres_clientes = [c[1] for c in lista_clientes]

# --- PESTAÑAS DE NAVEGACIÓN ---
tab_cobros, tab_gastos, tab_arqueo, tab_pdf, tab_historial = st.tabs(["💰 Cobros", "💸 Gastos", "🧮 Arqueo", "📄 PDF / Cierre", "📜 Historial"])

# ==========================================
# PESTAÑA 1: COBROS (VENTAS CAFÉ)
# ==========================================
with tab_cobros:
    st.subheader("📝 Registrar Cobro")
    
    es_edicion = st.session_state.edit_id is not None
    row_edit = None
    if es_edicion and not df_cobros.empty:
        filtered = df_cobros[df_cobros["id"] == st.session_state.edit_id]
        if not filtered.empty:
            row_edit = filtered.iloc[0]

    val_cliente = row_edit["cliente"] if row_edit is not None else ""
    val_albaran = row_edit["albaran"] if row_edit is not None else ""
    val_importe = float(row_edit["importe"]) if row_edit is not None else 0.0

    if es_edicion:
        st.info(f"✏️ Editando cobro ID #{st.session_state.edit_id}")

    with st.form("form_cobro", clear_on_submit=not es_edicion):
        if nombres_clientes and not es_edicion:
            cliente_sel = st.selectbox("Cliente habitual", ["-- Nuevo cliente --"] + nombres_clientes)
            cliente_inp = st.text_input("Nombre del Cliente (si es nuevo o diferente)", value="")
            cliente = cliente_inp.strip() if cliente_inp.strip() else (cliente_sel if cliente_sel != "-- Nuevo cliente --" else "")
        else:
            cliente = st.text_input("Nombre del Cliente", value=val_cliente, placeholder="Ej: Bar Plaza / Ogi Berri")

        albaran = st.text_input("Nº Albarán", value=val_albaran, placeholder="Ej: 10452")
        importe = st.number_input("Importe (€)", min_value=0.0, step=0.5, value=val_importe, format="%.2f")

        col1, col2 = st.columns(2)
        with col1:
            btn_guardar = st.form_submit_button("💾 Guardar Cobro" if not es_edicion else "🔄 Actualizar", use_container_width=True)
        with col2:
            btn_cancelar = st.form_submit_button("❌ Cancelar", use_container_width=True) if es_edicion else False

    if btn_cancelar and es_edicion:
        st.session_state.edit_id = None
        st.rerun()

    if btn_guardar:
        if not cliente:
            st.error("Por favor, introduce el nombre del cliente.")
        elif importe <= 0:
            st.error("El importe debe ser mayor que 0.00 €.")
        else:
            hora_act = datetime.now().strftime("%H:%M")
            fecha_act = datetime.now().strftime("%d/%m/%Y")
            if es_edicion:
                actualizar_cobro(st.session_state.edit_id, cliente, albaran, importe, user_id)
                st.session_state.edit_id = None
                st.success("✅ Cobro actualizado.")
            else:
                agregar_cobro(fecha_act, hora_act, cliente, albaran, importe, user_id)
                st.success("✅ Cobro registrado.")
            st.rerun()

    st.divider()
    total_cobros = df_cobros["importe"].sum() if not df_cobros.empty else 0.0
    st.metric("💵 TOTAL VENTAS CAFÉ (CAJA EN CURSO)", f"{total_cobros:.2f} €")

    if not df_cobros.empty:
        st.write("### Listado de Cobros Registrados")
        for _, row in df_cobros.iterrows():
            with st.expander(f"📌 #{row['albaran'] or row['id']} | {row['cliente']} — {row['importe']:.2f} € ({row['fecha']} - {row['hora']})"):
                st.write(f"**Cliente:** {row['cliente']}")
                st.write(f"**Albarán:** {row['albaran'] if row['albaran'] else 'N/A'}")
                st.write(f"**Importe:** {row['importe']:.2f} €")
                st.write(f"**Fecha / Hora:** {row['fecha']} a las {row['hora']}")
                
                c1, c2 = st.columns(2)
                with c1:
                    if st.button("✏️ Editar", key=f"edit_c_{row['id']}", use_container_width=True):
                        st.session_state.edit_id = int(row['id'])
                        st.rerun()
                with c2:
                    if st.button("🗑️ Eliminar", key=f"del_c_{row['id']}", use_container_width=True):
                        eliminar_cobro(row['id'], user_id)
                        st.rerun()

    st.divider()

    if lista_clientes:
        with st.expander("👥 Mis Clientes Habituales"):
            st.caption("Elimina de tu lista habitual los clientes que ya no utilices.")
            for c_id, c_nombre in lista_clientes:
                col_c1, col_c2 = st.columns([3, 1])
                with col_c1:
                    st.write(f"• **{c_nombre}**")
                with col_c2:
                    if st.button("🗑️ Borrar", key=f"del_cli_{c_id}"):
                        eliminar_cliente_habitual(c_id, user_id)
                        st.rerun()

# ==========================================
# PESTAÑA 2: GASTOS DE CAJA
# ==========================================
with tab_gastos:
    st.subheader("💸 Salidas / Gastos de Caja")

    with st.form("form_gasto", clear_on_submit=True):
        concepto_gasto = st.text_input("Concepto del Gasto", placeholder="Ej: Parking / Hielo")
        importe_gasto = st.number_input("Importe Gasto (€)", min_value=0.0, step=0.5, format="%.2f")
        btn_gasto = st.form_submit_button("💾 Registrar Gasto", use_container_width=True)

    if btn_gasto:
        if not concepto_gasto.strip():
            st.error("Introduce el concepto del gasto.")
        elif importe_gasto <= 0:
            st.error("El importe debe ser mayor que 0.00 €.")
        else:
            fecha_act = datetime.now().strftime("%d/%m/%Y")
            hora_act = datetime.now().strftime("%H:%M")
            agregar_gasto(fecha_act, hora_act, concepto_gasto.strip(), importe_gasto, user_id)
            st.success("✅ Gasto registrado.")
            st.rerun()

    st.divider()
    total_gastos = df_gastos["importe"].sum() if not df_gastos.empty else 0.0
    st.metric("📉 TOTAL GASTOS", f"{total_gastos:.2f} €")

    if not df_gastos.empty:
        for _, row in df_gastos.iterrows():
            col_g1, col_g2 = st.columns([3, 1])
            with col_g1:
                st.write(f"• **{row['concepto']}**: {row['importe']:.2f} € ({row['fecha']} - {row['hora']})")
            with col_g2:
                if st.button("🗑️", key=f"del_g_{row['id']}"):
                    eliminar_gasto(row['id'], user_id)
                    st.rerun()

# ==========================================
# PESTAÑA 3: ARQUEO DE BILLETES Y MONEDAS
# ==========================================
with tab_arqueo:
    st.subheader("🧮 Conteo Físico (Billetes y Monedas)")

    col_b, col_m = st.columns(2)

    with col_b:
        st.write("#### 💵 Billetes")
        b100 = st.number_input("Billetes 100€", min_value=0, step=1, key=f"{user_id}_b100")
        b50  = st.number_input("Billetes 50€", min_value=0, step=1, key=f"{user_id}_b50")
        b20  = st.number_input("Billetes 20€", min_value=0, step=1, key=f"{user_id}_b20")
        b10  = st.number_input("Billetes 10€", min_value=0, step=1, key=f"{user_id}_b10")
        b5   = st.number_input("Billetes 5€", min_value=0, step=1, key=f"{user_id}_b5")

    with col_m:
        st.write("#### 🪙 Monedas")
        m200 = st.number_input("Monedas 2,00€", min_value=0, step=1, key=f"{user_id}_m200")
        m100 = st.number_input("Monedas 1,00€", min_value=0, step=1, key=f"{user_id}_m100")
        m050 = st.number_input("Monedas 0,50€", min_value=0, step=1, key=f"{user_id}_m050")
        m020 = st.number_input("Monedas 0,20€", min_value=0, step=1, key=f"{user_id}_m020")
        m010 = st.number_input("Monedas 0,10€", min_value=0, step=1, key=f"{user_id}_m010")
        m005 = st.number_input("Monedas 0,05€", min_value=0, step=1, key=f"{user_id}_m005")
        m002 = st.number_input("Monedas 0,02€", min_value=0, step=1, key=f"{user_id}_m002")
        m001 = st.number_input("Monedas 0,01€", min_value=0, step=1, key=f"{user_id}_m001")

    total_billetes = (b100*100) + (b50*50) + (b20*20) + (b10*10) + (b5*5)
    total_monedas = (m200*2.0) + (m100*1.0) + (m050*0.5) + (m020*0.2) + (m010*0.1) + (m005*0.05) + (m002*0.02) + (m001*0.01)
    total_efectivo_contado = total_billetes + total_monedas

    total_teorico = total_cobros - total_gastos
    diferencia = total_efectivo_contado - total_teorico

    st.divider()
    st.write(f"**Total Billetes:** {total_billetes:.2f} € | **Total Monedas:** {total_monedas:.2f} €")
    st.metric("💰 EFECTIVO FÍSICO CONTADO", f"{total_efectivo_contado:.2f} €")

    if total_efectivo_contado > 0:
        if abs(diferencia) < 0.01:
            st.success("✅ **LA CAJA CUADRA PERFECTAMENTE**")
        elif diferencia > 0:
            st.warning(f"⚠️ **SOBRANTE:** +{diferencia:.2f} € respecto al teórico ({total_teorico:.2f} €)")
        else:
            st.error(f"❌ **FALTANTE:** {diferencia:.2f} € respecto al teórico ({total_teorico:.2f} €)")

    st.divider()
    st.write("### 📝 Observaciones y Guardado de Arqueo")
    
    key_obs_name = f"{user_id}_observaciones"
    obs_input = st.text_area(
        "Añade observaciones para este cierre (opcional):",
        value=st.session_state.get(key_obs_name, ""),
        placeholder="Ej: Se dejan 50€ en monedas para cambio en el cajetín / Sobrante por propina..."
    )

    if st.button("💾 Guardar Arqueo y Observaciones", use_container_width=True):
        st.session_state[key_obs_name] = obs_input.strip()
        datos_arqueo = {
            "b100": b100, "b50": b50, "b20": b20, "b10": b10, "b5": b5,
            "m200": m200, "m100": m100, "m050": m050, "m020": m020,
            "m010": m010, "m005": m005, "m002": m002, "m001": m001
        }
        guardar_arqueo_bd(user_id, datos_arqueo, obs_input.strip())
        st.success("✅ Arqueo y observaciones guardados permanentemente en la nube.")

# ==========================================
# PESTAÑA 4: INFORME PDF Y GENERACIÓN TICKET
# ==========================================
with tab_pdf:
    st.subheader("📄 Generar Hoja de Cierre / Ticket")
    
    st.info(f"**Comercial:** {user_nombre}", icon="👤")
    
    observaciones = st.session_state.get(f"{user_id}_observaciones", "")
    if observaciones:
        st.info(f"📌 **Observaciones de la caja:** *{observaciones}*")

    desglose_efectivo = {
        "b100": (b100, b100 * 100),
        "b50":  (b50,  b50 * 50),
        "b20":  (b20,  b20 * 20),
        "b10":  (b10,  b10 * 10),
        "b5":   (b5,   b5 * 5),
        "m200": (m200, m200 * 2.0),
        "m100": (m100, m100 * 1.0),
        "m050": (m050, m050 * 0.5),
        "m020": (m020, m020 * 0.2),
        "m010": (m010, m010 * 0.1),
        "m005": (m005, m005 * 0.05),
        "m002": (m002, m002 * 0.02),
        "m001": (m001, m001 * 0.01)
    }

    if not df_cobros.empty:
        # Opción 1: Generar PDF para Ticketera Datecs
        pdf_ticket_bytes = generar_pdf_ticket_termico(
            df_cobros, df_gastos, total_cobros, total_gastos, 
            total_billetes, total_monedas, total_efectivo_contado, diferencia,
            user_nombre, desglose_efectivo, observaciones
        )
        st.download_button(
            label="🖨️ Imprimir Ticket Cierre (Para Datecs DPP-450)",
            data=pdf_ticket_bytes,
            file_name=f"Ticket_Datecs_{user_id}_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
            mime="application/pdf",
            use_container_width=True
        )

        st.write("---")

        # Opción 2: Generar PDF A4 estándar
        pdf_a4_bytes = generar_pdf_a4(
            df_cobros, df_gastos, total_cobros, total_gastos, 
            total_billetes, total_monedas, total_efectivo_contado, diferencia,
            user_nombre, desglose_efectivo, observaciones
        )
        st.download_button(
            label="📄 Descargar Hoja Cierre A4 (Para Email / Oficina)",
            data=pdf_a4_bytes,
            file_name=f"Cierre_Caja_A4_{user_id}_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
            mime="application/pdf",
            use_container_width=True
        )

        st.divider()
        st.write("### 🔴 Finalizar Cierre y Reiniciar Caja")
        st.caption("Guarda este resumen en tu historial permanente y vacía la caja activa para empezar el siguiente turno.")
        
        with st.expander("⚠️ Confirmar Cierre Definitivo"):
            st.warning(f"Se guardará el resumen de {total_cobros:.2f} € en tu historial y la caja en curso pasará a cero.")
            if st.button("🔴 Confirmar y Cerrar Caja", use_container_width=True):
                cerrar_y_guardar_caja(user_id, total_cobros, total_gastos, total_efectivo_contado, diferencia, observaciones, desglose_efectivo)
                for d in denominaciones:
                    st.session_state[f"{user_id}_{d}"] = 0
                st.session_state[f"{user_id}_observaciones"] = ""
                st.session_state.edit_id = None
                st.success("✅ Caja cerrada y guardada en el historial correctamente.")
                st.rerun()
    else:
        st.caption("Registra al menos una venta para poder generar la hoja e iniciar el cierre.")

# ==========================================
# PESTAÑA 5: HISTORIAL DE CIERRES
# ==========================================
with tab_historial:
    st.subheader("📜 Historial de Cierres Guardados")
    st.caption("Consulta los resúmenes de tus cajas cerradas anteriormente y vuelve a imprimirlos si lo necesitas.")

    historial = obtener_historial_cierres(user_id)
    if historial:
        for c in historial:
            with st.expander(f"🗓️ Cierre del {c['fecha_cierre']} ({c['hora_cierre']}) — Ventas: {c['total_ventas']:.2f} €"):
                st.write(f"**Fecha y Hora:** {c['fecha_cierre']} a las {c['hora_cierre']}")
                st.write(f"**Total Ventas:** {c['total_ventas']:.2f} € | **Total Gastos:** {c['total_gastos']:.2f} €")
                st.write(f"**Efectivo Contado:** {c['total_efectivo']:.2f} €")
                
                dif_val = float(c['diferencia'])
                if abs(dif_val) < 0.01:
                    st.success("✅ Caja cuadrada (Diferencia: 0.00 €)")
                elif dif_val > 0:
                    st.warning(f"⚠️ Sobrante: +{dif_val:.2f} €")
                else:
                    st.error(f"❌ Faltante: {dif_val:.2f} €")

                if c.get("observaciones"):
                    st.info(f"**Observaciones:** {c['observaciones']}")

                # Recuperar desglose antiguo guardado
                desglose_hist = {
                    "b100": (int(c.get("b100") or 0), int(c.get("b100") or 0) * 100),
                    "b50":  (int(c.get("b50") or 0),  int(c.get("b50") or 0) * 50),
                    "b20":  (int(c.get("b20") or 0),  int(c.get("b20") or 0) * 20),
                    "b10":  (int(c.get("b10") or 0),  int(c.get("b10") or 0) * 10),
                    "b5":   (int(c.get("b5") or 0),   int(c.get("b5") or 0) * 5),
                    "m200": (int(c.get("m200") or 0), int(c.get("m200") or 0) * 2.0),
                    "m100": (int(c.get("m100") or 0), int(c.get("m100") or 0) * 1.0),
                    "m050": (int(c.get("m050") or 0), int(c.get("m050") or 0) * 0.5),
                    "m020": (int(c.get("m020") or 0), int(c.get("m020") or 0) * 0.2),
                    "m010": (int(c.get("m010") or 0), int(c.get("m010") or 0) * 0.1),
                    "m005": (int(c.get("m005") or 0), int(c.get("m005") or 0) * 0.05),
                    "m002": (int(c.get("m002") or 0), int(c.get("m002") or 0) * 0.02),
                    "m001": (int(c.get("m001") or 0), int(c.get("m001") or 0) * 0.01)
                }

                # RE-IMPRESIÓN DE CIERRES ANTERIORES CON DESGLOSE COMPLETO
                st.write("---")
                st.write("**Re-imprimir este cierre:**")
                
                fecha_custom = f"{c['fecha_cierre']} a las {c['hora_cierre']}"
                
                pdf_hist_ticket = generar_pdf_ticket_termico(
                    cobros_df=None, gastos_df=None, 
                    t_cobros=float(c['total_ventas']), t_gastos=float(c['total_gastos']), 
                    t_billetes=0, t_monedas=0, t_fisico=float(c['total_efectivo']), 
                    dif=dif_val, persona=user_nombre, desglose=desglose_hist, 
                    obs=c.get("observaciones", ""), fecha_h_custom=fecha_custom
                )
                
                st.download_button(
                    label=f"🖨️ Re-imprimir Ticket Datecs (#{c['id']})",
                    data=pdf_hist_ticket,
                    file_name=f"Ticket_Historial_{c['id']}.pdf",
                    mime="application/pdf",
                    key=f"hist_tick_{c['id']}",
                    use_container_width=True
                )
    else:
        st.info("Aún no has guardado ningún cierre de caja en el historial.")
