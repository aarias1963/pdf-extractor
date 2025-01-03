import streamlit as st
import pdfplumber
import re
import io
import sys
import gc
import logging
import tempfile
import os
from contextlib import contextmanager

# Configuración de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Constantes
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB
CHUNK_SIZE = 5  # Reducido a 5 páginas por chunk
MAX_TEXT_LENGTH = 1_000_000  # Límite de caracteres para el texto completo

def init_session_state():
    """
    Inicializa las variables de estado de la sesión
    """
    if 'processed_file_hash' not in st.session_state:
        st.session_state.processed_file_hash = None
    if 'full_text' not in st.session_state:
        st.session_state.full_text = None
    if 'total_pages' not in st.session_state:
        st.session_state.total_pages = None

@contextmanager
def temp_file_handler(uploaded_file):
    """
    Maneja el archivo subido creando un archivo temporal
    """
    temp_dir = tempfile.mkdtemp()
    temp_path = os.path.join(temp_dir, "temp.pdf")
    try:
        with open(temp_path, 'wb') as f:
            f.write(uploaded_file.getvalue())
        yield temp_path
    finally:
        try:
            os.remove(temp_path)
            os.rmdir(temp_dir)
        except Exception as e:
            logger.error(f"Error limpiando archivos temporales: {e}")

def check_file_size(file):
    """
    Verifica si el archivo está dentro del límite de tamaño permitido
    """
    try:
        file_size = sys.getsizeof(file.getvalue())
        logger.info(f"Tamaño del archivo: {file_size/1024/1024:.2f}MB")
        if file_size > MAX_FILE_SIZE:
            raise ValueError(f"El archivo es demasiado grande. El tamaño máximo permitido es {MAX_FILE_SIZE/1024/1024:.0f}MB")
    except Exception as e:
        logger.error(f"Error al verificar tamaño del archivo: {e}")
        raise

def process_page(page, page_num):
    """
    Procesa una única página del PDF
    """
    try:
        if page is None:
            logger.warning(f"Página {page_num} es None")
            return f"[Error en página {page_num}: Página vacía]"

        words = page.extract_words(
            x_tolerance=3,
            y_tolerance=3,
            keep_blank_chars=False,
            use_text_flow=True
        )
        
        if not words:
            logger.warning(f"No se encontraron palabras en la página {page_num}")
            return f"[Página {page_num}: Sin contenido]"

        sorted_words = sorted(words, key=lambda x: (x['top'], x['x0']))
        lines = []
        current_line = []
        current_y = None
        
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
        
        page_text = ""
        for line in lines:
            line_text = ' '.join(word['text'] for word in sorted(line, key=lambda x: x['x0']))
            page_text += line_text + '\n'
        
        return post_process_text(page_text)
    except Exception as e:
        logger.error(f"Error procesando página {page_num}: {e}")
        return f"[Error en página {page_num}: {str(e)}]"

def extract_text_from_pdf_chunk(pdf_path, start_page, end_page):
    """
    Extrae texto de un rango específico de páginas del PDF
    """
    chunk_text = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            if not pdf or not pdf.pages:
                raise ValueError("PDF vacío o inválido")

            for page_num in range(start_page, min(end_page, len(pdf.pages))):
                logger.info(f"Procesando página {page_num + 1}")
                page = pdf.pages[page_num] if page_num < len(pdf.pages) else None
                page_text = process_page(page, page_num + 1)
                chunk_text.append(page_text)
                
                # Limpieza de memoria
                del page
                gc.collect()
                
    except Exception as e:
        logger.error(f"Error en chunk {start_page}-{end_page}: {e}")
        raise
        
    return chunk_text

def get_total_pages(pdf_path):
    """
    Obtiene el número total de páginas del PDF
    """
    try:
        with pdfplumber.open(pdf_path) as pdf:
            if pdf is None or not hasattr(pdf, 'pages'):
                raise ValueError("PDF inválido")
            return len(pdf.pages)
    except Exception as e:
        logger.error(f"Error al obtener total de páginas: {e}")
        raise ValueError("No se pudo determinar el número de páginas del PDF")

