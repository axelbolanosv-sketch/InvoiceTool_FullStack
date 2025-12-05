"""
================================================================================
APP.PY - CONTROLADOR PRINCIPAL (FLASK) - VERSIÓN 10.1 (FIX EMPTY TABLE)
================================================================================
Descripción:
    Controlador completo que integra:
    1. Versión Protegida: No borra el archivo subido, lo protege.
    2. Historial en Disco: Usa archivos .pkl para 'Deshacer' masivo sin saturar RAM.
    3. Traductor: Context Processor inyectado correctamente.
    4. CORRECCIÓN CRÍTICA: Permite tablas vacías sin forzar recarga del original.
================================================================================
"""

# ------------------------------------------------------------------------------
# 1. IMPORTACIONES & CONFIGURACIÓN
# ------------------------------------------------------------------------------
import os
import io
import uuid
import json
import time
import shutil
import pickle
from datetime import datetime, timedelta

import pandas as pd
import numpy as np
from flask import Flask, request, jsonify, render_template, send_file, session
from flask_cors import CORS
from flask_session import Session

# --- Módulos Propios ---
from modules.loader import cargar_datos
from modules.filters import aplicar_filtros_dinamicos
from modules.translator import get_text, LANGUAGES
from modules.json_manager import guardar_json, cargar_json, USER_LISTS_FILE
from modules.autocomplete import get_autocomplete_options
from modules.analytics import detect_anomalies
from modules.llm_agent import procesar_mensaje_ia
from modules.priority_manager import (
    save_rule, load_rules, delete_rule, apply_priority_rules,
    load_settings, save_settings, toggle_rule, replace_all_rules
)

# --- Constantes Globales ---
UNDO_STACK_LIMIT = 20
UPLOAD_FOLDER = 'temp_uploads'
HISTORY_FOLDER = os.path.join(UPLOAD_FOLDER, 'history_cache')

# --- Inicialización de Flask ---
app = Flask(__name__, template_folder='templates', static_folder='static')
CORS(app)

# --- Configuración de Sesión ---
app.config['SECRET_KEY'] = 'mi-llave-maestra-segura-2025'
app.config["SESSION_TYPE"] = "filesystem"
app.config["SESSION_FILE_DIR"] = os.path.join(UPLOAD_FOLDER, 'flask_session')
app.config["SESSION_PERMANENT"] = True
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(minutes=120) # 2 horas
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB

# Asegurar existencia de carpetas
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(HISTORY_FOLDER, exist_ok=True)
os.makedirs(app.config["SESSION_FILE_DIR"], exist_ok=True)

Session(app)


# ------------------------------------------------------------------------------
# 2. GESTIÓN DE ALMACENAMIENTO EN DISCO & LIMPIEZA
# ------------------------------------------------------------------------------

def save_history_to_disk(data_payload):
    """Guarda bloque de historial en disco (.pkl) y retorna el nombre."""
    filename = f"hist_{uuid.uuid4().hex}.pkl"
    filepath = os.path.join(HISTORY_FOLDER, filename)
    try:
        with open(filepath, 'wb') as f:
            pickle.dump(data_payload, f)
        return filename
    except Exception as e:
        print(f"Error guardando historial en disco: {e}")
        return None

def load_history_from_disk(filename):
    """Lee bloque de historial desde disco."""
    filepath = os.path.join(HISTORY_FOLDER, filename)
    if not os.path.exists(filepath):
        return None
    try:
        with open(filepath, 'rb') as f:
            return pickle.load(f)
    except Exception as e:
        print(f"Error leyendo historial de disco: {e}")
        return None

def clean_stale_files():
    """Borra archivos temporales viejos (>24h) al inicio."""
    now = time.time()
    for folder in [HISTORY_FOLDER, UPLOAD_FOLDER]:
        if not os.path.exists(folder): continue
        for fname in os.listdir(folder):
            fpath = os.path.join(folder, fname)
            if os.path.isfile(fpath) and fname.startswith(('hist_', 'protected_', 'temp_')):
                if os.stat(fpath).st_mtime < (now - 86400):
                    try: os.remove(fpath)
                    except: pass

clean_stale_files()


# ------------------------------------------------------------------------------
# 3. CONTEXT PROCESSOR
# ------------------------------------------------------------------------------

@app.context_processor
def inject_translator():
    return dict(get_text=get_text, lang=session.get('language', 'es'))


