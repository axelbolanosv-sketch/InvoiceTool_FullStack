# modules/filters.py (Versión 3.0 - Documentado y Optimizado)

import pandas as pd
from collections import defaultdict

def aplicar_filtros_dinamicos(df: pd.DataFrame, filtros: list) -> pd.DataFrame:
    """
    Aplica filtros dinámicos al DataFrame con lógica mixta (AND/OR).

    Lógica:
    - Filtros en columnas DIFERENTES: Lógica AND (Intersección).
    - Filtros en la MISMA columna: Lógica OR (Unión).

    Optimización v18.0:
    - Uso de vectorización para comparaciones de strings.
    - Manejo robusto de tipos de datos antes de la búsqueda.

    Args:
        df (pd.DataFrame): DataFrame original.
        filtros (list): Lista de dicts {'columna': str, 'valor': str}.

    Returns:
        pd.DataFrame: Subconjunto filtrado del DataFrame.
    """
    
    if not filtros:
        return df.copy()

    # 1. Agrupar filtros por columna.
    filtros_agrupados = defaultdict(list)
    for f in filtros:
        if f.get('columna') and f.get('valor'):
             filtros_agrupados[f['columna']].append(f['valor'])

    resultado = df.copy()

    # 2. Iterar sobre cada columna (Lógica AND entre columnas).
    for columna, valores in filtros_agrupados.items():
        if not valores:
            continue
            
        try:
            # Caso Especial: Filtro por ID de fila.
            if columna == '_row_id':
                ids_a_buscar = []
                for v in valores:
                    try:
                        # El usuario ve IDs base-1, el sistema usa base-0.
                        ids_a_buscar.append(int(v) - 1)
                    except ValueError:
                        pass
                
                if ids_a_buscar:
                    # .isin es altamente eficiente.
                    resultado = resultado[resultado[columna].isin(ids_a_buscar)]

            # Caso General: Filtro de texto parcial.
            elif columna in resultado.columns:
                # Normalizamos la columna a string y minúsculas de una vez.
                columna_texto = resultado[columna].astype(str).str.lower()
                
                # Creamos una máscara inicial de Falsos.
                mascara_or_columna = pd.Series([False] * len(resultado), index=resultado.index)
                
                # Acumulamos condiciones con OR (|).
                for valor in valores:
                    valor_lower = str(valor).lower()
                    # Usamos contains para búsqueda parcial. na=False maneja nulos.
                    mascara_or_columna |= columna_texto.str.contains(valor_lower, case=False, regex=False, na=False)
            
                # Aplicamos la máscara acumulada.
                resultado = resultado[mascara_or_columna]

        except Exception as e:
            print(f"Advertencia al filtrar columna '{columna}': {e}")
            # En caso de error, no filtramos esta columna para no romper el flujo.
            pass

    return resultado