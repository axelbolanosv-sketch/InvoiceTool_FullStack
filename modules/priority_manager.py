"""
priority_manager.py (Versión 2.0 - Motor Multi-Condición)
---------------------------------------------------------
Gestiona reglas complejas con múltiples condiciones y operadores.
"""

import uuid
import pandas as pd
import numpy as np
from .json_manager import cargar_json, guardar_json

RULES_FILE = 'user_priority_rules.json'

def _load_data() -> dict:
    data = cargar_json(RULES_FILE)
    if 'rules' not in data: data['rules'] = []
    if 'settings' not in data:
        data['settings'] = { "enable_scf_intercompany": True, "enable_age_sort": True }
    return data

def load_rules() -> list[dict]:
    return _load_data().get('rules', [])

def load_settings() -> dict:
    return _load_data().get('settings', {})

def save_settings(new_settings: dict) -> bool:
    data = _load_data()
    data['settings'].update(new_settings)
    return guardar_json(RULES_FILE, data)

def save_rule(rule_data: dict) -> bool:
    """
    Guarda una regla nueva o actualiza una existente basada en su ID.
    """
    data = _load_data()
    rules = data['rules']
    
    # Si viene sin ID, es nueva: generamos uno
    if not rule_data.get('id'):
        rule_data['id'] = str(uuid.uuid4())
        rule_data['active'] = True
        rules.append(rule_data)
    else:
        # Si tiene ID, buscamos y reemplazamos (Edición)
        for i, r in enumerate(rules):
            if r.get('id') == rule_data['id']:
                # Mantenemos el estado 'active' original si no se especifica
                if 'active' not in rule_data:
                    rule_data['active'] = r.get('active', True)
                rules[i] = rule_data
                break
        else:
            # Si traía ID pero no se encontró (raro), la agregamos
            rules.append(rule_data)
            
    return guardar_json(RULES_FILE, data)

def delete_rule(rule_id: str) -> bool:
    """Elimina una regla por su ID único."""
    data = _load_data()
    initial_len = len(data['rules'])
    data['rules'] = [r for r in data['rules'] if r.get('id') != rule_id]
    if len(data['rules']) < initial_len:
        return guardar_json(RULES_FILE, data)
    return False

def toggle_rule(rule_id: str, active: bool) -> bool:
    """Activa o desactiva una regla por ID."""
    data = _load_data()
    for r in data['rules']:
        if r.get('id') == rule_id:
            r['active'] = active
            return guardar_json(RULES_FILE, data)
    return False

def replace_all_rules(new_rules: list, new_settings: dict) -> bool:
    """Sobrescribe todo (para Importar Vistas)."""
    return guardar_json(RULES_FILE, {"rules": new_rules, "settings": new_settings})

# --- MOTOR DE EVALUACIÓN ---

def _safe_numeric_convert(series):
    """Intenta convertir una columna a números para comparaciones matemáticas."""
    # Limpiar símbolos de moneda y comas
    clean = series.astype(str).str.replace(r'[$,]', '', regex=True)
    return pd.to_numeric(clean, errors='coerce')

def apply_priority_rules(df: pd.DataFrame) -> pd.DataFrame:
    """
    Aplica reglas multi-condición secuencialmente.
    Las reglas de más abajo en la lista tienen prioridad (sobrescriben).
    """
    rules = load_rules()
    if not rules: return df
    
    if '_priority_reason' not in df.columns: df['_priority_reason'] = ""

    for rule in rules:
        if not rule.get('active', True): continue
        
        conditions = rule.get('conditions', [])
        if not conditions: continue

        # Empezamos asumiendo que todas las filas cumplen (Máscara True)
        # y vamos filtrando con AND.
        final_mask = pd.Series([True] * len(df), index=df.index)
        
        try:
            for cond in conditions:
                col = cond.get('column')
                op = cond.get('operator')
                val = str(cond.get('value', '')).lower().strip()
                
                if col not in df.columns:
                    final_mask = False # Si falta una columna, la regla falla
                    break
                
                # Preparamos datos para comparar
                series_str = df[col].astype(str).str.lower().str.strip()
                
                mask_cond = False
                
                if op == 'contains':
                    mask_cond = series_str.str.contains(val, regex=False, na=False)
                elif op == 'equals':
                    mask_cond = (series_str == val)
                elif op in ['>', '<', '>=', '<=']:
                    # Comparación Numérica
                    nums_col = _safe_numeric_convert(df[col])
                    try:
                        val_num = float(val)
                        if op == '>': mask_cond = nums_col > val_num
                        elif op == '<': mask_cond = nums_col < val_num
                        elif op == '>=': mask_cond = nums_col >= val_num
                        elif op == '<=': mask_cond = nums_col <= val_num
                    except:
                        mask_cond = False # Fallo conversión
                
                # Lógica AND: Acumulamos
                final_mask = final_mask & mask_cond
            
            # Aplicar cambios donde la máscara sea True
            if isinstance(final_mask, pd.Series) and final_mask.any():
                df.loc[final_mask, '_priority'] = rule.get('priority')
                df.loc[final_mask, '_priority_reason'] = rule.get('reason', 'Regla compleja')
                
        except Exception as e:
            print(f"Error aplicando regla {rule.get('reason')}: {e}")
            continue

    return df