# ------------------------------------------------------------------------------
# 4. FUNCIONES AUXILIARES DE LÓGICA (CORREGIDAS)
# ------------------------------------------------------------------------------

def _check_file_id(request_file_id: str):
    session_file_id = session.get('file_id')
    # Si no hay sesión pero el ID coincide, intentamos recuperar (silent recovery)
    if not session_file_id and request_file_id:
        protected_path = os.path.join(UPLOAD_FOLDER, f"protected_{request_file_id}.xlsx")
        if os.path.exists(protected_path):
             return # Permitimos continuar para que _get_df_from_session restaure
        raise Exception("Sesión expirada. Por favor recargue.")
        
    if session_file_id != request_file_id:
        raise Exception("ID de archivo no coincide.")

def _get_df_from_session_as_df() -> pd.DataFrame:
    data = session.get('df_staging')
    
    # FIX: Usar 'is None' en lugar de 'if not data' para permitir tablas vacías (deleted all)
    if data is None:
        # Recuperación de emergencia desde archivo protegido
        fid = session.get('file_id') or request.json.get('file_id') # Intentar obtener ID
        if fid:
            protected_path = os.path.join(UPLOAD_FOLDER, f"protected_{fid}.xlsx")
            if os.path.exists(protected_path):
                print(f"[RECOVERY] Restaurando sesión desde {protected_path}")
                df, pay_col = cargar_datos(protected_path)
                if '_row_id' not in df.columns:
                     df = df.reset_index().rename(columns={'index': '_row_id'})
                
                # Restaurar sesión básica
                session['df_staging'] = df.to_dict('records')
                session['file_id'] = fid
                session['pay_group_col_name'] = pay_col
                return df
        # Si llegamos aquí, es que realmente no hay datos ni backup
        raise Exception("Datos no encontrados en memoria ni disco.")
    
    return pd.DataFrame.from_records(data)

def _calculate_kpis(df: pd.DataFrame) -> dict:
    monto_total = 0.0
    monto_promedio = 0.0
    total_facturas = len(df)
    
    monto_col = next((c for c in df.columns if str(c).lower() in ['monto', 'total', 'amount']), None)

    if monto_col and not df.empty:
        try:
            clean = df[monto_col].astype(str).str.replace(r'[$,]', '', regex=True)
            nums = pd.to_numeric(clean, errors='coerce').fillna(0)
            monto_total = nums.sum()
            monto_promedio = nums.mean()
        except: pass

    return {
        "total_facturas": total_facturas,
        "monto_total": f"${monto_total:,.2f}",
        "monto_promedio": f"${monto_promedio:,.2f}"
    }

def _recalculate_priorities(df: pd.DataFrame) -> pd.DataFrame:
    return apply_priority_rules(df)

