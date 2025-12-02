"""
Módulo de Agente de IA (llm_agent.py)
-------------------------------------
Gestiona la interacción con Azure OpenAI para procesar comandos en lenguaje natural
y ejecutarlos sobre el DataFrame de facturas.

Este módulo implementa un patrón de "Function Calling" para permitir que la IA
realice acciones como filtrar, borrar filas o gestionar columnas.


"""

import os
import json
import uuid
import pandas as pd
from openai import AzureOpenAI
from flask import session
from modules.priority_manager import save_rule, apply_priority_rules
from tenacity import retry, stop_after_attempt, wait_random_exponential
from dotenv import load_dotenv

# Cargar variables de entorno desde el archivo .env
load_dotenv()

# --- CONFIGURACIÓN DE CREDENCIALES ---
AZURE_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_API_KEY = os.getenv("AZURE_OPENAI_KEY")
DEPLOYMENT_NAME = os.getenv("AZURE_DEPLOYMENT_NAME")
API_VERSION = os.getenv("AZURE_API_VERSION")

# Inicialización segura del cliente.
# Si no hay claves, el cliente será None y las funciones responderán con un aviso.
client = None
if AZURE_API_KEY and AZURE_ENDPOINT and "tu-clave" not in AZURE_API_KEY:
    try:
        client = AzureOpenAI(
            azure_endpoint=AZURE_ENDPOINT,
            api_key=AZURE_API_KEY,
            api_version=API_VERSION
        )
        print("INFO: Cliente Azure OpenAI inicializado correctamente.")
    except Exception as e:
        print(f"ADVERTENCIA: Error al conectar con Azure OpenAI: {e}")
else:
    print("ADVERTENCIA: Credenciales de Azure OpenAI no configuradas en .env. El Agente IA estará desactivado.")


