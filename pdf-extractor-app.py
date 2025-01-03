import streamlit as st
import pdfplumber
import re
import io
from collections import defaultdict
import sys
import gc

# Constantes
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB
CHUNK_SIZE = 10  # Número de páginas por chunk

def check_file_size(file):
    """
    Verifica si el archivo está dentro del límite de tamaño permitido
    """
    file_size = sys.getsizeof(file.getvalue())
    if file_size > MAX_FILE_SIZE:
        raise ValueError(f"El archivo es demasiado grande. El tamaño máximo permitido es {MAX_FILE_SIZE/1024/1024:.0f}MB")

def extract_text_from_pdf_chunk(pdf, start_page, end_page):
    """
    Extrae texto de un rango específico de páginas del PDF
    """
    chunk_text = []
    
    for page_num in range(start_page, min(end_page, len(pdf.pages))):
        try:
            page = pdf.pages[page_num]
            
            # Extrae elementos de texto con coordenadas
            words = page.extract_words(
                x_tolerance=3,
                y_tolerance=3,
                keep_blank_chars=False,
                use_text_flow=True
            )
            
            # Ordena por posición vertical y horizontal
            sorted_words = sorted(words, key=lambda x: (x['top'], x['x0']))
            
            # Agrupa elementos en líneas
            current_line = []
            current_y = None
            lines = []
            
            for word in sorted_words:
                if current_y is None or abs(word['top'] - current_y) <= 3:
                    current_line.append(word)
                else:
                    if current_line:
                        lines.append(current_line)
                    current_line = [word]
                current_y = word['top']
            
            if current_line:
                lines.append(current_line)
            
            # Construye el texto de la página
            page_text = ""
            for line in lines:
                line_text = ' '.join(word['text'] for word in sorted(line, key=lambda x: x['x0']))
                page_text += line_text + '\n'
            
            chunk_text.append(post_process_text(page_text))
            
        except Exception as e:
            st.warning(f"Error al procesar la página {page_num + 1}: {str(e)}")
            chunk_text.append(f"[Error en página {page_num + 1}]")
            
        # Limpieza de memoria explícita
        gc.collect()
    
    return chunk_text

def extract_text_from_pdf(uploaded_file):
    """
    Extrae texto de un PDF procesándolo en chunks
    """
    pdf_bytes = uploaded_file.getvalue()
    all_pages_text = []
    
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            total_pages = len(pdf.pages)
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            # Procesar el PDF en chunks
            for start_idx in range(0, total_pages, CHUNK_SIZE):
                end_idx = min(start_idx + CHUNK_SIZE, total_pages)
                status_text.text(f"Procesando páginas {start_idx + 1} a {end_idx} de {total_pages}...")
                
                chunk_text = extract_text_from_pdf_chunk(pdf, start_idx, end_idx)
                all_pages_text.extend(chunk_text)
                
                # Actualizar progreso
                progress_bar.progress((end_idx) / total_pages)
                
                # Limpieza de memoria
                gc.collect()
            
            progress_bar.empty()
            status_text.empty()
            
    except Exception as e:
        raise Exception(f"Error al procesar el PDF: {str(e)}")
        
    return all_pages_text

def post_process_text(text):
    """
    Limpia el texto manteniendo el formato
    """
    text = re.sub(r'[^\w\s.,!?;:()\-\'\"áéíóúÁÉÍÓÚñÑ]', '', text)
    text = re.sub(r'\s+([.,!?;:])', r'\1', text)
    text = re.sub(r'\.(?!\s)', '. ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

def reset_app():
    """
    Reinicia todas las variables de estado de la aplicación
    """
    for key in list(st.session_state.keys()):
        del st.session_state[key]

def main():
    st.set_page_config(
        page_title="Extractor de Texto PDF",
        page_icon="📄",
        layout="wide"
    )
    
    with st.sidebar:
        st.title("Opciones")
        if st.button("🔄 Reiniciar aplicación", use_container_width=True):
            reset_app()
            st.rerun()
    
    st.title("📄 Extractor de Texto PDF")
    st.write("Sube un archivo PDF para extraer su texto manteniendo el formato.")
    
    # Información sobre límites
    st.info(f"Tamaño máximo de archivo: {MAX_FILE_SIZE/1024/1024:.0f}MB")
    
    uploaded_file = st.file_uploader("Selecciona un archivo PDF", type="pdf")
    
    if uploaded_file is not None:
        try:
            # Verificar tamaño del archivo
            check_file_size(uploaded_file)
            
            # Usar un contenedor para mostrar el estado del procesamiento
            with st.status("Procesando PDF...", expanded=True) as status:
                # Extraer el texto
                pages_text = extract_text_from_pdf(uploaded_file)
                
                # Preparar el texto completo con marcadores de página
                full_text = ""
                for i, page_text in enumerate(pages_text, 1):
                    full_text += f'[Página {i}]\n\n{page_text}\n\n{"="*50}\n\n'
                
                status.update(label="¡Procesamiento completado!", state="complete")
            
            # Mostrar vista previa
            st.subheader("Vista previa del texto extraído:")
            preview_text = full_text[:1000] + ("..." if len(full_text) > 1000 else "")
            st.text_area("", value=preview_text, height=300)
            
            # Botón de descarga
            st.download_button(
                label="📥 Descargar archivo de texto",
                data=full_text,
                file_name="texto_extraido.txt",
                mime="text/plain"
            )
                
        except ValueError as ve:
            st.error(str(ve))
        except Exception as e:
            st.error(f"Error al procesar el archivo: {str(e)}")
            st.error("Por favor, intenta con un archivo más pequeño o en un formato diferente.")

if __name__ == "__main__":
    main()
