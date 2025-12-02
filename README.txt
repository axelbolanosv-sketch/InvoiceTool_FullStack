# Proyecto: Buscador y Editor de Facturas Inteligente (AI-Powered)
## VERSIÓN: 12.0 (Agente IA, Azure GPT-4.1, Auditoría y Automatización)

***

## 1. DESCRIPCIÓN GENERAL

Esta es una plataforma web avanzada de análisis y gestión de datos construida con **Flask (Python)**, **JavaScript puro (Tabulator.js)** y potenciada por **Inteligencia Artificial (Azure OpenAI)**. 

Transforma un flujo de trabajo manual en Excel en una experiencia interactiva donde el usuario puede dialogar con sus datos. El sistema permite no solo filtrar y editar, sino ejecutar acciones complejas (borrado masivo, detección de anomalías, creación de reglas) mediante lenguaje natural.

***

## 2. FUNCIONALIDADES CLAVE

### A. AGENTE DE INTELIGENCIA ARTIFICIAL (NUEVO) 🤖
Un copiloto integrado (Chatbot Flotante) conectado a **GPT-4.1 (Preview)** que actúa como operador del sistema:
* **Análisis de Datos ("Ojos"):** Puede leer muestras reales de los datos cargados para detectar patrones de fraude, resumir gastos por proveedor o encontrar errores semánticos.
* **Ejecución de Acciones ("Manos"):**
    * **Filtros Naturales:** *"Muéstrame solo las facturas de Amazon mayores a $500"*.
    * **Gestión de Vistas:** *"Oculta las columnas de fechas e IDs"*.
    * **Borrado Quirúrgico:** *"Borra la fila número 15"* (Realiza scroll, selecciona y pide confirmación).
    * **Borrado Masivo:** *"Elimina todo lo que sea de Uber"* (Prepara el filtro y selección para confirmación).
* **Creación de Reglas:** *"Si el proveedor es Microsoft, pon prioridad Alta"*. (Programa la lógica automáticamente).

### B. CARGA Y VISUALIZACIÓN
* **Carga de Archivos:** Soporte para archivos `.xlsx` grandes con validación automática de integridad.
* **Tabla Interactiva:** Renderizado con **Tabulator.js (v5.6)**. Soporta ordenamiento, movilización de columnas y congelado de paneles.
* **Semáforo de Conexión:** Indicador visual de estado del backend y servicios de IA.

### C. FILTRADO Y ANÁLISIS
* **Lógica de Filtro Avanzada:** Motor de filtros acumulativos (AND/OR) manuales o vía IA.
* **Detección de Anomalías:** Algoritmo estadístico (Z-Score) que identifica desviaciones en los montos y genera un reporte visual con barra de riesgo.
* **KPIs Dinámicos:** Tarjetas de resumen (Total Facturas, Monto, Promedio) que reaccionan en tiempo real a filtros y ediciones.
* **Vista Agrupada (Pivot):** Generación instantánea de tablas dinámicas con sumatorias y conteos.

### D. EDICIÓN Y GESTIÓN DE DATOS
* **Arquitectura de "Borrador":** Los cambios ocurren en una capa temporal (`df_staging`) y no afectan el archivo original hasta que se exporta.
* **CRUD Completo:** Edición de celdas (doble clic), añadir filas vacías y eliminación de filas.
* **Historial de Deshacer (Undo):** Pila LIFO de 15 niveles. Permite revertir ediciones, borrados (restaurando posición original) y cambios masivos.
* **Edición Masiva:** Herramientas para "Buscar y Reemplazar" o "Editar en Bloque" múltiples filas seleccionadas.

### E. PERSONALIZACIÓN Y PERSISTENCIA
* **Reglas de Negocio:** Motor de reglas (`priority_manager.py`) que asigna prioridades (Alta/Media/Baja) automáticamente basado en condiciones configurables.
* **Listas de Autocompletado:** El sistema "aprende" nuevos valores ingresados y permite gestionar listas desplegables personalizadas.
* **Vistas Guardadas:** Permite exportar e importar la configuración completa del entorno (filtros, columnas visibles, reglas activas) en un archivo JSON.

***

## 3. ARQUITECTURA TÉCNICA

El sistema sigue un patrón **MVC Híbrido** con un "Cerebro" de IA desacoplado.

### A. Backend (Python/Flask):
* **`app.py`:** Controlador principal. Gestiona rutas HTTP, sesión de usuario y orquesta los módulos.
* **`modules/llm_agent.py` (El Cerebro):**
    * Gestiona la conexión segura con **Azure OpenAI**.
    * Define las "Herramientas" (Function Calling) que la IA puede usar.
    * Implementa lógica de "Doble Turno" para leer datos y responder en el mismo ciclo.
    * Utiliza `tenacity` para manejo robusto de errores y reintentos (Rate Limits).
* **`modules/priority_manager.py`:** Motor de evaluación de reglas lógicas.
* **`modules/analytics.py`:** Motor matemático (NumPy/Pandas) para detección de outliers.

### B. Frontend (JavaScript/HTML/CSS):
* **`script.js` (El Sistema Nervioso):**
    * Escucha eventos del usuario Y órdenes de la IA (ej: `delete_single_row_trigger`).
    * Manipula el DOM y la instancia de Tabulator en tiempo real.
* **`index.html`:** Estructura semántica con contenedores modales y widget de chat flotante.
* **`style.css`:** Diseño responsivo, limpio y profesional.

### C. Seguridad y Datos:
* **Variables de Entorno (`.env`):** Las claves de API y Endpoints de Azure están protegidos fuera del código fuente.
* **Aislamiento de Sesión:** Cada usuario tiene un ID de sesión único (`uuid`); los datos de un usuario nunca se cruzan con los de otro.
* **Limpieza Automática:** Los archivos subidos se procesan y eliminan del disco inmediatamente, viviendo solo en la memoria de sesión.

***

## 4. INSTALACIÓN Y EJECUCIÓN

### Requisitos Previos
* Python 3.9+
* Cuenta de Azure OpenAI Service (con modelo GPT-4 o superior desplegado).

### Pasos
1.  **Clonar y preparar entorno:**
    ```bash
    git clone <repo>
    cd Mi_Nuevo_Buscador_Web
    python -m venv venv
    # Activar: .\venv\Scripts\activate (Windows) o source venv/bin/activate (Mac/Linux)
    ```

2.  **Instalar dependencias:**
    ```bash
    pip install -r requirements.txt
    ```

3.  **Configurar Seguridad:**
    Cree un archivo llamado `.env` en la raíz del proyecto y agregue sus credenciales:
    ```env
    AZURE_OPENAI_ENDPOINT="[https://su-recurso.openai.azure.com/](https://su-recurso.openai.azure.com/)"
    AZURE_OPENAI_KEY="su-clave-secreta"
    AZURE_DEPLOYMENT_NAME="gpt-4-1-preview"
    AZURE_API_VERSION="2024-05-01-preview"
    ```

4.  **Ejecutar:**
    ```bash
    python app.py
    ```
    Acceda a `http://127.0.0.1:5000` en su navegador.

***

## 5. LIBRERÍAS PRINCIPALES

* **Core:** `Flask`, `Flask-Session`, `Flask-Cors`.
* **Datos:** `pandas`, `numpy`, `openpyxl`, `xlsxwriter`.
* **IA & Cloud:** `openai` (SDK oficial), `python-dotenv`, `tenacity`.
* **Frontend:** `Tabulator.js`, `FontAwesome`.

***
Desarrollado con arquitectura modular para escalabilidad y mantenimiento.