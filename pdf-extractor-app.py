import streamlit as st
import pdfplumber
import re
from io import StringIO
import base64
from collections import defaultdict

def extract_text_from_pdf(pdf_file):
    """
    Extrae texto de un PDF complejo manteniendo la paginación original.
    
    Args:
        pdf_file: Archivo PDF subido a través de Streamlit
        
    Returns:
        list: Lista de strings, cada elemento corresponde al texto de una página
    """
    pages_text = []
    
    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
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
            
            pages_text.append(post_process_text(page_text))
    
    return pages_text

def post_process_text(text):
    """
    Limpia el texto manteniendo el formato.
    """
    text = re.sub(r'[^\w\s.,!?;:()\-\'\"áéíóúÁÉÍÓÚñÑ]', '', text)
    text = re.sub(r'\s+([.,!?;:])', r'\1', text)
    text = re.sub(r'\.(?!\s)', '. ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

def get_text_download_link(text, filename):
    """
    Genera un enlace de descarga para el archivo de texto.
    """
    b64 = base64.b64encode(text.encode()).decode()
    return f'<a href="data:text/plain;base64,{b64}" download="{filename}">Descargar archivo de texto</a>'

def main():
    st.title("Extractor de Texto PDF")
    st.write("Sube un archivo PDF para extraer su texto manteniendo el formato.")
    
    uploaded_file = st.file_uploader("Selecciona un archivo PDF", type="pdf")
    
    if uploaded_file is not None:
        try:
            with st.spinner('Procesando el PDF...'):
                # Extraer el texto
                pages_text = extract_text_from_pdf(uploaded_file)
                
                # Preparar el texto completo con marcadores de página
                full_text = ""
                for i, page_text in enumerate(pages_text, 1):
                    full_text += f'[Página {i}]\n\n{page_text}\n\n{"="*50}\n\n'
                
                # Mostrar vista previa
                st.subheader("Vista previa del texto extraído:")
                st.text_area("", value=full_text[:1000] + "...", height=300)
                
                # Generar enlace de descarga
                st.markdown(
                    get_text_download_link(full_text, "texto_extraido.txt"),
                    unsafe_allow_html=True
                )
                
        except Exception as e:
            st.error(f"Error al procesar el archivo: {str(e)}")
            
if __name__ == "__main__":
    main()
