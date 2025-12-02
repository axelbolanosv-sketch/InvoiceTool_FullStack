# modules/translator.py
# (Modificado v17.2 para añadir claves de limpieza de duplicados)
# (Modificado v17.3 para añadir clave de eliminación masiva)
# (Modificado v17.4 para añadir claves de Buscar y Reemplazar)
# (Modificado v17.4.1 para añadir claves de botones faltantes)

# Diccionario de traducciones
LANGUAGES = {
    "es": {
        "title": "Buscador de Facturas Dinámico",
        "subtitle": "Cargue CUALQUIER archivo Excel (.xlsx) y añada múltiples filtros.",
        "lang_selector": "Idioma",
        "control_area": "Área de Control",
        "uploader_label": "Cargue su archivo de facturas",
        "add_filter_header": "Añadir Filtro",
        "column_select": "Seleccione una columna:",
        "search_text": "Texto a buscar (coincidencia parcial)",
        "add_filter_button": "Añadir Filtro",
        "warning_no_filter": "Debe seleccionar una columna y escribir un valor.",
        "active_filters_header": "Filtros Activos",
        "no_filters_applied": "No hay filtros aplicados. Se muestra la tabla completa.",
        "filter_display": "Columna **{columna}** contiene **'{valor}'**",
        "remove_button": "Quitar",
        "clear_all_button": "Limpiar todos los filtros",
        "results_header": "Resultados ({num_filas} filas encontradas)",
        "download_button": "Descargar resultados como JSON",
        "error_critical": "Error Crítico al procesar el archivo: {e}",
        "error_corrupt": "El archivo puede estar corrupto o tener un formato inesperado.",
        "info_upload": "Por favor, cargue un archivo .xlsx para comenzar.",
        "error_missing_cols": "Error: No se pudieron encontrar las columnas requeridas.",
        "warning_missing_cols": "El script esperaba: **{columnas}**",
        "info_check_excel": "Asegúrese de que su Excel tenga columnas que se parezcan a 'Emisor', 'Código Factura', 'Monto', y 'Fecha'.",
        "info_headers_found": "Encabezados encontrados en el archivo (antes de normalizar):",
        "visible_columns_header": "Columnas visibles",
        "check_all_button": "Marcar todas",
        "uncheck_all_button": "Desmarcar todas",
        "summary_header": "Resumen de la Búsqueda",
        "summary_total_invoices": "Total de Facturas",
        "summary_total_amount": "Monto Total Filtrado",
        "summary_avg_amount": "Monto Promedio",
        "view_type_header": "Tipo de Vista",
        "view_type_detailed": "Vista Detallada",
        "view_type_grouped": "Vista Agrupada",
        "group_by_select": "Agrupar por:",
        "group_by_placeholder": "Seleccione una columna para agrupar",
        "group_total_amount": "Monto Total",
        "group_avg_amount": "Monto Promedio",
        "group_min_amount": "Monto Mínimo",
        "group_max_amount": "Monto Máximo",
        "group_invoice_count": "Conteo de Facturas",
        "manage_lists_header": "4. Administrar Listas",
        "manage_lists_button": "Editar Listas de Autocompletado",
        
        # --- (INICIO - LÍNEAS v17.1) ---
        "data_cleaning_header": "Limpieza de Datos",
        "data_cleaning_desc": "Acciones específicas para limpiar facturas duplicadas (basado en 'Invoice #').",
        "btn_show_duplicates": "Mostrar Solo Duplicados",
        "btn_cleanup_duplicates": "Limpiar Duplicados (Mantener 1ro)",
        # --- (FIN - LÍNEAS v17.1) ---

        # --- (INICIO - LÍNEA v17.3) ---
        "btn_bulk_delete": "Eliminar",
        # --- (FIN - LÍNEA v17.3) ---

        # --- (INICIO - LÍNEAS v17.4) ---
        "btn_find_replace": "Buscar y Reemplazar...",
        "find_replace_modal_title": "Buscar y Reemplazar en Selección",
        "find_replace_find_label": "Buscar Texto (Coincidencia Exacta):",
        "find_replace_replace_label": "Reemplazar con:",
        "find_replace_apply_btn": "Aplicar Reemplazo",
        # --- (FIN - LÍNEAS v17.4) ---
        
        # --- (INICIO - NUEVAS LÍNEAS v17.4.1) ---
        "btn_bulk_edit": "Editar",
        "btn_undo": "Deshacer"
        # --- (FIN - NUEVAS LÍNEAS v17.4.1) ---
    },
    "en": {
        "title": "Dynamic Invoice Search",
        "subtitle": "Upload ANY Excel file (.xlsx) and add multiple filters.",
        "lang_selector": "Language",
        "control_area": "Control Panel",
        "uploader_label": "Upload your invoice file",
        "add_fsilter_header": "Add Filter",
        "column_select": "Select a column:",
        "search_text": "Text to search (partial match)",
        "add_filter_button": "Add Filter",
        "warning_no_filter": "You must select a column and enter a value.",
        "active_filters_header": "Active Filters",
        "no_filters_applied": "No filters applied. Showing full table.",
        "filter_display": "Column **{columna}** contains **'{valor}'**",
        "remove_button": "Remove",
        "clear_all_button": "Clear All Filters",
        "results_header": "Results ({num_filas} rows found)",
        "download_button": "Download results as JSON",
        "error_critical": "Critical Error while processing file: {e}",
        "error_corrupt": "The file might be corrupt or in an unexpected format.",
        "info_upload": "Please upload an .xlsx file to begin.",
        "error_missing_cols": "Error: Could not find the required columns.",
        "warning_missing_cols": "The script expected: **{columnas}**",
        "info_check_excel": "Please ensure your Excel file has columns similar to 'Vendor Name', 'Invoice #', 'Total', and 'Invoice Date'.",
        "info_headers_found": "Headers found in file (before normalization):",
        "visible_columns_header": "Visible Columns",
        "check_all_button": "Check All",
        "uncheck_all_button": "Uncheck All",
        "summary_header": "Search Summary",
        "summary_total_invoices": "Total Invoices",
        "summary_total_amount": "Total Amount Filtered",
        "summary_avg_amount": "Average Amount",
        "view_type_header": "View Type",
        "view_type_detailed": "Detailed View",
        "view_type_grouped": "Grouped View",
        "group_by_select": "Group by:",
        "group_by_placeholder": "Select a column to group by",
        "group_total_amount": "Total Amount",
        "group_avg_amount": "Average Amount",
        "group_min_amount": "Minimum Amount",
        "group_max_amount": "Maximum Amount",
        "group_invoice_count": "Invoice Count",
        "manage_lists_header": "4. Manage Lists",
        "manage_lists_button": "Edit Autocomplete Lists",
        
        # --- (INICIO - LÍNEAS v17.1) ---
        "data_cleaning_header": "Data Cleaning",
        "data_cleaning_desc": "Specific actions to clean duplicate invoices (based on 'Invoice #').",
        "btn_show_duplicates": "Show Duplicates Only",
        "btn_cleanup_duplicates": "Cleanup Duplicates (Keep 1st)",
        # --- (FIN - LÍNEAS v17.1) ---

        # --- (INICIO - LÍNEA v17.3) ---
        "btn_bulk_delete": "Delete",
        # --- (FIN - LÍNEA v17.3) ---
        
        # --- (INICIO - LÍNEAS v17.4) ---
        "btn_find_replace": "Find and Replace...",
        "find_replace_modal_title": "Find and Replace in Selection",
        "find_replace_find_label": "Find Text (Exact Match):",
        "find_replace_replace_label": "Replace with:",
        "find_replace_apply_btn": "Apply Replacement",
        # --- (FIN - NUEBAS LÍNEAS v17.4) ---
        
        # --- (INICIO - NUEVAS LÍNEAS v17.4.1) ---
        "btn_bulk_edit": "Edit",
        "btn_undo": "Undo"
        # --- (FIN - NUEVAS LÍNEAS v17.4.1) ---
    }
}

def get_text(language, key):
    """
    Obtiene el texto traducido para una clave y un idioma dados.
    Si no se encuentra, devuelve la clave misma.
    """
    return LANGUAGES.get(language, {}).get(key, key)