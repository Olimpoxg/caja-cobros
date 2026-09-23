import streamlit as st
import pandas as pd
from datetime import datetime
import io
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

# Configuración de página optimizada para móvil
st.set_page_config(
    page_title="Caja Diaria - Cobros",
    page_icon="💰",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# Inicializar variables de sesión (Persistencia durante la sesión actual)
if "cobros" not in st.session_state:
    st.session_state.cobros = []

if "edit_index" not in st.session_state:
    st.session_state.edit_index = None

# Título y Encabezado
st.title("💰 Caja Diaria de Cobros")
st.caption(f"Fecha actual: {datetime.now().strftime('%d/%m/%Y')}")

# --- SECCIÓN 1: FORMULARIO DE ENTRADA / EDICIÓN ---
st.subheader("📝 Registrar Cobro")

# Comprobar si estamos en modo edición
es_edicion = st.session_state.edit_index is not None
val_cliente = ""
val_importe = 0.0
val_albaran = ""

if es_edicion:
    idx = st.session_state.edit_index
    cobro_editar = st.session_state.cobros[idx]
    val_cliente = cobro_editar["cliente"]
    val_importe = cobro_editar["importe"]
    val_albaran = cobro_editar.get("albaran", "")
    st.info(f"✏️ Editando cobro #{idx + 1}")

with st.form(key="form_cobro", clear_on_submit=not es_edicion):
    cliente = st.text_input("Nombre del Cliente", value=val_cliente, placeholder="Ej: Bar Plaza / Juan Pérez")
    albaran = st.text_input("Nº de Albarán / Factura (Opcional)", value=val_albaran, placeholder="Ej: ALB-2026-089")
    importe = st.number_input("Importe en Metálico (€)", min_value=0.0, step=0.5, value=val_importe, format="%.2f")
    
    col_sub1, col_sub2 = st.columns(2)
    with col_sub1:
        btn_guardar = st.form_submit_button("💾 Guardar Cobro" if not es_edicion else "🔄 Actualizar", use_container_width=True)
    with col_sub2:
        if es_edicion:
            btn_cancelar = st.form_submit_button("❌ Cancelar", use_container_width=True)
        else:
            btn_cancelar = False

if btn_cancelar and es_edicion:
    st.session_state.edit_index = None
    st.rerun()

if btn_guardar:
    if not cliente.strip():
        st.error("Por favor, introduce el nombre del cliente.")
    elif importe <= 0:
        st.error("El importe debe ser mayor que 0.00 €.")
    else:
        hora_actual = datetime.now().strftime("%H:%M")
        if es_edicion:
            st.session_state.cobros[st.session_state.edit_index] = {
                "cliente": cliente.strip(),
                "albaran": albaran.strip(),
                "importe": float(importe),
                "hora": st.session_state.cobros[st.session_state.edit_index]["hora"]
            }
            st.session_state.edit_index = None
            st.success("✅ Cobro actualizado correctamente.")
        else:
            st.session_state.cobros.append({
                "cliente": cliente.strip(),
                "albaran": albaran.strip(),
                "importe": float(importe),
                "hora": hora_actual
            })
            st.success("✅ Cobro registrado con éxito.")
        st.rerun()

# --- SECCIÓN 2: RESUMEN Y LISTADO DE COBROS ---
st.divider()

total_efectivo = sum(c["importe"] for c in st.session_state.cobros)

# Destacado con el Total
st.metric(label="💵 TOTAL METÁLICO ACUMULADO", value=f"{total_efectivo:.2f} €")

if len(st.session_state.cobros) > 0:
    st.subheader("📋 Detalle de Cobros del Día")
    
    for i, c in enumerate(st.session_state.cobros):
        with st.expander(f"📌 #{i+1} | {c['cliente']} — {c['importe']:.2f} € ({c['hora']})"):
            st.write(f"**Cliente:** {c['cliente']}")
            st.write(f"**Albarán:** {c['albaran'] if c['albaran'] else 'N/A'}")
            st.write(f"**Importe:** {c['importe']:.2f} €")
            st.write(f"**Hora:** {c['hora']}")
            
            col_ed, col_el = st.columns(2)
            with col_ed:
                if st.button("✏️ Editar", key=f"edit_{i}", use_container_width=True):
                    st.session_state.edit_index = i
                    st.rerun()
            with col_el:
                if st.button("🗑️ Eliminar", key=f"del_{i}", use_container_width=True):
                    st.session_state.cobros.pop(i)
                    if st.session_state.edit_index == i:
                        st.session_state.edit_index = None
                    st.rerun()

    # Opción para vaciar caja
    if st.button("🚨 Borrar todos los cobros", type="secondary"):
        st.session_state.cobros = []
        st.session_state.edit_index = None
        st.rerun()
else:
    st.info("Aún no se han registrado cobros hoy.")

# --- SECCIÓN 3: GENERACIÓN Y EXPORTACIÓN A PDF ---
st.divider()
st.subheader("📄 Generar Informe de Cierre (PDF)")

def generar_pdf(cobros, total):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36
    )
    story = []
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Title'],
        fontSize=20,
        leading=24,
        textColor=colors.HexColor('#1E293B'),
        alignment=0,
        spaceAfter=6
    )
    
    subtitle_style = ParagraphStyle(
        'DocSubtitle',
        parent=styles['Normal'],
        fontSize=10,
        textColor=colors.HexColor('#64748B'),
        spaceAfter=15
    )

    cell_style = ParagraphStyle(
        'Cell',
        parent=styles['Normal'],
        fontSize=9,
        leading=11,
        textColor=colors.HexColor('#334155')
    )

    cell_bold_style = ParagraphStyle(
        'CellBold',
        parent=styles['Normal'],
        fontSize=9,
        leading=11,
        fontName='Helvetica-Bold',
        textColor=colors.HexColor('#0F172A')
    )

    # Encabezado
    fecha_str = datetime.now().strftime('%d/%m/%Y - %H:%M')
    story.append(Paragraph("Informe de Cierre de Caja en Metálico", title_style))
    story.append(Paragraph(f"Fecha de emisión: {fecha_str}", subtitle_style))
    story.append(Spacer(1, 10))

    # Tabla de cobros
    data = [[
        Paragraph("<b>Nº</b>", cell_bold_style),
        Paragraph("<b>Hora</b>", cell_bold_style),
        Paragraph("<b>Cliente</b>", cell_bold_style),
        Paragraph("<b>Albarán / Doc.</b>", cell_bold_style),
        Paragraph("<b>Importe (€)</b>", cell_bold_style)
    ]]

    for idx, c in enumerate(cobros, 1):
        data.append([
            Paragraph(str(idx), cell_style),
            Paragraph(c['hora'], cell_style),
            Paragraph(c['cliente'], cell_style),
            Paragraph(c['albaran'] if c['albaran'] else "-", cell_style),
            Paragraph(f"{c['importe']:.2f} €", cell_bold_style)
        ])

    # Fila de Total
    data.append([
        Paragraph("<b>TOTAL RECAUDADO</b>", cell_bold_style),
        "", "", "",
        Paragraph(f"<b>{total:.2f} €</b>", cell_bold_style)
    ])

    table = Table(data, colWidths=[30, 50, 220, 120, 100])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#F1F5F9')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#0F172A')),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('ALIGN', (-1, 0), (-1, -1), 'RIGHT'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('GRID', (0, 0), (-1, -2), 0.5, colors.HexColor('#E2E8F0')),
        ('SPAN', (0, -1), (3, -1)),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#E2E8F0')),
        ('LINEABOVE', (0, -1), (-1, -1), 1.5, colors.HexColor('#0F172A')),
    ]))

    story.append(table)
    doc.build(story)
    buffer.seek(0)
    return buffer

if len(st.session_state.cobros) > 0:
    pdf_data = generar_pdf(st.session_state.cobros, total_efectivo)
    nombre_archivo_pdf = f"Cierre_Caja_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
    
    st.download_button(
        label="📥 Descargar Reporte PDF",
        data=pdf_data,
        file_name=nombre_archivo_pdf,
        mime="application/pdf",
        use_container_width=True
    )
else:
    st.caption("Registra al menos un cobro para habilitar la descarga del PDF.")