# --- DEFINICIÓN DE HERRAMIENTAS (TOOLS) PARA LA IA ---
# Estas estructuras JSON definen qué puede "hacer" la IA en la interfaz.
tools = [
    {
        "type": "function",
        "function": {
            "name": "eliminar_fila_individual",
            "description": "Elimina UNA sola fila específica. Usa esto si el usuario dice 'borra la fila 5'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "numero_fila_usuario": {"type": "integer", "description": "El número visual (N°) de la fila."}
                },
                "required": ["numero_fila_usuario"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "eliminar_multiples_filas_por_numero",
            "description": "Elimina VARIAS filas por número. Ej: 'borra las filas 1, 5 y 10'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "lista_numeros": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "Lista de números visuales."
                    }
                },
                "required": ["lista_numeros"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "preparar_eliminacion_masiva",
            "description": "Filtra datos para borrado masivo. Ej: 'borra todo lo de Amazon'.",
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
    {
        "type": "function",
        "function": {
            "name": "gestionar_columnas",
            "description": "Oculta o muestra columnas en la tabla.",
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
    {
        "type": "function",
        "function": {
            "name": "eliminar_columna_permanentemente",
            "description": "ELIMINA una columna completa del dataset.",
            "parameters": {
                "type": "object",
                "properties": {
                    "columna": {"type": "string"}
                },
                "required": ["columna"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "examinar_datos_reales",
            "description": "Lee una muestra de datos para entender el contexto.",
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
            "description": "Aplica un filtro visual a la tabla.",
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
            "description": "Elimina todos los filtros activos.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "analizar_anomalias",
            "description": "Ejecuta el análisis estadístico de anomalías.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "crear_regla_prioridad",
            "description": "Crea una nueva regla de negocio persistente.",
            "parameters": {
                "type": "object",
                "properties": {
                    "condiciones": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "columna": {"type": "string"},
                                "operador": {"type": "string"},
                                "valor": {"type": "string"}
                            },
                            "required": ["columna", "operador", "valor"]
                        }
                    },
                    "prioridad": {"type": "string", "enum": ["Alta", "Media", "Baja"]},
                    "razon": {"type": "string"}
                },
                "required": ["condiciones", "prioridad", "razon"]
            }
        }
    }
]


def _generar_contexto_valores(df: pd.DataFrame) -> str:
    """
    Genera un resumen textual de los valores únicos en columnas clave.
    Ayuda a la IA a entender qué datos contiene el archivo (ej. nombres de proveedores).

    Args:
        df (pd.DataFrame): DataFrame con los datos actuales.

    Returns:
        str: Texto formateado con ejemplos de valores.
    """
    if df.empty:
        return ""
    
    cols_interes = ['Vendor Name', 'Assignee', 'Status', 'Pay Group']
    contexto = []
    
    for col in cols_interes:
        if col in df.columns:
            # Obtener hasta 20 valores únicos para dar contexto sin saturar el token limit
            unicos = df[col].dropna().astype(str).unique()
            ejemplos = ", ".join(unicos[:20])
            contexto.append(f"- '{col}': {ejemplos}...")
            
    return "\n".join(contexto)


@retry(wait=wait_random_exponential(min=1, max=60), stop=stop_after_attempt(3))
def llamar_openai_con_retry(messages: list, tools=None, tool_choice="auto", temperature=0.3):
    """
    Wrapper para llamar a la API de OpenAI con lógica de reintento automático.
    
    Args:
        messages (list): Historial de conversación.
        tools (list, optional): Definiciones de funciones disponibles.
        tool_choice (str, optional): Estrategia de selección de herramientas.
        temperature (float, optional): Creatividad del modelo.

    Returns:
        ChatCompletion: Respuesta de la API.
    """
    if not client:
        raise Exception("Cliente Azure OpenAI no inicializado.")
        
    return client.chat.completions.create(
        model=DEPLOYMENT_NAME,
        messages=messages,
        tools=tools,
        tool_choice=tool_choice,
        temperature=temperature
    )


def procesar_mensaje_ia(mensaje_usuario: str, df_staging: pd.DataFrame) -> tuple[str, list]:
    """
    Procesa un mensaje del usuario utilizando el LLM y determina acciones a realizar en la UI.

    Args:
        mensaje_usuario (str): Texto ingresado por el usuario en el chat.
        df_staging (pd.DataFrame): Datos actuales en sesión para dar contexto.

    Returns:
        tuple[str, list]: 
            - str: Respuesta textual para el usuario.
            - list: Lista de diccionarios con acciones para el Frontend (ej. {'action': 'add_filter'...}).
    """
    # 1. Verificación de Seguridad: Si no hay cliente, abortar con mensaje amigable.
    if not client:
        return (
            "⚠️ La IA no está configurada. Por favor, verifica las variables AZURE_OPENAI_KEY en el archivo .env.",
            []
        )

    # 2. Construcción del Contexto (System Prompt)
    info_columnas = ""
    info_valores = ""
    if not df_staging.empty:
        info_columnas = f"Columnas disponibles: {', '.join(df_staging.columns.tolist())}."
        info_valores = _generar_contexto_valores(df_staging)

    messages = [
        {"role": "system", "content": f"""
        Eres un copiloto experto en análisis de datos de facturación.
        Tu objetivo es ayudar al usuario a filtrar, limpiar y entender sus datos Excel.
        
        CONTEXTO DE DATOS:
        {info_columnas}
        
        MUESTRA DE VALORES:
        {info_valores}
        
        INSTRUCCIONES CLAVE:
        1. Para borrar una lista de números (ej: "1, 2 y 3"), USA 'eliminar_multiples_filas_por_numero'.
        2. Para borrar por condición (ej: "las de Amazon"), USA 'preparar_eliminacion_masiva'.
        3. Para borrar UNA fila, USA 'eliminar_fila_individual'.
        4. Sé conciso y profesional.
        """},
        {"role": "user", "content": mensaje_usuario}
    ]

    try:
        # 3. Primera llamada al modelo (Pensamiento)
        response = llamar_openai_con_retry(messages=messages, tools=tools, temperature=0.3)
        msg = response.choices[0].message
        
        acciones_ui = []
        texto_final = msg.content
        
        # 4. Manejo de llamadas a herramientas (Tool Calls)
        if msg.tool_calls:
            messages.append(msg) # Añadir la respuesta del asistente al historial
            necesita_segundo_turno = False

            for tool in msg.tool_calls:
                fname = tool.function.name
                args = json.loads(tool.function.arguments)
                
                # --- Mapeo de Herramientas a Acciones de UI ---
                
                if fname == "eliminar_multiples_filas_por_numero":
                    numeros = args.get("lista_numeros", [])
                    # Convertir a IDs internos (base 0)
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

                elif fname == "eliminar_columna_permanentemente":
                    acciones_ui.append({"action": "delete_column_trigger", "columna": args.get("columna")})
                    texto_final = f"Solicitando borrado de la columna {args.get('columna')}..."
                    messages.append({"tool_call_id": tool.id, "role": "tool", "name": fname, "content": "OK"})

                elif fname == "gestionar_columnas":
                    acciones_ui.append({
                        "action": "manage_columns", 
                        "mode": args.get("accion"), 
                        "columns": args.get("columnas")
                    })
                    texto_final = f"Ajustando visibilidad de columnas..."
                    messages.append({"tool_call_id": tool.id, "role": "tool", "name": fname, "content": "OK"})

                elif fname == "preparar_eliminacion_masiva":
                    acciones_ui.append({
                        "action": "prepare_bulk_delete", 
                        "columna": args.get("columna"), 
                        "valor": args.get("valor"), 
                        "operador": args.get("operador", "contains")
                    })
                    texto_final = f"Filtrando registros para eliminación..."
                    messages.append({"tool_call_id": tool.id, "role": "tool", "name": fname, "content": "OK"})

                elif fname == "examinar_datos_reales":
                    # Esta herramienta es especial: devuelve datos al LLM, no a la UI.
                    limite = args.get("filas_maximas", 50) 
                    datos_csv = df_staging.head(limite).to_csv(index=False)
                    messages.append({
                        "tool_call_id": tool.id, 
                        "role": "tool", 
                        "name": fname, 
                        "content": f"MUESTRA DE DATOS:\n{datos_csv}"
                    })
                    necesita_segundo_turno = True
                
                elif fname == "filtrar_datos":
                    acciones_ui.append({
                        "action": "add_filter", 
                        "columna": args.get("columna"), 
                        "valor": args.get("valor")
                    })
                    texto_final = f"Aplicando filtro: {args.get('columna')} contiene '{args.get('valor')}'."
                    messages.append({"tool_call_id": tool.id, "role": "tool", "name": fname, "content": "OK"})

                elif fname == "crear_regla_prioridad":
                    # Esta lógica se ejecuta en el backend, no solo en UI.
                    condiciones_internas = []
                    if "condiciones" in args:
                        for cond in args["condiciones"]:
                            condiciones_internas.append({
                                "column": cond.get("columna"), 
                                "operator": cond.get("operador"), 
                                "value": cond.get("valor")
                            })
                    
                    nueva_regla = {
                        "id": str(uuid.uuid4()), 
                        "active": True, 
                        "priority": args.get("prioridad"), 
                        "reason": args.get("razon"), 
                        "conditions": condiciones_internas
                    }
                    
                    # Guardamos la regla usando el módulo de lógica
                    save_rule(nueva_regla)
                    
                    # Re-aplicar reglas a los datos en sesión
                    if session.get('df_staging'):
                        df = pd.DataFrame.from_records(session['df_staging'])
                        df = apply_priority_rules(df)
                        session['df_staging'] = df.to_dict('records')
                    
                    acciones_ui.append({"action": "refresh_table"})
                    texto_final = f"Regla '{args.get('razon')}' creada y aplicada correctamente."
                    messages.append({"tool_call_id": tool.id, "role": "tool", "name": fname, "content": "OK"})

                elif fname == "limpiar_filtros":
                    acciones_ui.append({"action": "clear_filters"})
                    texto_final = "Filtros limpiados."
                    messages.append({"tool_call_id": tool.id, "role": "tool", "name": fname, "content": "OK"})

                elif fname == "analizar_anomalias":
                    acciones_ui.append({"action": "trigger_anomalies"})
                    texto_final = "Ejecutando análisis de anomalías..."
                    messages.append({"tool_call_id": tool.id, "role": "tool", "name": fname, "content": "OK"})

            # 5. Segundo turno (si la IA necesita hablar después de ejecutar la herramienta)
            if necesita_segundo_turno:
                segunda_respuesta = llamar_openai_con_retry(
                    messages=messages, tools=tools, tool_choice="none", temperature=0.5
                )
                texto_final = segunda_respuesta.choices[0].message.content

        return texto_final or "Hecho.", acciones_ui

    except Exception as e:
        print(f"ERROR EN AGENTE IA: {e}")
        return f"Lo siento, ocurrió un error al procesar tu solicitud: {str(e)}", []