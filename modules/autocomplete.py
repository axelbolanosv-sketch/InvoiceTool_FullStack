# modules/autocomplete.py (Versión 9.0 - Dinámico)
# Módulo dedicado a generar las opciones de autocompletado.

import pandas as pd
from .json_manager import cargar_json, USER_LISTS_FILE

def get_autocomplete_options(df: pd.DataFrame) -> dict:
    """
    Genera opciones de autocompletado combinando:
    1. Listas guardadas por el usuario (JSON).
    2. Valores existentes en el DataFrame actual.
    
    Mejora v9.0:
    - Ahora itera sobre TODAS las columnas que el usuario tenga guardadas,
      no solo las "canónicas" hardcodeadas. Esto permite añadir autocompletado
      a columnas nuevas dinámicamente.
    """
    listas_de_usuario = cargar_json(USER_LISTS_FILE)
    
    autocomplete_options = {}

    # Lista base sugerida por el sistema
    columnas_target_canonicas = {
        "Vendor Name", "Status", "Assignee", 
        "Operating Unit Name", "Pay Status", "Document Type",
        "Pay group", "WEC Email Inbox", "Sender Email", 
        "Currency Code", "payment method",
        "_row_status", "_priority"
    }
    
    # UNIÓN: Las canónicas + Las que el usuario haya creado/guardado alguna vez
    todas_las_keys = columnas_target_canonicas.union(listas_de_usuario.keys())
    
    # Mapa para encontrar columnas sin importar mayúsculas/minúsculas
    df_cols_lower_map = {col.lower(): col for col in df.columns}

    for target_col_name in todas_las_keys:
        
        opciones_combinadas = set()
        
        # 1. Agregar lo que está guardado en JSON (si existe)
        lista_guardada = listas_de_usuario.get(target_col_name)
        if isinstance(lista_guardada, list):
            opciones_combinadas.update(lista_guardada)

        # 2. Agregar lo que está en el Excel actual (si la columna existe)
        df_col_name_real = df_cols_lower_map.get(target_col_name.lower())
        
        if df_col_name_real:
            # Extraer valores únicos del Excel
            valores_unicos_excel = df[df_col_name_real].astype(str).unique()
            opciones_limpias_excel = [
                val.strip() for val in valores_unicos_excel 
                if val and pd.notna(val) and val.strip() not in ["", "nan", "None"]
            ]
            opciones_combinadas.update(opciones_limpias_excel)
            
            # Usamos el nombre real del Excel como clave para el frontend
            key_name = df_col_name_real
        else:
            # Si no está en el Excel, usamos el nombre guardado
            key_name = target_col_name
        
        if opciones_combinadas:
            autocomplete_options[key_name] = sorted(list(opciones_combinadas))
             
    return autocomplete_options