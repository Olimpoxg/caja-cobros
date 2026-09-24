import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
import io
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

# --- CONFIGURACIÓN DE USUARIOS Y PINS ---
USUARIOS = {
    "6666": {"id": "usr1", "nombre": "Mikel"},
    "8888": {"id": "usr2", "nombre": "Javier"}
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

# --- BASE DE DATOS LOCAL (SQLite Multiusuario) ---
DB_NAME = "caja_diaria.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS cobros (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id TEXT,
            fecha TEXT,
            hora TEXT,
            cliente TEXT,
            albaran TEXT,
            importe REAL
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS gastos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id TEXT,
            fecha TEXT,
            hora TEXT,
            concepto TEXT,
            importe REAL
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id TEXT,
            nombre TEXT,
            UNIQUE(usuario_id, nombre)
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# --- FUNCIONES DE BASE DE DATOS FILTRADAS POR USUARIO ---
def obtener_cobros_hoy(fecha, u_id):
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql_query("SELECT * FROM cobros WHERE fecha = ? AND usuario_id = ?", conn, params=(fecha, u_id))
    conn.close()
    return df

def guardar_cliente_habitual(nombre_cliente, u_id):
    if nombre_cliente and nombre_cliente.strip():
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("INSERT OR IGNORE INTO clientes (usuario_id, nombre) VALUES (?, ?)", (u_id, nombre_cliente.strip()))
        conn.commit()
        conn.close()

def obtener_todos_los_clientes(u_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT id, nombre FROM clientes WHERE usuario_id = ? ORDER BY nombre ASC", (u_id,))
    clientes = c.fetchall()
    conn.close()
    return clientes

def eliminar_cliente_habitual(id_cliente, u_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("DELETE FROM clientes WHERE id = ? AND usuario_id = ?", (id_cliente, u_id))
    conn.commit()
    conn.close()

def agregar_cobro(fecha, hora, cliente, albaran, importe, u_id):
    guardar_cliente_habitual(cliente, u_id)
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("INSERT INTO cobros (usuario_id, fecha, hora, cliente, albaran, importe) VALUES (?, ?, ?, ?, ?, ?)",
              (u_id, fecha, hora, cliente, albaran, importe))
    conn.commit()
    conn.close()

def actualizar_cobro(id_cobro, cliente, albaran, importe, u_id):
    guardar_cliente_habitual(cliente, u_id)
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("UPDATE cobros SET cliente = ?, albaran = ?, importe = ? WHERE id = ? AND usuario_id = ?",
              (cliente, albaran, importe, id_cobro, u_id))
    conn.commit()
    conn.close()

def eliminar_cobro(id_cobro, u_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("DELETE FROM cobros WHERE id = ? AND usuario_id = ?", (id_cobro, u_id))
    conn.commit()
    conn.close()

def obtener_gastos_hoy(fecha, u_id):
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql_query("SELECT * FROM gastos WHERE fecha = ? AND usuario_id = ?", conn, params=(fecha, u_id))
    conn.close()
    return df

def agregar_gasto(fecha, hora, concepto, importe, u_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("INSERT INTO gastos (usuario_id, fecha, hora, concepto, importe) VALUES (?, ?, ?, ?, ?)",
              (u_id, fecha, hora, concepto, importe))
    conn.commit()
    conn.close()

def eliminar_gasto(id_gasto, u_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("DELETE FROM gastos WHERE id = ? AND usuario_id = ?", (id_gasto, u_id))
    conn.commit()
    conn.close()

def vaciar_caja_del_dia(u_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("DELETE FROM cobros WHERE usuario_id = ?", (u_id,))
    c.execute("DELETE FROM gastos WHERE usuario_id = ?", (u_id,))
    conn.commit()
    conn.close()

# --- ESTADO Y VARIABLES DE SESIÓN ---
fecha_hoy = datetime.now().strftime("%Y-%m-%d")
fecha_mostrar = datetime.now().strftime("%d/%m/%Y")

if "edit_id" not in st.session_state:
    st.session_state.edit_id = None

denominaciones = ["b100", "b50", "b20", "b10", "b5", "m200", "m100", "m050", "m020", "m010", "m005", "m002", "m001"]
for d in denominaciones:
    key_d = f"{user_id}_{d}"
    if key_d not in st.session_state:
        st.session_state[key_d] = 0

# Cabecera principal con indicador de usuario activo y botón de salir
col_tit, col_logout = st.columns([3, 1])
with col_tit:
    st.title("☕ Venta Café — Caja Diaria")
    st.caption(f"📅 Fecha: {fecha_mostrar} | 👤 Usuario: **{user_nombre}**")
with col_logout:
    if st.button("🔒 Salir"):
        st.session_state.autenticado = False
        st.session_state.usuario_actual = None
        st.rerun()

df_cobros = obtener_cobros_hoy(fecha_hoy, user_id)
df_gastos = obtener_gastos_hoy(fecha_hoy, user_id)
lista_clientes = obtener_todos_los_clientes(user_id)
nombres_clientes = [c[1] for c in lista_clientes]

# --- PESTAÑAS DE NAVEGACIÓN ---
tab_cobros, tab_gastos, tab_arqueo, tab_pdf = st.tabs(["💰 Cobros", "💸 Gastos", "🧮 Arqueo Billetes", "📄 PDF Cierre"])

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
            if es_edicion:
                actualizar_cobro(st.session_state.edit_id, cliente, albaran, importe, user_id)
                st.session_state.edit_id = None
                st.success("✅ Cobro actualizado.")
            else:
                agregar_cobro(fecha_hoy, hora_act, cliente, albaran, importe, user_id)
                st.success("✅ Cobro registrado.")
            st.rerun()

    st.divider()
    total_cobros = df_cobros["importe"].sum() if not df_cobros.empty else 0.0
    st.metric("💵 TOTAL VENTAS CAFÉ", f"{total_cobros:.2f} €")

    if not df_cobros.empty:
        st.write("### Listado de Cobros del Día")
        for _, row in df_cobros.iterrows():
            with st.expander(f"📌 #{row['albaran'] or row['id']} | {row['cliente']} — {row['importe']:.2f} € ({row['hora']})"):
                st.write(f"**Cliente:** {row['cliente']}")
                st.write(f"**Albarán:** {row['albaran'] if row['albaran'] else 'N/A'}")
                st.write(f"**Importe:** {row['importe']:.2f} €")
                st.write(f"**Hora:** {row['hora']}")
                
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

    # --- GESTIÓN DE CLIENTES DE ESTE USUARIO ---
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

    # --- BOTÓN PARA PONER A CERO LA CAJA ---
    st.write("### 🔄 Reiniciar Mi Caja")
    st.caption("Pone a cero tus cobros, gastos y tu arqueo. **No afecta a los datos de otros compañeros**.")
    
    with st.expander("⚠️ Abrir opciones para poner a cero mi caja"):
        st.warning(f"¿Estás seguro de que deseas vaciar la caja actual de {user_nombre}?")
        if st.button("🔴 Confirmar y Poner Mi Caja a Cero", use_container_width=True):
            vaciar_caja_del_dia(user_id)
            for d in denominaciones:
                st.session_state[f"{user_id}_{d}"] = 0
            st.session_state.edit_id = None
            st.success("✅ Tu caja ha sido puesta a cero correctamente.")
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
            agregar_gasto(fecha_hoy, datetime.now().strftime("%H:%M"), concepto_gasto.strip(), importe_gasto, user_id)
            st.success("✅ Gasto registrado.")
            st.rerun()

    st.divider()
    total_gastos = df_gastos["importe"].sum() if not df_gastos.empty else 0.0
    st.metric("📉 TOTAL GASTOS", f"{total_gastos:.2f} €")

    if not df_gastos.empty:
        for _, row in df_gastos.iterrows():
            col_g1, col_g2 = st.columns([3, 1])
            with col_g1:
                st.write(f"• **{row['concepto']}**: {row['importe']:.2f} € ({row['hora']})")
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

# ==========================================
# PESTAÑA 4: INFORME PDF COMPLETO
# ==========================================
with tab_pdf:
    st.subheader("📄 Generar Hoja de Cierre")
    
    st.info(f"<b>Entregado por:</b> {user_nombre}", icon="👤")

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

    def generar_pdf_completo(cobros_df, gastos_df, t_cobros, t_gastos, t_billetes, t_monedas, t_fisico, persona, desglose):
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
        story = []
        styles = getSampleStyleSheet()

        title_style = ParagraphStyle('DocTitle', parent=styles['Title'], fontSize=15, leading=18, textColor=colors.HexColor('#1E293B'), alignment=0)
        sub_style = ParagraphStyle('DocSub', parent=styles['Normal'], fontSize=9, textColor=colors.HexColor('#475569'))
        cell_style = ParagraphStyle('Cell', parent=styles['Normal'], fontSize=8, leading=10)
        cell_bold = ParagraphStyle('CellB', parent=styles['Normal'], fontSize=8, leading=10, fontName='Helvetica-Bold')

        story.append(Paragraph("<b>VENTA CAFÉ — HOJA DE CIERRE DE CAJA</b>", title_style))
        story.append(Spacer(1, 4))
        story.append(Paragraph(f"<b>Fecha:</b> {fecha_mostrar} &nbsp;&nbsp;|&nbsp;&nbsp; <b>Entregado por:</b> {persona}", sub_style))
        story.append(Spacer(1, 10))

        story.append(Paragraph("<b>VENTAS CAFÉ (ALBARANES)</b>", cell_bold))
        story.append(Spacer(1, 4))
        
        data_c = [[Paragraph("<b>Nº Albarán</b>", cell_bold), Paragraph("<b>Cliente</b>", cell_bold), Paragraph("<b>Hora</b>", cell_bold), Paragraph("<b>Importe (€)</b>", cell_bold)]]
        
        if not cobros_df.empty:
            for _, r in cobros_df.iterrows():
                data_c.append([
                    Paragraph(str(r['albaran']) if r['albaran'] else "-", cell_style),
                    Paragraph(str(r['cliente']), cell_style),
                    Paragraph(str(r['hora']), cell_style),
                    Paragraph(f"{float(r['importe']):.2f} €", cell_bold)
                ])
        data_c.append([Paragraph("<b>TOTAL VENTAS</b>", cell_bold), "", "", Paragraph(f"<b>{t_cobros:.2f} €</b>", cell_bold)])

        t_cobros_table = Table(data_c, colWidths=[90, 250, 70, 90])
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

        if not gastos_df.empty:
            story.append(Paragraph("<b>GASTOS / SALIDAS DE CAJA</b>", cell_bold))
            story.append(Spacer(1, 4))
            data_g = [[Paragraph("<b>Concepto</b>", cell_bold), Paragraph("<b>Hora</b>", cell_bold), Paragraph("<b>Importe (€)</b>", cell_bold)]]
            for _, r in gastos_df.iterrows():
                data_g.append([Paragraph(str(r['concepto']), cell_style), Paragraph(str(r['hora']), cell_style), Paragraph(f"{float(r['importe']):.2f} €", cell_bold)])
            data_g.append([Paragraph("<b>TOTAL GASTOS</b>", cell_bold), "", Paragraph(f"<b>{t_gastos:.2f} €</b>", cell_bold)])

            t_gastos_table = Table(data_g, colWidths=[340, 70, 90])
            t_gastos_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#FEE2E2')),
                ('GRID', (0, 0), (-1, -2), 0.5, colors.HexColor('#FCA5A5')),
                ('SPAN', (0, -1), (1, -1)),
                ('ALIGN', (-1, 0), (-1, -1), 'RIGHT'),
                ('PADDING', (0, 0), (-1, -1), 4),
            ]))
            story.append(t_gastos_table)
            story.append(Spacer(1, 10))

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
        data_a = [
            [Paragraph("<b>Total Ventas Albaranes:</b>", cell_style), Paragraph(f"{t_cobros:.2f} €", cell_style), Paragraph("<b>Total Billetes Contados:</b>", cell_style), Paragraph(f"{t_billetes:.2f} €", cell_style)],
            [Paragraph("<b>(-) Gastos en Metálico:</b>", cell_style), Paragraph(f"-{t_gastos:.2f} €", cell_style), Paragraph("<b>Total Monedas Contadas:</b>", cell_style), Paragraph(f"{t_monedas:.2f} €", cell_style)],
            [Paragraph("<b>TOTAL TEÓRICO CAJA:</b>", cell_bold), Paragraph(f"<b>{t_teorico:.2f} €</b>", cell_bold), Paragraph("<b>TOTAL EFECTIVO CONTADO:</b>", cell_bold), Paragraph(f"<b>{t_fisico:.2f} €</b>", cell_bold)]
        ]

        t_arqueo_table = Table(data_a, colWidths=[130, 120, 130, 120])
        t_arqueo_table.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#F8FAFC')),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('ALIGN', (3, 0), (3, -1), 'RIGHT'),
            ('PADDING', (0, 0), (-1, -1), 4),
        ]))
        story.append(t_arqueo_table)

        doc.build(story)
        buffer.seek(0)
        return buffer

    if not df_cobros.empty:
        pdf_bytes = generar_pdf_completo(
            df_cobros, df_gastos, total_cobros, total_gastos, 
            total_billetes, total_monedas, total_efectivo_contado, 
            user_nombre, desglose_efectivo
        )
        st.download_button(
            label="📥 Descargar Hoja de Cierre en PDF",
            data=pdf_bytes,
            file_name=f"Cierre_Caja_{user_id}_{fecha_hoy}.pdf",
            mime="application/pdf",
            use_container_width=True
        )
    else:
        st.caption("Registra al menos una venta para poder descargar la hoja en PDF.")
