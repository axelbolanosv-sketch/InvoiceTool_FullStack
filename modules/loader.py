"""
loader.py
---------
Módulo encargado de la carga, limpieza inicial y asignación de lógica base de datos.

Estándares: Google Python Style Guide.
Optimizaciones v18.0:
- Reemplazo de `.apply()` por `np.select` para asignación de prioridades (Mejora de rendimiento O(n) a Vectorial).
"""

import pandas as pd
import numpy as np
# Importamos la función para aplicar reglas dinámicas y cargar settings.
from .priority_manager import apply_priority_rules, load_settings


def _find_pay_group_column(df: pd.DataFrame) -> str | None:
    """
    Busca heurísticamente la columna de "Pay Group" en el DataFrame.

    Args:
        df (pd.DataFrame): El DataFrame cargado.

    Returns:
        str | None: El nombre real de la columna encontrada o None si no existe.
    """
    # Lista de posibles nombres (en minúsculas) para la columna.
    possible_names = ['pay group', 'grupo de pago', 'paygroup']
    
    # Iteramos sobre las columnas del DataFrame.
    for col in df.columns:
        if str(col).lower() in possible_names:
            return col 
    return None 


def cargar_datos(ruta_archivo: str) -> tuple[pd.DataFrame, str | None]:
    """
    Carga un archivo Excel, normaliza datos y aplica lógica de negocio base.

    Proceso:
    1. Carga Excel con pandas.
    2. Limpia espacios en nombres de columnas.
    3. Calcula `_row_status` vectorizado.
    4. Aplica prioridades base (SCF/Intercompany) usando vectorización (`np.select`).
    5. Aplica reglas personalizadas (`apply_priority_rules`).

    Args:
        ruta_archivo (str): Ruta absoluta al archivo .xlsx.

    Returns:
        tuple[pd.DataFrame, str | None]: 
            - DataFrame procesado.
            - Nombre de la columna 'Pay Group' detectada.
    """
    try:
        # 1. Carga y limpieza inicial de datos.
        # dtype=str asegura que no se pierdan ceros a la izquierda en IDs.
        df = pd.read_excel(ruta_archivo, dtype=str)
        
        # Eliminamos espacios en blanco de los nombres de las columnas.
        df.columns = [col.strip() for col in df.columns]
        
        # Reemplazamos NaN con cadenas vacías para manejo uniforme de strings.
        df = df.fillna("")
        print(f"INFO: Archivo cargado correctamente con {len(df)} registros.")

        # 2. Cálculo Vectorizado de "Row Status" (Completo/Incompleto).
        # Creamos una máscara booleana donde True indica celda vacía o "0".
        blank_mask = (df == "") | (df == "0")
        # Si alguna columna en la fila (axis=1) es True, la fila es incompleta.
        incomplete_rows = blank_mask.any(axis=1)
        
        # Asignamos estado usando numpy where (mucho más rápido que apply).
        df['_row_status'] = np.where(incomplete_rows, "Incompleto", "Completo")
        
        # --- LÓGICA DE PRIORIDAD (Optimizada v18.0) ---
        
        # Inicializamos columna de razón vacía.
        df['_priority_reason'] = "" 

        # 3. Cargar configuración del usuario.
        user_settings = load_settings()
        enable_scf = user_settings.get('enable_scf_intercompany', True)
        
        # 4. Aplicar Prioridad Base.
        pay_group_col_name = _find_pay_group_column(df)
        
        # Definimos valores por defecto.
        df['_priority'] = 'Media'
        df['_priority_reason'] = "Prioridad base (Estándar)"

        if pay_group_col_name and enable_scf:
            print(f"INFO: Aplicando lógica base sobre columna '{pay_group_col_name}'")
            
            # Normalizamos la columna 'Pay Group' para comparaciones (vectorizado).
            pg_series = df[pay_group_col_name].str.strip().str.upper()
            
            # Definimos condiciones vectoriales.
            # Condición 1: SCF o Intercompany.
            cond_alta = pg_series.isin(['SCF', 'INTERCOMPANY'])
            # Condición 2: Empieza con 'PAY GROUP'.
            cond_baja = pg_series.str.startswith('PAY GROUP', na=False)
            
            # Definimos las listas de condiciones y elecciones para np.select.
            conditions = [cond_alta, cond_baja]
            
            # Elecciones para '_priority'.
            choices_prio = ['Alta', 'Baja']
            # Elecciones para '_priority_reason'.
            choices_reason = ['Prioridad base (SCF/Intercompany)', 'Prioridad base (Pay Group)']
            
            # Aplicamos np.select (equivalente a if/elif/else vectorial).
            # default='Media' mantiene lo que ya asignamos, pero podemos reforzarlo.
            df['_priority'] = np.select(conditions, choices_prio, default='Media')
            
            # Para la razón, tomamos las filas que cambiaron.
            # Nota: np.select evalúa todo, así que actualizamos la razón solo donde hubo match,
            # o usamos la misma lógica completa.
            df['_priority_reason'] = np.select(conditions, choices_reason, default="Prioridad base (Estándar)")

        elif not pay_group_col_name:
            print("WARN: No se encontró columna 'Pay Group'. Se asigna prioridad Media por defecto.")
        
        # 5. Aplicar Reglas Personalizadas (Sobrescritura).
        print("INFO: Aplicando reglas de prioridad personalizadas...")
        df = apply_priority_rules(df)
        
        return df, pay_group_col_name

    except FileNotFoundError:
        print(f"ERROR: No se encontró el archivo en la ruta: {ruta_archivo}")
        return pd.DataFrame(), None
    except Exception as e:
        print(f"ERROR CRÍTICO al cargar el archivo Excel: {e}")
        return pd.DataFrame(), None

# (Nota: Se elimina la función auxiliar `_assign_priority` ya que su lógica fue
#  incorporada de forma vectorizada dentro de `cargar_datos` para mayor eficiencia.)