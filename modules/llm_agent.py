# modules/llm_agent.py
# modules/llm_agent.py
import os
import json
import uuid
import pandas as pd
from openai import AzureOpenAI
from flask import session
from modules.priority_manager import save_rule, apply_priority_rules
from tenacity import retry, stop_after_attempt, wait_random_exponential

from dotenv import load_dotenv  # <--- NUEVA IMPORTACIÓN

# Cargar variables del archivo .env
load_dotenv()

# --- TUS CREDENCIALES (Ahora seguras) ---
AZURE_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_API_KEY = os.getenv("AZURE_OPENAI_KEY")
DEPLOYMENT_NAME = os.getenv("AZURE_DEPLOYMENT_NAME")
API_VERSION = os.getenv("AZURE_API_VERSION")

if not AZURE_API_KEY:
    raise ValueError("Error: No se encontró la clave API en el archivo .env")

client = AzureOpenAI(
    azure_endpoint=AZURE_ENDPOINT,
    api_key=AZURE_API_KEY,
    api_version=API_VERSION
)

# --- DEFINICIÓN DE HERRAMIENTAS ---
tools = [
    # 1. BORRADO INDIVIDUAL
    {
        "type": "function",
        "function": {
            "name": "eliminar_fila_individual",
            "description": "Elimina UNA sola fila específica. Usa esto si el usuario dice 'borra la fila 5'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "numero_fila_usuario": {"type": "integer", "description": "El número visual (N°)."}
                },
                "required": ["numero_fila_usuario"]
            }
        }
    },
    # 2. BORRADO MÚLTIPLE POR NÚMEROS (NUEVO)
    {
        "type": "function",
        "function": {
            "name": "eliminar_multiples_filas_por_numero",
            "description": "Elimina VARIAS filas específicas dadas por sus números. Usa esto si el usuario dice 'borra las filas 1, 5 y 10'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "lista_numeros": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "Lista de los números visuales de fila a borrar."
                    }
                },
                "required": ["lista_numeros"]
            }
        }
    },
    # 3. BORRADO POR FILTRO (CONDICIÓN)
    {
        "type": "function",
        "function": {
            "name": "preparar_eliminacion_masiva",
            "description": "Prepara borrado masivo aplicando un FILTRO. Usa esto para 'borrar todo lo de Amazon'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "columna": {"type": "string"},
                    "valor": {"type": "string"},
                    "operador": {"type": "string", "enum": ["contains", "equals"], "default": "contains"}
                },
                "required": ["columna", "valor"]
            }
        }
    },
    # 4. GESTIÓN COLUMNAS
    {
        "type": "function",
        "function": {
            "name": "gestionar_columnas",
            "description": "Oculta o muestra columnas visualmente.",
            "parameters": {
                "type": "object",
                "properties": {
                    "accion": {"type": "string", "enum": ["ocultar", "mostrar", "solo_mostrar"]},
                    "columnas": {"type": "array", "items": {"type": "string"}}
                },
                "required": ["accion", "columnas"]
            }
        }
    },
    # 5. BORRAR COLUMNA PERMANENTE
    {
        "type": "function",
        "function": {
            "name": "eliminar_columna_permanentemente",
            "description": "ELIMINA una columna completa.",
            "parameters": {
                "type": "object",
                "properties": {
                    "columna": {"type": "string"}
                },
                "required": ["columna"]
            }
        }
    },
    # OTRAS HERRAMIENTAS
    {
        "type": "function",
        "function": {
            "name": "examinar_datos_reales",
            "description": "Lee los datos para análisis.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filas_maximas": {"type": "integer", "description": "Default 50"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "filtrar_datos",
            "description": "Aplica filtros.",
            "parameters": {
                "type": "object",
                "properties": {
                    "columna": {"type": "string"},
                    "valor": {"type": "string"},
                    "operador": {"type": "string", "enum": ["contains", "equals", ">", "<"], "default": "contains"}
                },
                "required": ["columna", "valor"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "limpiar_filtros",
            "description": "Borra filtros.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "analizar_anomalias",
            "description": "Busca anomalías.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "crear_regla_prioridad",
            "description": "Crea reglas.",
            "parameters": {
                "type": "object",
                "properties": {
                    "condiciones": {"type": "array", "items": {"type": "object", "properties": {"columna": {"type": "string"}, "operador": {"type": "string"}, "value": {"type": "string"}}, "required": ["columna", "operador", "valor"]}},
                    "prioridad": {"type": "string", "enum": ["Alta", "Media", "Baja"]},
                    "razon": {"type": "string"}
                },
                "required": ["condiciones", "prioridad", "razon"]
            }
        }
    }
]

def _generar_contexto_valores(df):
    if df.empty: return ""
    cols_interes = ['Vendor Name', 'Assignee', 'Status', 'Pay Group']
    contexto = []
    for col in cols_interes:
        if col in df.columns:
            unicos = df[col].dropna().astype(str).unique()
            ejemplos = ", ".join(unicos[:20])
            contexto.append(f"- '{col}': {ejemplos}...")
    return "\n".join(contexto)

@retry(wait=wait_random_exponential(min=1, max=60), stop=stop_after_attempt(3))
def llamar_openai_con_retry(messages, tools=None, tool_choice="auto", temperature=0.3):
    return client.chat.completions.create(
        model=DEPLOYMENT_NAME, messages=messages, tools=tools, tool_choice=tool_choice, temperature=temperature
    )

def procesar_mensaje_ia(mensaje_usuario, df_staging):
    info_columnas = ""
    info_valores = ""
    if not df_staging.empty:
        info_columnas = f"Columnas: {', '.join(df_staging.columns.tolist())}."
        info_valores = _generar_contexto_valores(df_staging)

    messages = [
        {"role": "system", "content": f"""
        Eres un copiloto experto.
        {info_columnas}
        VALORES: {info_valores}
        
        INSTRUCCIONES CLAVE:
        1. Para borrar una lista de números (ej: "1, 2 y 3"), USA 'eliminar_multiples_filas_por_numero'.
        2. Para borrar por condición (ej: "las de Amazon"), USA 'preparar_eliminacion_masiva'.
        3. Para borrar UNA fila, USA 'eliminar_fila_individual'.
        """},
        {"role": "user", "content": mensaje_usuario}
    ]

    try:
        response = llamar_openai_con_retry(messages=messages, tools=tools, temperature=0.3)
        msg = response.choices[0].message
        acciones_ui = []
        texto_final = msg.content
        
        if msg.tool_calls:
            messages.append(msg)
            necesita_segundo_turno = False

            for tool in msg.tool_calls:
                fname = tool.function.name
                args = json.loads(tool.function.arguments)
                
                if fname == "eliminar_multiples_filas_por_numero":
                    numeros = args.get("lista_numeros", [])
                    # Convertir a IDs internos (restar 1)
                    ids_internos = [int(n) - 1 for n in numeros]
                    acciones_ui.append({
                        "action": "delete_multiple_rows_by_id_trigger",
                        "row_ids": ids_internos,
                        "numeros_visuales": numeros
                    })
                    texto_final = f"Seleccionando {len(numeros)} filas para eliminar..."
                    messages.append({"tool_call_id": tool.id, "role": "tool", "name": fname, "content": "OK"})

                elif fname == "eliminar_fila_individual":
                    row_visual = args.get("numero_fila_usuario")
                    row_id_interno = int(row_visual) - 1
                    acciones_ui.append({"action": "delete_single_row_trigger", "row_id": row_id_interno})
                    texto_final = f"Localizando la fila {row_visual}..."
                    messages.append({"tool_call_id": tool.id, "role": "tool", "name": fname, "content": "OK"})

                # ... (Resto de herramientas igual) ...
                elif fname == "eliminar_columna_permanentemente":
                    acciones_ui.append({"action": "delete_column_trigger", "columna": args.get("columna")})
                    texto_final = f"Solicitando borrado de columna..."
                    messages.append({"tool_call_id": tool.id, "role": "tool", "name": fname, "content": "OK"})

                elif fname == "gestionar_columnas":
                    acciones_ui.append({"action": "manage_columns", "mode": args.get("accion"), "columns": args.get("columnas")})
                    texto_final = f"Ajustando columnas..."
                    messages.append({"tool_call_id": tool.id, "role": "tool", "name": fname, "content": "OK"})

                elif fname == "preparar_eliminacion_masiva":
                    acciones_ui.append({"action": "prepare_bulk_delete", "columna": args.get("columna"), "valor": args.get("valor"), "operador": args.get("operador", "contains")})
                    texto_final = f"Seleccionando por filtro..."
                    messages.append({"tool_call_id": tool.id, "role": "tool", "name": fname, "content": "OK"})

                elif fname == "examinar_datos_reales":
                    limite = args.get("filas_maximas", 50) 
                    datos_csv = df_staging.head(limite).to_csv(index=False)
                    messages.append({"tool_call_id": tool.id, "role": "tool", "name": fname, "content": f"DATOS:\n{datos_csv}"})
                    necesita_segundo_turno = True
                
                elif fname == "filtrar_datos":
                    acciones_ui.append({"action": "add_filter", "columna": args.get("columna"), "valor": args.get("valor")})
                    texto_final = "Filtrando..."
                    messages.append({"tool_call_id": tool.id, "role": "tool", "name": fname, "content": "OK"})

                elif fname == "crear_regla_prioridad":
                    # ... misma lógica ...
                    condiciones_internas = []
                    if "condiciones" in args:
                        for cond in args["condiciones"]:
                            condiciones_internas.append({"column": cond.get("columna"), "operator": cond.get("operador"), "value": cond.get("valor")})
                    nueva_regla = {"id": str(uuid.uuid4()), "active": True, "priority": args.get("prioridad"), "reason": args.get("razon"), "conditions": condiciones_internas}
                    save_rule(nueva_regla)
                    if session.get('df_staging'):
                        df = pd.DataFrame.from_records(session['df_staging'])
                        df = apply_priority_rules(df)
                        session['df_staging'] = df.to_dict('records')
                    acciones_ui.append({"action": "refresh_table"})
                    texto_final = f"Regla '{args.get('razon')}' creada."
                    messages.append({"tool_call_id": tool.id, "role": "tool", "name": fname, "content": "OK"})

                elif fname == "limpiar_filtros":
                    acciones_ui.append({"action": "clear_filters"})
                    texto_final = "Limpiado."
                    messages.append({"tool_call_id": tool.id, "role": "tool", "name": fname, "content": "OK"})

                elif fname == "analizar_anomalias":
                    acciones_ui.append({"action": "trigger_anomalies"})
                    texto_final = "Analizando..."
                    messages.append({"tool_call_id": tool.id, "role": "tool", "name": fname, "content": "OK"})

            if necesita_segundo_turno:
                segunda_respuesta = llamar_openai_con_retry(messages=messages, tools=tools, tool_choice="none", temperature=0.5)
                texto_final = segunda_respuesta.choices[0].message.content

        return texto_final or "Hecho.", acciones_ui

    except Exception as e:
        return f"Error IA: {str(e)}", [] 