def extract_text_from_pdf(uploaded_file):
    """
    Extrae texto de un PDF procesándolo en chunks
    """
    all_pages_text = []
    total_text_length = 0
    
    with temp_file_handler(uploaded_file) as temp_path:
        try:
            total_pages = get_total_pages(temp_path)
            st.session_state.total_pages = total_pages
            logger.info(f"Total de páginas: {total_pages}")
            
            progress_bar = st.progress(0)
            
            try:
                for start_idx in range(0, total_pages, CHUNK_SIZE):
                    end_idx = min(start_idx + CHUNK_SIZE, total_pages)
                    st.write(f"Procesando páginas {start_idx + 1} a {end_idx} de {total_pages}...")
                    
                    chunk_text = extract_text_from_pdf_chunk(temp_path, start_idx, end_idx)
                    
                    # Verificar límite de texto
                    chunk_length = sum(len(text) for text in chunk_text if text)
                    if total_text_length + chunk_length > MAX_TEXT_LENGTH:
                        raise ValueError("El texto extraído excede el límite permitido")
                    
                    total_text_length += chunk_length
                    all_pages_text.extend(chunk_text)
                    
                    progress_bar.progress((end_idx) / total_pages)
                    gc.collect()
                    
            finally:
                progress_bar.empty()
                
        except Exception as e:
            logger.error(f"Error durante la extracción: {e}")
            raise
            
    return all_pages_text

def post_process_text(text):
    """
    Limpia el texto manteniendo el formato
    """
    if text is None:
        return ""
    try:
        text = re.sub(r'[^\w\s.,!?;:()\-\'\"áéíóúÁÉÍÓÚñÑ]', '', text)
        text = re.sub(r'\s+([.,!?;:])', r'\1', text)
        text = re.sub(r'\.(?!\s)', '. ', text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()
    except Exception as e:
        logger.error(f"Error en post-procesamiento: {e}")
        return text

def process_and_show_pdf(uploaded_file):
    """
    Procesa el PDF y muestra los resultados
    """
    try:
        file_hash = hash(uploaded_file.getvalue())
        
        if 'processed_file_hash' not in st.session_state or st.session_state.processed_file_hash != file_hash:
            status = st.empty()
            progress_placeholder = st.empty()
            
            try:
                status.write("Procesando PDF...")
                pages_text = extract_text_from_pdf(uploaded_file)
                
                # Preparar texto por partes
                if pages_text:
                    output_chunks = []
                    for i, page_text in enumerate(pages_text, 1):
                        if page_text:  # Verificar que el texto de la página no sea None
                            output_chunks.append(f'[Página {i}]\n\n{page_text}\n\n{"="*50}\n\n')
                    
                    st.session_state.full_text = ''.join(output_chunks)
                    st.session_state.processed_file_hash = file_hash
                    status.write("¡Procesamiento completado!")
                else:
                    raise ValueError("No se pudo extraer texto del PDF")
                
            except Exception as e:
                logger.error(f"Error durante el procesamiento: {e}")
                raise e
            finally:
                # Limpiar los placeholders temporales
                status.empty()
                progress_placeholder.empty()

def main():
    try:
        st.set_page_config(
            page_title="Extractor de Texto PDF",
            page_icon="📄",
            layout="wide"
        )
        
        # Inicializar variables de estado
        init_session_state()
        
        with st.sidebar:
            st.title("Opciones")
            if st.button("🔄 Reiniciar aplicación", use_container_width=True):
                st.session_state.clear()
                st.rerun()
        
        st.title("📄 Extractor de Texto PDF")
        st.write("Sube un archivo PDF para extraer su texto manteniendo el formato.")
        
        st.info(f"Tamaño máximo de archivo: {MAX_FILE_SIZE/1024/1024:.0f}MB")
        
        uploaded_file = st.file_uploader("Selecciona un archivo PDF", type="pdf")
        
        if uploaded_file is not None:
            try:
                check_file_size(uploaded_file)
                process_and_show_pdf(uploaded_file)
                
                # Mostrar vista previa y botón de descarga solo si hay texto procesado
                if st.session_state.full_text is not None:
                    # Mostrar vista previa
                    st.subheader("Vista previa del texto extraído:")
                    preview_text = st.session_state.full_text[:1000] + ("..." if len(st.session_state.full_text) > 1000 else "")
                    st.text_area("", value=preview_text, height=300)
                    
                    # Botón de descarga
                    st.download_button(
                        label="📥 Descargar archivo de texto",
                        data=st.session_state.full_text,
                        file_name="texto_extraido.txt",
                        mime="text/plain",
                        key="download_button"
                    )
                    
            except ValueError as ve:
                st.error(str(ve))
            except Exception as e:
                logger.error(f"Error inesperado: {e}")
                st.error("Se produjo un error al procesar el archivo. Por favor, intenta recargar la página y procesar el archivo nuevamente.")
                st.error(f"Detalles del error: {str(e)}")

    except Exception as e:
        logger.error(f"Error fatal en la aplicación: {e}")
        st.error("Error crítico en la aplicación. Por favor, recarga la página.")

if __name__ == "__main__":
    main()
