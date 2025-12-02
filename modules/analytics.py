"""
modules/analytics.py
--------------------
Módulo de Análisis Estadístico e Inteligencia de Negocio.
"""
import pandas as pd
import numpy as np

def detect_anomalies(df: pd.DataFrame, monto_col: str) -> dict:
    """
    Detecta filas cuyo monto supera la media + 2 desviaciones estándar.
    """
    if not monto_col or monto_col not in df.columns:
        return {"error": "No se encontró columna de monto."}

    try:
        # 1. Limpieza Numérica
        clean_series = df[monto_col].astype(str).str.replace(r'[$,]', '', regex=True)
        numeric_values = pd.to_numeric(clean_series, errors='coerce').fillna(0)
        
        # 2. Cálculo Estadístico
        mean = numeric_values.mean()
        std_dev = numeric_values.std()
        
        if std_dev == 0:
            threshold = numeric_values.max() + 0.01
        else:
            threshold = mean + (2 * std_dev)

        # 3. Filtrado de Anomalías
        anomalies_mask = numeric_values > threshold
        anomalies_df = df[anomalies_mask].copy()
        
        if not anomalies_df.empty:
            diff = numeric_values[anomalies_mask] - mean
            z_scores = diff / std_dev if std_dev > 0 else 0
            anomalies_df['_anomaly_score'] = z_scores.round(2)

        # --- CORRECCIÓN CRÍTICA: Convertir a tipos nativos de Python ---
        # Esto evita el error de "JSON Serializable" con Numpy
        return {
            "status": "success",
            "threshold": float(threshold),  # Convertir numpy.float -> float
            "mean": float(mean),            # Convertir numpy.float -> float
            "count": int(len(anomalies_df)), # Convertir numpy.int -> int
            "data": anomalies_df.fillna("").to_dict('records') # fillna para evitar NaNs que rompen JSON
        }

    except Exception as e:
        return {"error": f"Error de cálculo: {str(e)}"}