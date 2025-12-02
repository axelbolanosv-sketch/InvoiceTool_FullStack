# modules/json_manager.py (Versión Completa)
import os
import json
from typing import Dict, Any

# --- CONSTANTE FALTANTE ---
# Esta es la pieza que autocomplete.py no encontraba
USER_LISTS_FILE = 'user_autocomplete.json'

def cargar_json(file_path: str) -> Dict[str, Any]:
    """
    Carga un archivo JSON de forma segura.
    Si no existe o está corrupto, devuelve un diccionario vacío.
    """
    try:
        if not os.path.exists(file_path):
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump({}, f)
            return {}
            
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
                
    except Exception as e:
        print(f"Error leyendo JSON {file_path}: {e}")
        return {}

def guardar_json(file_path: str, data: Dict[str, Any]) -> bool:
    """
    Guarda un diccionario en un archivo JSON.
    """
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"Error guardando JSON {file_path}: {e}")
        return False