def _generic_download(data, grouped):
    _check_file_id(data.get('file_id'))
    df = _get_df_from_session_as_df()
    df = aplicar_filtros_dinamicos(df, data.get('filtros_activos'))
    
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine='xlsxwriter') as writer:
        if grouped:
            col = data.get('columna_agrupar')
            if col in df.columns:
                gb = df.groupby(col).size().reset_index(name='count')
                gb.to_excel(writer, index=False)
        else:
            cols = data.get('columnas_visibles', df.columns)
            valid = [c for c in cols if c in df.columns]
            df[valid].to_excel(writer, index=False)
            
    out.seek(0)
    return send_file(out, as_attachment=True, download_name='download.xlsx', mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


# ------------------------------------------------------------------------------
# 5. RUTAS: VISTAS Y SISTEMA
# ------------------------------------------------------------------------------

@app.route('/')
def home():
    session_data = {
        "file_id": session.get('file_id'),
        "columnas": [], "autocomplete_options": {}, 
        "history_count": len(session.get('history', []))
    }
    df_data = session.get('df_staging')
    if df_data:
        session_data["columnas"] = list(df_data[0].keys())
        try: session_data["autocomplete_options"] = get_autocomplete_options(pd.DataFrame.from_records(df_data))
        except: pass

    return render_template('index.html', session_data=session_data)

@app.route('/api/system/reset_cache', methods=['POST'])
def reset_system_cache():
    try:
        # 1. Identificar archivos asociados antes de borrar la sesión
        file_id = session.get('file_id')
        hist = session.get('history', [])
        
        # 2. Borrar Historial de Disco específico de este usuario
        if hist:
            for h in hist:
                if h.get('storage') == 'disk' and 'filename' in h:
                    try:
                        os.remove(os.path.join(HISTORY_FOLDER, h['filename']))
                    except: pass
        
        # 3. Borrar Archivos Temporales y Protegidos de este usuario
        if file_id:
            for prefix in ['temp_', 'protected_']:
                try:
                    path = os.path.join(UPLOAD_FOLDER, f"{prefix}{file_id}.xlsx")
                    if os.path.exists(path): os.remove(path)
                except: pass

        # 4. Limpiar la sesión de Flask (RAM/Cookie)
        session.clear()
        
        return jsonify({'message': 'Sistema reiniciado y memoria liberada.', 'status': 'success'})
    except Exception as e:
        # Incluso si falla borrar un archivo, la sesión debe limpiarse
        session.clear() 
        return jsonify({'error': str(e)}), 500

@app.route('/api/set_language/<string:lang_code>')
def set_language(lang_code):
    if lang_code in LANGUAGES: session['language'] = lang_code
    return jsonify({"status": "success", "language": lang_code})

@app.route('/api/get_translations')
def get_translations():
    return jsonify(LANGUAGES.get(session.get('language', 'es'), LANGUAGES['es']))


# ------------------------------------------------------------------------------
# 6. RUTAS: GESTIÓN DE ARCHIVOS (PROTECTED)
# ------------------------------------------------------------------------------

@app.route('/api/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files: return jsonify({"error": "No file"}), 400
    file = request.files['file']
    if file.filename == '': return jsonify({"error": "No selection"}), 400

    file_id = str(uuid.uuid4())
    temp_path = os.path.join(UPLOAD_FOLDER, f"temp_{file_id}.xlsx")
    protected_path = os.path.join(UPLOAD_FOLDER, f"protected_{file_id}.xlsx")
    
    file.save(temp_path)

    try:
        session.clear() 
        
        df, pay_col = cargar_datos(temp_path)
        if df.empty: raise Exception("Archivo vacío.")
        df = df.reset_index().rename(columns={'index': '_row_id'})

        # Guardar copia protegida (Persistencia)
        if os.path.exists(protected_path): os.remove(protected_path)
        os.rename(temp_path, protected_path)

        session['df_staging'] = df.to_dict('records')
        session['history'] = []
        session['audit_log'] = []
        session['file_id'] = file_id
        session['pay_group_col_name'] = pay_col
        session.permanent = True 
        
        return jsonify({
            "file_id": file_id,
            "columnas": list(df.columns),
            "autocomplete_options": get_autocomplete_options(df)
        })

    except Exception as e:
        if os.path.exists(temp_path): os.remove(temp_path)
        return jsonify({"error": str(e)}), 500


# ------------------------------------------------------------------------------
# 7. RUTAS: MANIPULACIÓN DE DATOS
# ------------------------------------------------------------------------------

@app.route('/api/filter', methods=['POST'])
def filter_data():
    try:
        data = request.json
        _check_file_id(data.get('file_id'))
        df = _get_df_from_session_as_df()
        df_filt = aplicar_filtros_dinamicos(df, data.get('filtros_activos'))
        return jsonify({
            "data": df_filt.to_dict('records'),
            "num_filas": len(df_filt),
            "resumen": _calculate_kpis(df_filt)
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/group_by', methods=['POST'])
def group_by_data():
    try:
        data = request.json
        _check_file_id(data.get('file_id'))
        df = _get_df_from_session_as_df()
        df = aplicar_filtros_dinamicos(df, data.get('filtros_activos'))
        col = data.get('columna_agrupar')
        if col not in df.columns: return jsonify({"error": "Columna inválida"}), 400
        
        monto_col = next((c for c in df.columns if str(c).lower() in ['monto', 'total', 'amount']), None)
        
        if monto_col:
            clean = df[monto_col].astype(str).str.replace(r'[$,]', '', regex=True)
            df['_tm'] = pd.to_numeric(clean, errors='coerce').fillna(0)
            gb = df.groupby(col)['_tm'].agg(['sum', 'mean', 'min', 'max', 'count']).reset_index()
            gb.columns = [col, 'Total_sum', 'Total_mean', 'Total_min', 'Total_max', 'Total_count']
            for c in ['Total_sum', 'Total_mean', 'Total_min', 'Total_max']: gb[c] = gb[c].round(2)
        else:
            gb = df.groupby(col).size().reset_index(name='Total_count')
            for c in ['Total_sum', 'Total_mean', 'Total_min', 'Total_max']: gb[c] = 0
            
        return jsonify({"data": gb.fillna(0).to_dict('records')})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ------------------------------------------------------------------------------
# 8. RUTAS: EDICIÓN Y OPERACIONES MASIVAS
# ------------------------------------------------------------------------------

@app.route('/api/update_cell', methods=['POST'])
def update_cell():
    try:
        d = request.json
        _check_file_id(d.get('file_id'))
        rid_str = str(d.get('row_id'))
        
        data = session.get('df_staging')
        history = session.get('history', [])
        audit = session.get('audit_log', [])
        changed = None
        new_prio = None
        
        for r in data:
            if str(r.get('_row_id')) == rid_str:
                old = r.get(d['columna'])
                if old == d['valor']: return jsonify({"status": "no_change"})
                
                history.append({'action': 'update', 'row_id': rid_str, 'columna': d['columna'], 'old_val': old, 'new_val': d['valor']})
                if len(history) > UNDO_STACK_LIMIT: history.pop(0)
                
                audit.append({'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M'), 'action': 'Update', 'row_id': rid_str, 'details': f"{d['columna']}: {old}->{d['valor']}"})
                
                r[d['columna']] = d['valor']
                r['_row_status'] = 'Incompleto' if not str(d['valor']).strip() else 'Completo'
                changed = r
                break
        
        if not changed: return jsonify({"error": "Fila no encontrada"}), 404
        
        df = pd.DataFrame.from_records(data)
        df = _recalculate_priorities(df)
        session['df_staging'] = df.to_dict('records')
        session['history'] = history
        session['audit_log'] = audit
        
        p_row = df.loc[df['_row_id'].astype(str) == rid_str]
        if not p_row.empty: new_prio = p_row['_priority'].iloc[0]
        
        return jsonify({
            "status": "success", "history_count": len(history),
            "resumen": _calculate_kpis(df), "new_priority": new_prio,
            "new_row_status": changed.get('_row_status')
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/add_row', methods=['POST'])
def add_row():
    try:
        _check_file_id(request.json.get('file_id'))
        data = session.get('df_staging')
        max_id = max([int(r.get('_row_id', 0)) for r in data]) if data else 0
        new_id = max_id + 1
        cols = list(data[0].keys()) if data else ['_row_id']
        new_row = {c: "" for c in cols}
        new_row.update({'_row_id': new_id, '_row_status': 'Incompleto', '_priority': 'Media'})
        data.append(new_row)
        
        hist = session.get('history', [])
        hist.append({'action': 'add', 'row_id': new_id})
        if len(hist) > UNDO_STACK_LIMIT: hist.pop(0)
        
        session['df_staging'] = data
        session['history'] = hist
        return jsonify({"status": "success", "new_row_id": new_id, "history_count": len(hist), "resumen": _calculate_kpis(pd.DataFrame.from_records(data))})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/delete_row', methods=['POST'])
def delete_row():
    try:
        rid = str(request.json.get('row_id'))
        _check_file_id(request.json.get('file_id'))
        data = session.get('df_staging')
        idx = next((i for i, r in enumerate(data) if str(r.get('_row_id')) == rid), -1)
        if idx == -1: return jsonify({"error": "No encontrada"}), 404
        
        deleted = data.pop(idx)
        hist = session.get('history', [])
        hist.append({'action': 'delete', 'deleted_row': deleted, 'original_index': idx})
        if len(hist) > UNDO_STACK_LIMIT: hist.pop(0)
        
        session['df_staging'] = data
        session['history'] = hist
        return jsonify({"status": "success", "history_count": len(hist), "resumen": _calculate_kpis(pd.DataFrame.from_records(data))})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/bulk_update', methods=['POST'])
def bulk_update():
    try:
        d = request.json
        _check_file_id(d.get('file_id'))
        ids = set(str(i) for i in d.get('row_ids', []))
        data = session.get('df_staging')
        changes = []
        count = 0
        
        for r in data:
            if str(r.get('_row_id')) in ids:
                old = r.get(d['column'])
                if old != d['new_value']:
                    changes.append({'row_id': str(r.get('_row_id')), 'old_val': old})
                    r[d['column']] = d['new_value']
                    count += 1
        
        if count > 0:
            hist = session.get('history', [])
            hist.append({'action': 'bulk_update', 'columna': d['column'], 'new_val': d['new_value'], 'changes': changes})
            session['history'] = hist
            df = pd.DataFrame.from_records(data)
            df = _recalculate_priorities(df)
            session['df_staging'] = df.to_dict('records')
            return jsonify({"status": "success", "message": f"{count} editados.", "history_count": len(hist), "resumen": _calculate_kpis(df)})
        return jsonify({"status": "no_change"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/find_replace_in_selection', methods=['POST'])
def find_replace():
    try:
        d = request.json
        _check_file_id(d.get('file_id'))
        ids = set(str(i) for i in d.get('row_ids', []))
        data = session.get('df_staging')
        changes = []
        count = 0
        
        for r in data:
            if str(r.get('_row_id')) in ids:
                old = r.get(d['columna'])
                if str(old) == str(d['find_text']):
                    changes.append({'row_id': str(r.get('_row_id')), 'old_val': old})
                    r[d['columna']] = d['replace_text']
                    count += 1
        
        if count > 0:
            hist = session.get('history', [])
            hist.append({'action': 'find_replace', 'columna': d['columna'], 'new_val': d['replace_text'], 'changes': changes})
            session['history'] = hist
            df = pd.DataFrame.from_records(data)
            df = _recalculate_priorities(df)
            session['df_staging'] = df.to_dict('records')
            return jsonify({"status": "success", "message": f"{count} reemplazados.", "history_count": len(hist), "resumen": _calculate_kpis(df)})
        return jsonify({"status": "no_change"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/bulk_delete_rows', methods=['POST'])
def bulk_delete():
    try:
        req = request.json
        ids = set(str(i) for i in req.get('row_ids', []))
        _check_file_id(req.get('file_id'))
        
        data = session.get('df_staging')
        kept = []
        deleted = []
        
        for r in data:
            if str(r.get('_row_id')) in ids: deleted.append(r)
            else: kept.append(r)
            
        if deleted:
            hist = session.get('history', [])
            
            if len(deleted) > 50:
                filename = save_history_to_disk(deleted)
                if filename:
                    hist.append({'action': 'bulk_delete', 'storage': 'disk', 'filename': filename, 'count': len(deleted)})
                else:
                    hist.append({'action': 'bulk_delete', 'storage': 'ram', 'deleted_rows': deleted})
            else:
                hist.append({'action': 'bulk_delete', 'storage': 'ram', 'deleted_rows': deleted})
            
            if len(hist) > UNDO_STACK_LIMIT: 
                old = hist.pop(0)
                if old.get('storage') == 'disk':
                    try: os.remove(os.path.join(HISTORY_FOLDER, old['filename']))
                    except: pass
            
            session['history'] = hist
            session['df_staging'] = kept
            
            return jsonify({
                "status": "success", "message": f"{len(deleted)} eliminadas.", 
                "history_count": len(hist), "resumen": _calculate_kpis(pd.DataFrame.from_records(kept))
            })
            
        return jsonify({"status": "no_change"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ------------------------------------------------------------------------------
# 9. RUTAS: DESHACER Y COMMIT
# ------------------------------------------------------------------------------

@app.route('/api/undo_change', methods=['POST'])
def undo_change():
    try:
        _check_file_id(request.json.get('file_id'))
        hist = session.get('history', [])
        if not hist: return jsonify({"error": "Nada que deshacer"}), 404
        
        last = hist.pop()
        data = session.get('df_staging')
        affected = 'bulk'
        
        if last['action'] == 'update':
            for r in data:
                if str(r['_row_id']) == str(last['row_id']):
                    r[last['columna']] = last['old_val']
                    affected = last['row_id']
                    break
        
        elif last['action'] == 'add':
            data = [r for r in data if str(r['_row_id']) != str(last['row_id'])]
            
        elif last['action'] == 'delete':
            data.insert(last['original_index'], last['deleted_row'])
            affected = last['deleted_row']['_row_id']
            
        elif last['action'] in ('bulk_update', 'find_replace'):
            restore_map = {c['row_id']: c['old_val'] for c in last['changes']}
            for r in data:
                if str(r['_row_id']) in restore_map: r[last['columna']] = restore_map[str(r['_row_id'])]
        
        elif last['action'] == 'bulk_delete':
            restored = []
            if last.get('storage') == 'disk':
                restored = load_history_from_disk(last['filename'])
                try: os.remove(os.path.join(HISTORY_FOLDER, last['filename']))
                except: pass
            else:
                restored = last.get('deleted_rows', [])
            
            if restored:
                data.extend(restored)
                data.sort(key=lambda x: int(x['_row_id']))
                
        elif last['action'] == 'delete_column':
             col = last['columna']
             restore_map = {str(x['_row_id']): x[col] for x in last['restore_data']}
             for r in data:
                 if str(r['_row_id']) in restore_map: r[col] = restore_map[str(r['_row_id'])]

        df = pd.DataFrame.from_records(data)
        df = _recalculate_priorities(df)
        session['df_staging'] = df.to_dict('records')
        session['history'] = hist
        
        return jsonify({
            "status": "success", "history_count": len(hist),
            "resumen": _calculate_kpis(df), "affected_row_id": affected
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/commit_changes', methods=['POST'])
def commit_changes():
    _check_file_id(request.json.get('file_id'))
    
    hist = session.get('history', [])
    for h in hist:
        if h.get('storage') == 'disk':
            try: os.remove(os.path.join(HISTORY_FOLDER, h['filename']))
            except: pass
            
    session['history'] = []
    return jsonify({"status": "success", "message": "Historial limpiado."})


# ------------------------------------------------------------------------------
# 10. RUTAS: EXTENSIONES
# ------------------------------------------------------------------------------

@app.route('/api/get_duplicate_invoices', methods=['POST'])
def get_duplicates():
    try:
        _check_file_id(request.json.get('file_id'))
        df = _get_df_from_session_as_df()
        
        invoice_col = next((c for c in df.columns if str(c).lower() in ['invoice #', 'invoice number', 'n° factura', 'factura']), None)
        if not invoice_col: return jsonify({"error": "No se detectó columna de Factura"}), 400
        
        dupes = df[df.duplicated(subset=[invoice_col], keep=False)].sort_values(by=[invoice_col])
        return jsonify({"data": dupes.to_dict('records'), "num_filas": len(dupes)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/cleanup_duplicate_invoices', methods=['POST'])
def cleanup_duplicates():
    try:
        _check_file_id(request.json.get('file_id'))
        df = _get_df_from_session_as_df()
        invoice_col = next((c for c in df.columns if str(c).lower() in ['invoice #', 'invoice number', 'n° factura', 'factura']), None)
        
        mask = df.duplicated(subset=[invoice_col], keep='first')
        deleted = df[mask]
        
        if not deleted.empty:
            hist = session.get('history', [])
            rows_list = deleted.to_dict('records')
            if len(rows_list) > 50:
                fname = save_history_to_disk(rows_list)
                hist.append({'action': 'bulk_delete', 'storage': 'disk', 'filename': fname})
            else:
                hist.append({'action': 'bulk_delete', 'storage': 'ram', 'deleted_rows': rows_list})
                
            session['history'] = hist
            df_clean = df[~mask]
            session['df_staging'] = df_clean.to_dict('records')
            return jsonify({"status": "success", "message": f"{len(deleted)} eliminados.", "history_count": len(hist), "resumen": _calculate_kpis(df_clean)})
        return jsonify({"status": "no_change"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/delete_column', methods=['POST'])
def delete_column_route():
    try:
        col = request.json.get('columna')
        _check_file_id(request.json.get('file_id'))
        df = _get_df_from_session_as_df()
        
        col_backup = df[['_row_id', col]].to_dict('records')
        df_new = df.drop(columns=[col])
        session['df_staging'] = df_new.to_dict('records')
        
        hist = session.get('history', [])
        hist.append({'action': 'delete_column', 'columna': col, 'restore_data': col_backup})
        session['history'] = hist
        
        return jsonify({"status": "success", "history_count": len(hist), "new_columns": list(df_new.columns)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- Extensiones Varias ---
@app.route('/api/priority_rules/get', methods=['GET'])
def get_rules(): return jsonify({"rules": load_rules(), "settings": load_settings()})

@app.route('/api/priority_rules/save_settings', methods=['POST'])
def api_save_settings():
    save_settings(request.json)
    if session.get('df_staging'):
        df = _recalculate_priorities(_get_df_from_session_as_df())
        session['df_staging'] = df.to_dict('records')
    return jsonify({"status": "success"})

@app.route('/api/priority_rules/save', methods=['POST'])
def api_save_rule():
    save_rule(request.json)
    res = None
    if session.get('df_staging'):
        df = _recalculate_priorities(_get_df_from_session_as_df())
        session['df_staging'] = df.to_dict('records')
        res = _calculate_kpis(df)
    return jsonify({"status": "success", "resumen": res})

@app.route('/api/priority_rules/toggle', methods=['POST'])
def api_toggle_rule():
    d = request.json
    toggle_rule(d.get('rule_id'), d.get('active'))
    if session.get('df_staging'):
        df = _recalculate_priorities(_get_df_from_session_as_df())
        session['df_staging'] = df.to_dict('records')
    return jsonify({"status": "success"})

@app.route('/api/priority_rules/delete', methods=['POST'])
def api_delete_rule():
    delete_rule(request.json.get('rule_id'))
    res = None
    if session.get('df_staging'):
        df = _recalculate_priorities(_get_df_from_session_as_df())
        session['df_staging'] = df.to_dict('records')
        res = _calculate_kpis(df)
    return jsonify({"status": "success", "resumen": res})

@app.route('/api/save_autocomplete_lists', methods=['POST'])
def api_save_lists():
    guardar_json(USER_LISTS_FILE, request.json)
    return jsonify({"status": "success"})

@app.route('/api/import_autocomplete_values', methods=['POST'])
def api_import_autocomplete():
    try:
        data = request.json
        _check_file_id(data.get('file_id'))
        col = data.get('column')
        df = _get_df_from_session_as_df()
        vals = sorted([v.strip() for v in df[col].dropna().astype(str).unique() if v.strip() not in ["", "nan", "None"]])
        curr = cargar_json(USER_LISTS_FILE)
        ex = set(curr.get(col, []))
        ex.update(vals)
        curr[col] = sorted(list(ex))
        guardar_json(USER_LISTS_FILE, curr)
        return jsonify({"status": "success", "message": f"Importados {len(vals)}.", "autocomplete_options": get_autocomplete_options(df)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/chat_agent', methods=['POST'])
def chat_agent_route():
    try:
        data = request.json
        _check_file_id(data.get('file_id'))
        df = _get_df_from_session_as_df()
        res_txt, acts = procesar_mensaje_ia(data.get('message'), df)
        return jsonify({"response": res_txt, "actions": acts})
    except Exception as e:
        return jsonify({"response": f"Error: {e}", "actions": []}), 500

@app.route('/api/analyze_anomalies', methods=['POST'])
def analyze_anomalies_route():
    try:
        _check_file_id(request.json.get('file_id'))
        df = _get_df_from_session_as_df()
        monto_col = next((c for c in df.columns if str(c).lower() in ['monto', 'total', 'amount']), None)
        res = detect_anomalies(df, monto_col)
        if res.get("error"): return jsonify({"status": "error", "message": res["error"]}), 400
        return jsonify({"status": "success", "data": res['data'], "summary": {"threshold": res['threshold'], "mean": res['mean'], "count": res['count'], "column_used": monto_col}})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/download_audit_log', methods=['POST'])
def download_audit():
    _check_file_id(request.json.get('file_id'))
    logs = session.get('audit_log', [])
    sio = io.StringIO()
    sio.write(f"TIMESTAMP\tACCION\tFILA\tCOLUMNA\tVAL_ANT\tVAL_NUEVO\n")
    for l in logs:
        sio.write(f"{l.get('timestamp')}\t{l.get('action')}\t{l.get('row_id')}\t{l.get('columna')}\t{l.get('valor_anterior')}\t{l.get('valor_nuevo')}\n")
    out = io.BytesIO(sio.getvalue().encode('utf-8'))
    out.seek(0)
    return send_file(out, as_attachment=True, download_name='audit.txt', mimetype='text/plain')

@app.route('/api/download_excel', methods=['POST'])
def download_excel(): return _generic_download(request.json, grouped=False)

@app.route('/api/download_excel_grouped', methods=['POST'])
def download_excel_grouped(): return _generic_download(request.json, grouped=True)


if __name__ == '__main__':
    app.run(debug=True, port=5000)