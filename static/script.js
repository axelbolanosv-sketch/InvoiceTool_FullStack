/**
 * ============================================================================
 * SCRIPT.JS - CONTROLADOR PRINCIPAL DEL CLIENTE (Versión 12.0 - Fix Global Modales)
 * ============================================================================
 * Incluye:
 * - Lógica de Tabulator
 * - Gestión de Archivos
 * - Filtros con Autocompletado Dinámico
 * - Eliminación individual de filtros
 * - Chatbot, Reglas y Modales (FIX CIERRE)
 */

// ============================================================================
// 1. VARIABLES GLOBALES & CONFIGURACIÓN
// ============================================================================

let currentFileId = null;
let currentData = [];
let tableData = [];
let undoHistoryCount = 0;
let currentView = 'detailed'; 

let todasLasColumnas = [];
let columnasVisibles = [];
const COLUMNAS_AGRUPABLES = [
    "Vendor Name", "Status", "Assignee", 
    "Operating Unit Name", "Pay Status", "Document Type", 
    "_row_status", "_priority", 
    "Pay group", "WEC Email Inbox", "Sender Email", "Currency Code", "payment method"
];

let tabulatorInstance = null;
let groupedTabulatorInstance = null;
let duplicatesTabulator = null; 

let i18n = {}; 
let activeFilters = []; 
let autocompleteOptions = {};
let systemSettings = {
    enable_scf_intercompany: true,
    enable_age_sort: true
};


// ============================================================================
// 2. SERVICIOS UI & UTILIDADES
// ============================================================================

async function loadTranslations() {
    try {
        const response = await fetch('/api/get_translations');
        if (!response.ok) throw new Error('Error de red');
        i18n = await response.json();
    } catch (error) { 
        console.error('Error cargando traducciones:', error); 
        i18n = {}; 
    }
    updateDynamicText();
}

async function setLanguage(langCode) {
    try { 
        await fetch(`/api/set_language/${langCode}`); 
        location.reload();
    } catch (error) { console.error('Error cambio idioma:', error); }
}

function updateDynamicText() {
    const valInput = document.getElementById('input-valor');
    const searchTableInput = document.getElementById('input-search-table');
    const resultsTableDiv = document.getElementById('results-table');
    const resultsTableGrouped = document.getElementById('results-table-grouped');

    if (valInput) valInput.placeholder = i18n['search_text'] || "Texto a buscar...";
    if (searchTableInput) searchTableInput.placeholder = (i18n['search_text'] || "Buscar...") + "... (Hotkey: F)";
    
    const emptyMsg = `<p>${i18n['info_upload'] || 'Upload file'}</p>`;
    if (resultsTableDiv && !tabulatorInstance && !currentFileId) resultsTableDiv.innerHTML = emptyMsg;
    if (resultsTableGrouped && !groupedTabulatorInstance && !currentFileId) resultsTableGrouped.innerHTML = emptyMsg;
}

function updateResumenCard(resumen_data) {
    if (!resumen_data) return; 
    const setTxt = (id, val) => { const el = document.getElementById(id); if(el) el.textContent = val; };
    setTxt('resumen-total-facturas', resumen_data.total_facturas);
    setTxt('resumen-monto-total', resumen_data.monto_total);
    setTxt('resumen-monto-promedio', resumen_data.monto_promedio);
}

function resetResumenCard() {
    updateResumenCard({ total_facturas: '0', monto_total: '$0.00', monto_promedio: '$0.00' });
}

function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    
    let icon = '<i class="fas fa-info-circle"></i>';
    if (type === 'success') icon = '<i class="fas fa-check-circle" style="color:var(--success)"></i>';
    if (type === 'error') icon = '<i class="fas fa-exclamation-circle" style="color:var(--danger)"></i>';
    if (type === 'warning') icon = '<i class="fas fa-exclamation-triangle" style="color:var(--warning)"></i>';

    toast.innerHTML = `<div style="display:flex; align-items:center; gap:10px;">${icon}<span style="font-weight:500;">${message}</span></div>`;
    
    container.appendChild(toast);
    setTimeout(() => {
        toast.classList.add('hide');
        toast.addEventListener('animationend', () => toast.remove());
    }, 3500);
}

function showConfirm(title, message) {
    return new Promise((resolve) => {
        document.getElementById('confirm-title').innerText = title;
        document.getElementById('confirm-msg').innerText = message;
        
        const modal = document.getElementById('custom-confirm-modal');
        const overlay = document.getElementById('modal-overlay');
        if (modal) modal.style.display = 'flex';
        if (overlay) overlay.style.display = 'flex';

        const btnYes = document.getElementById('btn-confirm-yes');
        const btnNo = document.getElementById('btn-confirm-no');

        const cleanup = () => {
            if (btnYes) btnYes.replaceWith(btnYes.cloneNode(true));
            if (btnNo) btnNo.replaceWith(btnNo.cloneNode(true));
            if (modal) modal.style.display = 'none';
            
            // Revisa si hay otros modales abiertos para mantener el overlay
            const otherModals = document.querySelectorAll('[id$="-modal"]');
            let anyVisible = false;
            otherModals.forEach(m => { 
                if((m.style.display === 'flex' || m.style.display === 'block') && m.id !== 'custom-confirm-modal') anyVisible = true; 
            });
            
            if (!anyVisible && overlay) overlay.style.display = 'none';
        };

        if(document.getElementById('btn-confirm-yes')) 
            document.getElementById('btn-confirm-yes').onclick = () => { cleanup(); resolve(true); };
        
        if(document.getElementById('btn-confirm-no'))
            document.getElementById('btn-confirm-no').onclick = () => { cleanup(); resolve(false); };
    });
}

// --- Utilidades de Modales ---
function closeModal(id) {
    // Cerramos el overlay principal
    const overlay = document.getElementById('modal-overlay');
    if(overlay) overlay.style.display = 'none';
    
    // Cerramos el modal específico
    const el = document.getElementById(id);
    if(el) el.style.display = 'none';
}

function openModal(id, initFunc = null) {
    // Cerrar otros modales preventivamente
    const allModals = document.querySelectorAll('[id$="-modal"]');
    allModals.forEach(m => {
        if(m.id !== id) m.style.display = 'none';
    });

    const overlay = document.getElementById('modal-overlay');
    if(overlay) overlay.style.display = 'flex';
    
    const target = document.getElementById(id);
    if(target) {
        target.style.display = 'flex';
        if(initFunc) initFunc();
    } else {
        console.error("Modal no encontrado: " + id);
    }
}


// ============================================================================
// 3. GESTIÓN DE ARCHIVOS (UPLOAD/DOWNLOAD)
// ============================================================================

async function handleFileUpload(event) {
    const file = event.target.files[0]; if (!file) return;
    const fileUploadList = document.getElementById('file-upload-list');
    const fileSizeMB = (file.size / (1024 * 1024)).toFixed(1);
    
    fileUploadList.innerHTML = `
        <div class="file-list-item">
            <svg class="file-icon" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" /></svg>
            <div class="file-details"><span class="file-name">${file.name}</span><span class="file-size">${fileSizeMB}MB</span></div>
        </div>`;    

    const formData = new FormData(); formData.append('file', file);
    try {
        const response = await fetch('/api/upload', { method: 'POST', body: formData });
        const result = await response.json(); if (!response.ok) throw new Error(result.error);

        if (tabulatorInstance) { tabulatorInstance.destroy(); tabulatorInstance = null; }
        if (groupedTabulatorInstance) { groupedTabulatorInstance.destroy(); groupedTabulatorInstance = null; }

        currentFileId = result.file_id;
        todasLasColumnas = result.columnas; 
        columnasVisibles = [...todasLasColumnas];
        autocompleteOptions = result.autocomplete_options || {};
        
        populateColumnDropdowns(); 
        renderColumnSelector(); 
        updateVisibleColumnsFromCheckboxes();
        resetResumenCard(); 
        
        activeFilters = []; 
        document.getElementById('input-search-table').value = ''; 
        undoHistoryCount = 0; 
        updateActionButtonsVisibility(); 
        toggleView('detailed', true); 
        
        showToast("Archivo cargado exitosamente.", "success");

    } catch (error) { 
        console.error('Error Upload:', error); 
        fileUploadList.innerHTML = `<p style="color: red;">Error al cargar el archivo.</p>`;
        showToast("Error al cargar archivo: " + error.message, "error");
    }
}

async function handleDownloadExcel() {
    if (!currentFileId) { showToast(i18n['no_data_to_download'] || "No hay datos.", "warning"); return; }
    const colsToDownload = columnasVisibles.filter(col => col !== 'Priority');
    try {
        const response = await fetch('/api/download_excel', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ file_id: currentFileId, filtros_activos: activeFilters, columnas_visibles: colsToDownload })
        });
        if (!response.ok) throw new Error('Error servidor');
        const blob = await response.blob(); 
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a'); 
        a.href = url; a.download = 'datos_filtrados_detallado.xlsx';
        document.body.appendChild(a); a.click(); document.body.removeChild(a); 
        URL.revokeObjectURL(url);
        showToast("Descarga iniciada.", "success");
    } catch (error) { showToast('Error descarga: ' + error.message, "error"); }
}

async function handleDownloadExcelGrouped() {
    const select = document.getElementById('select-columna-agrupar');
    const colAgrupar = select ? select.value : null;
    if (!currentFileId || !colAgrupar) { showToast("Seleccione columna para agrupar.", "warning"); return; }
    try {
        const response = await fetch('/api/download_excel_grouped', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ file_id: currentFileId, filtros_activos: activeFilters, columna_agrupar: colAgrupar })
        });
        if (!response.ok) throw new Error('Error servidor');
        const blob = await response.blob(); 
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a'); 
        a.href = url; a.download = `datos_agrupados_por_${colAgrupar}.xlsx`;
        document.body.appendChild(a); a.click(); document.body.removeChild(a); 
        URL.revokeObjectURL(url);
        showToast("Descarga agrupada iniciada.", "success");
    } catch (error) { showToast('Error descarga: ' + error.message, "error"); }
}

async function handleDownloadAuditLog() {
    if (!currentFileId) { showToast(i18n['no_data_to_download'] || "No hay datos.", "warning"); return; }
    try {
        const response = await fetch('/api/download_audit_log', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ file_id: currentFileId })
        });
        if (!response.ok) throw new Error('Error servidor');
        const blob = await response.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url; a.download = 'reporte_auditoria_sesion.txt';
        document.body.appendChild(a); a.click(); document.body.removeChild(a);
        URL.revokeObjectURL(url);
        showToast("Auditoría descargada.", "success");
    } catch (error) { showToast('Error descarga reporte: ' + error.message, "error"); }
}


// ============================================================================
// 4. MOTOR DE TABLAS (TABULATOR)
// ============================================================================

function renderTable(data = null, forceClear = false) {
    const resultsTableDiv = document.getElementById('results-table');
    if (!resultsTableDiv) return; 

    if (forceClear && tabulatorInstance) { tabulatorInstance.destroy(); tabulatorInstance = null; }
    
    const dataToRender = data || tableData;

    if (!currentFileId) { 
        if (tabulatorInstance) { tabulatorInstance.destroy(); tabulatorInstance = null; }
        resultsTableDiv.innerHTML = `<p>${i18n['info_upload'] || 'Upload file'}</p>`; 
        return; 
    }
    
    const dateColumns = new Set(["Invoice Date", "Intake Date", "Assigned Date", "Due Date", "Terms Date", "GL Date", "Updated Date", "Batch Matching Date"]);
    
    const handleCellClick = function(e, cell) { 
        e.stopPropagation(); 
        const colDef = cell.getColumn().getDefinition();
        if (colDef.editor) {
            setTimeout(() => { cell.edit(true); }, 50);
        }
    }

    const columnDefs = [
        { formatter: "rowSelection", titleFormatter: "rowSelection", width: 40, hozAlign: "center", headerSort: false, frozen: true },
        
        {
            title: "", field: "delete", width: 40, hozAlign: "center", headerSort: false, frozen: true,
            formatter: function(cell){ return '<i class="fas fa-trash-alt delete-icon"></i>'; },
            cellClick: async function(e, cell){
                e.stopPropagation(); 
                if (!await showConfirm("Eliminar Fila", "¿Estás seguro de que deseas eliminar esta fila permanentemente?")) return; 
                handleDeleteRow(cell.getRow().getData()._row_id);
            }
        },
        { title: "N°", field: "_row_id", width: 70, hozAlign: "right", headerSort: true, frozen: true, formatter: (cell) => cell.getValue() + 1, cellClick: handleCellClick },
        {
            title: "Prioridad", field: "_priority", width: 100, hozAlign: "left", headerSort: true, editable: false, frozen: true, 
            tooltip: (e, cell) => cell.getRow().getData()._priority_reason || "Sin razón",
            sorter: function(a, b, aRow, bRow){
                const pMap = { "Alta": 3, "Media": 2, "Baja": 1, "": 0, null: 0 };
                const diff = (pMap[a] || 0) - (pMap[b] || 0);
                if (diff !== 0) return diff;
                if (systemSettings && !systemSettings.enable_age_sort) return 0;
                return (Number(aRow.getData()['Invoice Date Age']) || 0) - (Number(bRow.getData()['Invoice Date Age']) || 0);
            },
            cellClick: handleCellClick 
        }
    ];

    columnasVisibles.forEach(colName => {
        if (['_row_id', '_priority', 'Priority'].includes(colName)) return; 
        
        let editorType = "input", editorParams = {}, formatter = undefined, mutatorEdit = undefined, isEditable = true;
        
        if (colName === '_row_status') { isEditable = false; editorType = undefined; }
        else if (dateColumns.has(colName)) {
            editorType = "date";
            mutatorEdit = (v) => v ? v.split(" ")[0] : v;
            formatter = (cell) => { const v = cell.getValue(); return v ? (v.split ? v.split(" ")[0] : v) : ""; }
        }
        else if (autocompleteOptions && autocompleteOptions[colName] && autocompleteOptions[colName].length > 0) {
            const opts = autocompleteOptions[colName];
            if (opts.length > 50 || colName === 'Sender Email') {
                editorType = "autocomplete"; editorParams = { values: opts, showListOnEmpty: true, freetext: true };
            } else {
                editorType = "select"; editorParams = { values: ["", ...opts] };
            }
        }

        columnDefs.push({
            title: colName === '_row_status' ? "Row Status" : colName,
            field: colName, editor: isEditable ? editorType : undefined, editable: isEditable, 
            editorParams: editorParams, mutatorEdit: mutatorEdit, formatter: formatter, minWidth: 150, visible: true,
            cellClick: handleCellClick 
        });
    });

    if (tabulatorInstance) {
        tabulatorInstance.setColumns(columnDefs); 
        tabulatorInstance.setData(dataToRender);
    } else {
        tabulatorInstance = new Tabulator(resultsTableDiv, {
            selectable: true, 
            rowFormatter: function(row) {
                const d = row.getData();
                const rowEl = row.getElement();
                rowEl.classList.remove('priority-alta', 'priority-media', 'priority-baja');
                row.getCells().forEach(cell => {
                    const cellEl = cell.getElement();
                    const def = cell.getColumn().getDefinition();
                    cellEl.classList.remove('priority-alta', 'priority-media', 'priority-baja');
                    if (def.frozen === true) {
                        if (d._priority === 'Alta') cellEl.classList.add('priority-alta');
                        else if (d._priority === 'Media') cellEl.classList.add('priority-media');
                        else if (d._priority === 'Baja') cellEl.classList.add('priority-baja');
                    }
                });
            },
            index: "_row_id", virtualDom: true, data: dataToRender, columns: columnDefs, 
            layout: "fitData", movableColumns: true, placeholder: `<p>${i18n['info_upload'] || 'Upload file'}</p>`,
        });

        tabulatorInstance.on("rowSelectionChanged", function(data, rows){
            const btnEdit = document.getElementById('btn-bulk-edit'), btnDel = document.getElementById('btn-bulk-delete'), btnFind = document.getElementById('btn-find-replace');
            if (!btnEdit) return;
            const display = rows.length > 0 ? 'inline-block' : 'none';
            btnEdit.style.display = display; btnEdit.textContent = `${i18n['btn_bulk_edit'] || 'Editar'} (${rows.length})`;
            btnDel.style.display = display; btnDel.textContent = `${i18n['btn_bulk_delete'] || 'Eliminar'} (${rows.length})`;
            btnFind.style.display = display; btnFind.textContent = `${i18n['btn_find_replace'] || 'Buscar/Reemplazar'} (${rows.length})`;
        });

        tabulatorInstance.on("cellEdited", handleCellEdited);
    }
}

function renderGroupedTable(data, colAgrupada, forceClear = false) {
    const resultsTableDiv = document.getElementById('results-table-grouped');
    if (!resultsTableDiv) return;

    if (forceClear && groupedTabulatorInstance) { groupedTabulatorInstance.destroy(); groupedTabulatorInstance = null; }

    if (!data || data.length === 0) {
        if (groupedTabulatorInstance) { groupedTabulatorInstance.destroy(); groupedTabulatorInstance = null; }
        resultsTableDiv.innerHTML = `<p>${i18n['info_upload'] || 'Upload file & group.'}</p>`;
        return;
    }

    const headersMap = {
        [colAgrupada]: colAgrupada === '_row_status' ? "Row Status" : (colAgrupada === '_priority' ? "Prioridad" : colAgrupada),
        "Total_sum": i18n['group_total_amount'] || "Total Amount",
        "Total_mean": i18n['group_avg_amount'] || "Avg Amount",
        "Total_min": i18n['group_min_amount'] || "Min Amount",
        "Total_max": i18n['group_max_amount'] || "Max Amount",
        "Total_count": i18n['group_invoice_count'] || "Invoice Count"
    };
    
    const columnDefs = [colAgrupada, "Total_sum", "Total_mean", "Total_min", "Total_max", "Total_count"].map(key => {
        if (!headersMap[key]) return null;
        const isMoney = key.startsWith('Total_') && key !== 'Total_count';
        return {
            title: headersMap[key], field: key, minWidth: 140, hozAlign: isMoney ? "right" : "left",
            formatter: isMoney ? "money" : "string", formatterParams: isMoney ? { decimal: ".", thousand: ",", symbol: "$", precision: 2 } : {}
        };
    }).filter(Boolean);

    if (groupedTabulatorInstance) groupedTabulatorInstance.destroy();
    
    groupedTabulatorInstance = new Tabulator(resultsTableDiv, {
        data: data, columns: columnDefs, layout: "fitData", movableColumns: true, 
    });
}


// ============================================================================
// 5. FILTROS, VISTAS Y BÚSQUEDA
// ============================================================================

function updateFilterAutocomplete() {
    const colSelect = document.getElementById('select-columna');
    const dataList = document.getElementById('input-valor-list');
    const inputVal = document.getElementById('input-valor');
    
    if (!colSelect || !dataList) return;
    
    const col = colSelect.value;
    dataList.innerHTML = ''; 
    if(inputVal) inputVal.value = ''; 

    if (col && autocompleteOptions[col]) {
        autocompleteOptions[col].forEach(val => {
            const option = document.createElement('option');
            option.value = val;
            dataList.appendChild(option);
        });
    }
}

async function handleAddFilter() {
    const col = document.getElementById('select-columna').value;
    const val = document.getElementById('input-valor').value;
    
    if (col && val) { 
        activeFilters.push({ columna: col, valor: val }); 
        document.getElementById('input-valor').value = ''; 
        if (currentView === 'detailed') document.getElementById('input-search-table').value = ''; 
        await refreshActiveView();
    } else { showToast(i18n['warning_no_filter'] || 'Select col and value', "warning"); }
}

async function handleClearFilters() { 
    activeFilters = []; 
    if (currentView === 'detailed') document.getElementById('input-search-table').value = ''; 
    await refreshActiveView(); 
}

// FIX: Manejador de eventos actualizado para eliminación individual
async function handleRemoveFilter(event) {
    const btn = event.target.closest('.remove-filter-btn');
    if (!btn) return;
    
    const index = parseInt(btn.dataset.index, 10);
    activeFilters.splice(index, 1);
    await refreshActiveView(); 
}

function handleSearchTable() {
    const searchTerm = document.getElementById('input-search-table').value.toLowerCase();
    if (tabulatorInstance) {
        if (!searchTerm) tabulatorInstance.clearFilter(); 
        else tabulatorInstance.setFilter(data => columnasVisibles.some(col => 
            String(col === '_row_id' ? data[col] + 1 : data[col]).toLowerCase().includes(searchTerm)
        ));
    }
}

function renderFilters() {
    const listId = (currentView === 'detailed') ? 'active-filters-list' : 'active-filters-list-grouped';
    const clearBtnId = (currentView === 'detailed') ? 'btn-clear-filters' : 'btn-clear-filters-grouped';
    const filtersListDiv = document.getElementById(listId);
    const btnClear = document.getElementById(clearBtnId);
    
    if (filtersListDiv) filtersListDiv.innerHTML = '';
    if (btnClear) btnClear.style.display = (activeFilters.length > 0) ? 'inline-block' : 'none';
    
    if (!filtersListDiv || activeFilters.length === 0) return;
    
    activeFilters.forEach((filtro, index) => {
        let colName = filtro.columna === '_row_id' ? 'N° Fila' : (filtro.columna === '_row_status' ? 'Row Status' : (filtro.columna === '_priority' ? 'Prioridad' : filtro.columna));
        filtersListDiv.innerHTML += `
            <div class="filtro-chip">
                <span>${colName}: <strong>${filtro.valor}</strong></span>
                <button class="remove-filter-btn" data-index="${index}" style="margin-left:8px; border:none; background:transparent; cursor:pointer; font-size:1.1rem; color:#666; display:flex; align-items:center;">&times;</button>
            </div>`;
    });
}

async function getFilteredData() {
    const btnReset = document.getElementById('btn-reset-view');
    if(btnReset) btnReset.style.display = 'none';
    const resultsHeader = document.getElementById('results-header');
    if (!currentFileId) { 
        currentData = []; tableData = []; renderFilters(); renderTable(null, true); resetResumenCard(); 
        if (resultsHeader) resultsHeader.textContent = 'Results'; 
        return; 
    }
    try {
        const response = await fetch('/api/filter', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ file_id: currentFileId, filtros_activos: activeFilters })
        });
        const result = await response.json(); if (!response.ok) throw new Error(result.error);

        currentData = result.data; tableData = [...currentData];
        if (result.resumen) updateResumenCard(result.resumen);
        renderFilters(); renderTable(result.data); 

    } catch (error) { 
        console.error('Error filter:', error); showToast('Error al filtrar: ' + error.message, "error");
        resetResumenCard(); renderTable(null, true);
    }
}

function toggleView(view, force = false) {
    if (view === currentView && !force) return; 
    currentView = view;
    
    const showDetailed = (view === 'detailed');
    document.getElementById('view-container-detailed').style.display = showDetailed ? 'flex' : 'none';
    document.getElementById('view-container-grouped').style.display = showDetailed ? 'none' : 'flex';
    document.getElementById('btn-view-detailed').classList.toggle('active', showDetailed);
    document.getElementById('btn-view-grouped').classList.toggle('active', !showDetailed);
    document.getElementById('group-by-controls-wrapper').style.display = showDetailed ? 'none' : 'flex';
    
    if (!showDetailed) {
        populateGroupDropdown();
        const selectAgrupar = document.getElementById('select-columna-agrupar');
        if (selectAgrupar && !selectAgrupar.value) selectAgrupar.value = selectAgrupar.querySelector('option:not([value=""])')?.value || "";
    }
    
    refreshActiveView();
}

async function refreshActiveView() {
    if (currentView === 'detailed') {
        await getFilteredData(); 
        if (tabulatorInstance) tabulatorInstance.redraw();
    } 
    else { 
        await getGroupedData(); 
        if (groupedTabulatorInstance) groupedTabulatorInstance.redraw();
    }
    updateActionButtonsVisibility();
}

function populateGroupDropdown() {
    const select = document.getElementById('select-columna-agrupar');
    if (!select) return; 
    const val = select.value;
    select.innerHTML = `<option value="">${i18n['group_by_placeholder'] || 'Select column...'}</option>`;
    COLUMNAS_AGRUPABLES.filter(c => todasLasColumnas.includes(c) && c !== '_row_id').forEach(colName => {
        const option = document.createElement('option'); option.value = colName;
        option.textContent = colName === '_row_status' ? "Row Status" : (colName === '_priority' ? "Prioridad" : colName);
        select.appendChild(option);
    });
    if (val) select.value = val;
}

function populateColumnDropdowns() {
    const filterSelect = document.getElementById('select-columna');
    if (filterSelect) {
        filterSelect.innerHTML = `<option value="">${i18n['column_select'] || 'Select column:'}</option>`;
        todasLasColumnas.forEach(col => {
            const opt = document.createElement('option');
            opt.value = col;
            opt.textContent = col === '_row_id' ? "N° Fila" : (col === '_row_status' ? "Row Status" : (col === '_priority' ? "Prioridad" : col));
            filterSelect.appendChild(opt);
        });
    }
}

async function handleGroupColumnChange() { await getGroupedData(); }

async function getGroupedData() {
    const select = document.getElementById('select-columna-agrupar');
    if (!currentFileId || !select?.value) { renderGroupedTable(null, null, true); return; }

    try {
        document.getElementById('results-table-grouped').innerHTML = `<p>Agrupando datos...</p>`;
        const response = await fetch('/api/group_by', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ file_id: currentFileId, filtros_activos: activeFilters, columna_agrupar: select.value })
        });
        const result = await response.json(); if (!response.ok) throw new Error(result.error);
        renderGroupedTable(result.data, select.value, false); renderFilters();
    } catch (error) {
        document.getElementById('results-table-grouped').innerHTML = `<p style="color: red;">Error: ${error.message}</p>`;
    }
}

function handleFullscreen() {
    const isDetailed = currentView === 'detailed';
    const container = document.getElementById(isDetailed ? 'view-container-detailed' : 'view-container-grouped');
    const table = isDetailed ? tabulatorInstance : groupedTabulatorInstance;

    document.body.classList.toggle('fullscreen-mode');
    if(container) container.classList.toggle('in-fullscreen');
    
    const isFull = document.body.classList.contains('fullscreen-mode');
    const svg = isFull 
        ? `<path stroke-linecap="round" stroke-linejoin="round" d="M9 9V4.5M9 9H4.5M9 9L3.75 3.75M9 15v4.5M9 15H4.5M9 15l-5.25 5.25M15 9V4.5M15 9h4.5M15 9l5.25-5.25M15 15v4.5M15 15h4.5M15 15l5.25 5.25" />`
        : `<path stroke-linecap="round" stroke-linejoin="round" d="M3.75 3.75v4.5m0-4.5h4.5m-4.5 0L9 9M3.75 20.25v-4.5m0 4.5h4.5m-4.5 0L9 15M20.25 3.75h-4.5m4.5 0v4.5m0-4.5L15 9m5.25 11.25h-4.5m4.5 0v-4.5m0 4.5L15 15" />`;
    
    document.querySelectorAll('.icon-button[title*="Hotkey: G"]').forEach(btn => btn.querySelector('svg').innerHTML = svg);
    setTimeout(() => { if (table) table.redraw(true); }, 200);
}

function renderColumnSelector() {
    const wrapper = document.getElementById('column-selector-wrapper');
    if (!wrapper) return;
    wrapper.innerHTML = ''; 
    if (todasLasColumnas.length === 0) { 
        wrapper.innerHTML = `<p>${i18n['info_upload'] || 'Upload file'}</p>`; 
        return; 
    }
    
    todasLasColumnas.filter(col => !['_row_id', '_priority', '_priority_reason', 'Priority'].includes(col))
        .forEach(columnName => {
            const isChecked = columnasVisibles.includes(columnName);
            const colText = (columnName === '_row_status') ? "Row Status" : columnName;
            const itemHTML = `
                <div class="column-selector-item">
                    <label><input type="checkbox" value="${columnName}" ${isChecked ? 'checked' : ''}> ${colText}</label>
                </div>`;
            wrapper.innerHTML += itemHTML;
        });
}

function updateVisibleColumnsFromCheckboxes() {
    const checkboxes = document.querySelectorAll('#column-selector-wrapper input[type="checkbox"]');
    columnasVisibles = [];
    checkboxes.forEach(cb => { if (cb.checked) columnasVisibles.push(cb.value); });
    
    if (todasLasColumnas.includes('_row_id')) columnasVisibles.push('_row_id');
    if (todasLasColumnas.includes('_priority')) columnasVisibles.push('_priority');
    
    columnasVisibles = columnasVisibles.filter(col => col !== 'Priority');
    renderTable();
}


// ============================================================================
// 6. ACCIONES DE FILA (CRUD & UNDO)
// ============================================================================

async function handleCellEdited(cell) {
    const newVal = cell.getValue(), oldVal = cell.getOldValue(), row = cell.getRow();
    const colField = cell.getField(), rowId = row.getData()._row_id;
    const rowEl = row.getElement();

    const isDate = ["Invoice Date", "Intake Date", "Assigned Date", "Due Date"].includes(colField);
    if (isDate && (!newVal) && oldVal) { cell.restoreOldValue(); return; }
    if (newVal === oldVal) return;

    if (rowEl) rowEl.style.backgroundColor = "#FFF9E5";

    try {
        const response = await fetch('/api/update_cell', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ file_id: currentFileId, row_id: rowId, columna: colField, valor: newVal })
        });
        const result = await response.json(); if (!response.ok) throw new Error(result.error);

        if (result.resumen) updateResumenCard(result.resumen);
        undoHistoryCount = result.history_count;
        updateActionButtonsVisibility();

        if (result.new_priority) {
            row.update({_priority: result.new_priority});
        }
        if (result.new_row_status) row.update({_row_status: result.new_row_status});
        if (rowEl) { rowEl.style.backgroundColor = ""; row.reformat(); }

    } catch (error) {
        console.error("Error update cell:", error); showToast("Error guardando cambio: " + error.message, "error");
        cell.restoreOldValue(); if (rowEl) rowEl.style.backgroundColor = "";
    }
}

async function handleAddRow() {
    if (!currentFileId) { showToast("Cargue archivo primero.", "warning"); return; }
    try {
        const response = await fetch('/api/add_row', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ file_id: currentFileId })
        });
        const result = await response.json(); if (!response.ok) throw new Error(result.error);
        
        undoHistoryCount = result.history_count;
        updateActionButtonsVisibility(); 
        await getFilteredData();
        
        if (result.new_row_id && tabulatorInstance) {
            setTimeout(() => {
                tabulatorInstance.scrollToRow(result.new_row_id, "bottom", false);
                const row = tabulatorInstance.getRow(result.new_row_id);
                if (row?.getElement()) {
                    const el = row.getElement(); el.style.backgroundColor = "#FFF9E5";
                    setTimeout(() => { if(el) el.style.backgroundColor = ""; row.reformat(); }, 2000);
                }
            }, 100);
        }
    } catch (error) { showToast("Error añadir fila: " + error.message, "error"); }
}

async function handleDeleteRow(row_id) {
    if (!currentFileId) return;
    try {
        const response = await fetch('/api/delete_row', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ file_id: currentFileId, row_id: row_id })
        });
        const result = await response.json(); if (!response.ok) throw new Error(result.error);
        undoHistoryCount = result.history_count;
        updateActionButtonsVisibility(); 
        await getFilteredData();
        showToast("Fila eliminada correctamente.", "success");
    } catch (error) { showToast("Error eliminar fila: " + error.message, "error"); }
}

async function handleUndoChange() {
    if (undoHistoryCount === 0 || !currentFileId) return;
    try {
        const response = await fetch('/api/undo_change', {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, 
            body: JSON.stringify({ file_id: currentFileId }) 
        });
        const result = await response.json(); if (!response.ok) throw new Error(result.error);
        
        undoHistoryCount = result.history_count;
        updateActionButtonsVisibility(); 

        if (result.affected_row_id && result.affected_row_id !== 'bulk' && tabulatorInstance) {
            const row = tabulatorInstance.getRow(result.affected_row_id);
            if (row) tabulatorInstance.scrollToRow(row, "center", false);
        }
        await getFilteredData();
        showToast("Cambio deshecho.", "info");
    } catch (error) { showToast("Error Undo: " + error.message, "error"); }
}

async function handleCommitChanges() {
    if (undoHistoryCount === 0 || !currentFileId) return;
    if (!await showConfirm("Consolidar Cambios", "¿Consolidar cambios y limpiar historial de deshacer?")) return;
    try {
        const response = await fetch('/api/commit_changes', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ file_id: currentFileId })
        });
        const result = await response.json(); if (!response.ok) throw new Error(result.error);
        showToast(result.message, "success");
        undoHistoryCount = 0; updateActionButtonsVisibility(); 
    } catch (error) { showToast("Error Commit: " + error.message, "error"); }
}

function updateActionButtonsVisibility() {
    const show = (id, visible) => { const el = document.getElementById(id); if(el) el.style.display = visible ? 'inline-block' : 'none'; };
    const hasFile = !!currentFileId && currentView === 'detailed';
    
    show('btn-undo-change', undoHistoryCount > 0 && currentView === 'detailed');
    show('btn-commit-changes', undoHistoryCount > 0 && currentView === 'detailed');
    if (document.getElementById('btn-undo-change')) document.getElementById('btn-undo-change').textContent = `Deshacer (${undoHistoryCount})`;
    
    show('btn-add-row', hasFile);
    show('btn-download-audit-log', hasFile);
}


// ============================================================================
// 7. OPERACIONES MASIVAS (BULK)
// ============================================================================

function openBulkEditModal() {
    if (!tabulatorInstance) return;
    const rows = tabulatorInstance.getSelectedData();
    if (rows.length === 0) { showToast("Seleccione al menos una fila.", "warning"); return; }

    document.getElementById('bulk-edit-count').textContent = `Editar ${rows.length} filas.`;
    const sel = document.getElementById('bulk-edit-column');
    sel.innerHTML = '<option value="">Seleccione...</option>';
    todasLasColumnas.forEach(col => { if (!col.startsWith('_') && col !== 'Priority') sel.innerHTML += `<option value="${col}">${col}</option>`; });
    
    document.getElementById('bulk-edit-value').value = '';
    openModal('bulk-edit-modal');
}

async function handleBulkEditApply() {
    const col = document.getElementById('bulk-edit-column').value, val = document.getElementById('bulk-edit-value').value;
    if (!col) return showToast("Seleccione columna", "warning");
    const rows = tabulatorInstance.getSelectedData();
    
    if (!await showConfirm("Edición Masiva", `¿Cambiar "${col}" a "${val}" en ${rows.length} filas?`)) return;

    try {
        const response = await fetch('/api/bulk_update', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ file_id: currentFileId, row_ids: rows.map(r => r._row_id), column: col, new_value: val })
        });
        const res = await response.json(); if (!response.ok) throw new Error(res.error);
        
        showToast(res.message, "success"); undoHistoryCount = res.history_count;
        if (res.resumen) updateResumenCard(res.resumen);
        closeModal('bulk-edit-modal'); tabulatorInstance.deselectRow();
        await getFilteredData();
    } catch (e) { showToast("Error Bulk Edit: " + e.message, "error"); }
}

function openFindReplaceModal() {
    if (!tabulatorInstance) return;
    const rows = tabulatorInstance.getSelectedData();
    if (rows.length === 0) { showToast("Seleccione filas primero.", "warning"); return; }
    
    document.getElementById('find-replace-count').textContent = `En ${rows.length} filas seleccionadas.`;
    const sel = document.getElementById('find-replace-column');
    sel.innerHTML = '<option value="">Seleccione...</option>';
    todasLasColumnas.forEach(col => { if (!col.startsWith('_') && col !== 'Priority') sel.innerHTML += `<option value="${col}">${col}</option>`; });
    
    document.getElementById('find-replace-find-text').value = '';
    document.getElementById('find-replace-replace-text').value = '';
    openModal('find-replace-modal');
}

async function handleFindReplaceApply() {
    const col = document.getElementById('find-replace-column').value;
    const findT = document.getElementById('find-replace-find-text').value;
    const replT = document.getElementById('find-replace-replace-text').value;
    if (!col) return showToast("Seleccione columna", "warning");

    const rows = tabulatorInstance.getSelectedData();
    if (!await showConfirm("Buscar y Reemplazar", `Buscar "${findT}" y reemplazar con "${replT}" en ${rows.length} filas de "${col}"?`)) return;

    try {
        const response = await fetch('/api/find_replace_in_selection', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ file_id: currentFileId, row_ids: rows.map(r => r._row_id), columna: col, find_text: findT, replace_text: replT })
        });
        const res = await response.json(); if (!response.ok) throw new Error(res.error);

        showToast(res.message, "success"); undoHistoryCount = res.history_count;
        if (res.resumen) updateResumenCard(res.resumen);
        closeModal('find-replace-modal'); tabulatorInstance.deselectRow();
        await getFilteredData();
    } catch (e) { showToast("Error Find/Replace: " + e.message, "error"); }
}

async function handleBulkDelete() {
    const rows = tabulatorInstance.getSelectedData();
    if (rows.length === 0) return showToast("Seleccione filas.", "warning");
    if (!await showConfirm("Eliminar Filas", `¿Eliminar ${rows.length} filas? (Deshacer disponible)`)) return;

    try {
        const response = await fetch('/api/bulk_delete_rows', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ file_id: currentFileId, row_ids: rows.map(r => r._row_id) })
        });
        const res = await response.json(); if (!response.ok) throw new Error(res.error);

        showToast(res.message, "success"); 
        undoHistoryCount = res.history_count;
        if (res.resumen) updateResumenCard(res.resumen);
        tabulatorInstance.deselectRow(); 
        updateActionButtonsVisibility(); 
        await getFilteredData();
    } catch (e) { showToast("Error Bulk Delete: " + e.message, "error"); }
}


// ============================================================================
// 8. GESTIÓN DE DUPLICADOS & LIMPIEZA
// ============================================================================

async function handleShowDuplicates() {
    if (!currentFileId) return showToast("Cargue archivo primero.", "warning");
    
    const btn = document.getElementById('btn-show-duplicates');
    const originalText = btn.innerHTML;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Buscando...';
    btn.disabled = true;

    try {
        const response = await fetch('/api/get_duplicate_invoices', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ file_id: currentFileId })
        });
        const res = await response.json(); 
        
        btn.innerHTML = originalText;
        btn.disabled = false;

        if (!response.ok) throw new Error(res.error);
        
        if (res.num_filas > 0) {
            openModal('duplicates-modal', () => {
                const countMsg = document.getElementById('duplicates-count-msg');
                if(countMsg) countMsg.innerText = `Se encontraron ${res.num_filas} registros conflictivos.`;

                // 1. Configurar Botón de Limpieza Automática
                const btnClean = document.getElementById('btn-modal-cleanup');
                if(btnClean) {
                    btnClean.onclick = () => {
                        handleCleanupDuplicates(); 
                        closeModal('duplicates-modal'); 
                    };
                }

                // 2. Configurar Botón "Ver en Tabla Principal"
                const btnFilterMain = document.getElementById('btn-filter-duplicates-main');
                if(btnFilterMain) {
                    console.log("[DEBUG] Botón filtro duplicados encontrado.");
                    btnFilterMain.onclick = () => {
                        console.log("[DEBUG] Click en Ver en Tabla Principal");
                        closeModal('duplicates-modal');
                        
                        currentData = res.data; 
                        tableData = [...currentData];
                        
                        activeFilters = [{columna: 'MODO', valor: 'Revisión de Duplicados'}];
                        renderFilters();
                        renderTable(currentData);
                        
                        let totalDupes = 0;
                        try {
                            totalDupes = currentData.reduce((acc, row) => {
                                const val = parseFloat(String(row['Total'] || row['Monto'] || row['Amount'] || 0).replace(/[$,]/g, '')) || 0;
                                return acc + val;
                            }, 0);
                        } catch(e) {}

                        updateResumenCard({ 
                            total_facturas: res.num_filas, 
                            monto_total: `$${totalDupes.toLocaleString('en-US', {minimumFractionDigits: 2})}`, 
                            monto_promedio: "Revisión" 
                        });
                        
                        showToast("Mostrando duplicados. Usa las casillas para seleccionar y borrar.", "info");
                    };
                }

                // Renderizar tabla pequeña dentro del modal
                if (duplicatesTabulator) duplicatesTabulator.destroy();
                duplicatesTabulator = new Tabulator("#duplicates-table-container", {
                    data: res.data,
                    layout: "fitColumns",
                    height: "100%",
                    columns: [
                        {title: "Fila", field: "_row_id", width: 60, formatter: c => c.getValue() + 1},
                        {title: "Invoice #", field: "Invoice #", width: 140},
                        {title: "Vendor Name", field: "Vendor Name", width: 180},
                        {title: "Total", field: "Total", width: 100, hozAlign: "right"},
                        {title: "Fecha", field: "Invoice Date", width: 110}
                    ]
                });
            });
            showToast(`Atención: ${res.num_filas} posibles duplicados.`, "warning");
        } else {
            showToast("¡Limpio! No se encontraron duplicados.", "success");
        }
    } catch (e) { 
        btn.innerHTML = originalText;
        btn.disabled = false;
        showToast("Error Duplicados: " + e.message, "error"); 
    }
}

async function handleCleanupDuplicates() {
    if (!currentFileId) return showToast("Cargue archivo.", "warning");
    
    if (!await showConfirm("Confirmar Limpieza", "¿Eliminar duplicados automáticamente? Se conservará la primera aparición.")) return;
    
    try {
        const response = await fetch('/api/cleanup_duplicate_invoices', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ file_id: currentFileId })
        });
        const res = await response.json(); if (!response.ok) throw new Error(res.error);
        
        showToast(res.message, "success"); 
        undoHistoryCount = res.history_count;
        
        if (res.resumen) updateResumenCard(res.resumen);
        updateActionButtonsVisibility(); 
        await getFilteredData(); 
        
    } catch (e) { showToast("Error Cleanup: " + e.message, "error"); }
}

async function handleAnalyzeAnomalies() {
    if (!currentFileId) return showToast("Cargue un archivo primero.", "warning");
    
    const btn = document.getElementById('btn-analyze-anomalies');
    const originalText = btn.innerHTML;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Analizando...';
    btn.disabled = true;

    try {
        const response = await fetch('/api/analyze_anomalies', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ file_id: currentFileId })
        });
        const res = await response.json();
        
        btn.innerHTML = originalText;
        btn.disabled = false;

        if (!response.ok) throw new Error(res.message || res.error);

        openModal('anomalies-modal');
        
        const summaryEl = document.getElementById('anomalies-summary-text');
        if (res.data.length === 0) {
            summaryEl.innerHTML = `<strong>¡Todo parece normal!</strong><br>No se encontraron facturas que superen el umbral de riesgo (${res.summary.threshold}).`;
            document.getElementById('anomalies-table-container').innerHTML = "";
        } else {
            summaryEl.innerHTML = `
                Se encontraron <strong>${res.summary.count} facturas atípicas</strong>.<br>
                Superan el umbral estadístico de <strong>${res.summary.threshold}</strong> 
                (Promedio: ${res.summary.mean}).<br>
                <span style="font-size:0.8em; opacity:0.8">Basado en columna: ${res.summary.column_used}</span>
            `;
            
           new Tabulator("#anomalies-table-container", {
                data: res.data,
                layout: "fitColumns", 
                height: "100%", 
                columns: [
                    {title: "N°", field: "_row_id", width: 60, frozen:true, formatter: c => c.getValue() + 1},
                    {title: "Monto", field: res.summary.column_used, width: 130, hozAlign:"right", 
                     formatter:"money", formatterParams:{symbol:"$", precision:2, decimal:".", thousand:","}},
                    {
                        title: "Risk Score", 
                        field: "_anomaly_score", 
                        width: 140, 
                        hozAlign:"center", 
                        formatter:"progress", 
                        formatterParams:{
                            min: 0, max: 10, legend: true,
                            color: ["#22c55e", "#eab308", "#ef4444"],
                            legendColor: "#000000", legendAlign: "center"
                        }
                    },
                    {title: "Vendor", field: "Vendor Name", minWidth: 200}, 
                    {title: "Invoice #", field: "Invoice #", width: 120}
                ]
            });
        }

    } catch (e) {
        btn.innerHTML = originalText;
        btn.disabled = false;
        showToast("Error en análisis: " + e.message, "error");
    }
}


// ============================================================================
// 9. REGLAS DE NEGOCIO & AUTOCOMPLETADO
// ============================================================================

function openManageListsModal() {
    openModal('manage-lists-modal', () => {
        const sel = document.getElementById('manage-list-column');
        sel.innerHTML = '<option value="">Seleccione columna...</option>';
        const allCols = new Set([...todasLasColumnas, ...Object.keys(autocompleteOptions)]);
        const cleanCols = Array.from(allCols).filter(c => !c.startsWith('_') && c !== 'Priority').sort();

        cleanCols.forEach(col => {
            const hasAuto = autocompleteOptions[col] && autocompleteOptions[col].length > 0;
            const mark = hasAuto ? ' (Activo)' : '';
            sel.innerHTML += `<option value="${col}">${col}${mark}</option>`;
        });
        document.getElementById('manage-list-input').value = '';
        document.getElementById('current-list-values').innerHTML = '<em>Seleccione una columna arriba...</em>';
    });
}

function updateManageListsCurrentValues() {
    const col = document.getElementById('manage-list-column').value;
    const container = document.getElementById('current-list-values');
    const vals = autocompleteOptions[col];
    container.innerHTML = ''; 

    if (!col) { container.innerHTML = '<em>Seleccione una columna...</em>'; return; }
    if (!vals || vals.length === 0) { container.innerHTML = '<em>Vacío</em>'; return; }

    vals.forEach(val => {
        const chip = document.createElement('div');
        chip.className = 'value-chip';
        const textSpan = document.createElement('span');
        textSpan.textContent = val;
        chip.appendChild(textSpan);
        const icon = document.createElement('i');
        icon.className = 'fas fa-times remove-icon';
        icon.title = "Eliminar valor";
        icon.onclick = () => handleRemoveSingleValue(col, val); 
        chip.appendChild(icon);
        container.appendChild(chip);
    });
}

function handleRemoveSingleValue(col, valToRemove) {
    if (!autocompleteOptions[col]) return;
    autocompleteOptions[col] = autocompleteOptions[col].filter(v => v !== valToRemove);
    updateManageListsCurrentValues();
}

async function handleDeleteAllValues() {
    const col = document.getElementById('manage-list-column').value;
    if (!col) return showToast("Seleccione una columna.", "warning");
    if (!autocompleteOptions[col] || autocompleteOptions[col].length === 0) return showToast("La lista ya está vacía.", "info");

    if (!await showConfirm("Borrar Lista", `¿Está seguro de borrar TODOS los valores de autocompletado para "${col}"?`)) return;

    autocompleteOptions[col] = [];
    updateManageListsCurrentValues();
}

async function handleManageListsSave() {
    const col = document.getElementById('manage-list-column').value;
    const input = document.getElementById('manage-list-input').value;
    
    if (!col) return showToast("Seleccione una columna.", "warning");

    const current = new Set(autocompleteOptions[col] || []);
    if (input.trim()) {
        input.split(',').map(v => v.trim()).filter(Boolean).forEach(mod => {
            if (mod.startsWith('-')) current.delete(mod.substring(1).trim());
            else current.add(mod);
        });
    }
    autocompleteOptions[col] = Array.from(current).sort();

    try {
        await fetch('/api/save_autocomplete_lists', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(autocompleteOptions) 
        });
        renderTable(); 
        showToast("Listas guardadas correctamente.", "success"); 
        closeModal('manage-lists-modal');
    } catch (e) { showToast("Error guardar listas: " + e.message, "error"); }
}

async function handleImportAutocomplete() {
    const col = document.getElementById('manage-list-column').value;
    if (!col) return showToast("Seleccione una columna primero.", "warning");
    if (!currentFileId) return showToast("No hay archivo cargado.", "warning");

    if (!await showConfirm("Importar Valores", `¿Analizar la columna "${col}" y guardar todos sus valores únicos?`)) return;

    try {
        const btn = document.getElementById('btn-manage-import');
        const originalText = btn.innerHTML;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Procesando...';
        btn.disabled = true;

        const response = await fetch('/api/import_autocomplete_values', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ file_id: currentFileId, column: col })
        });
        const result = await response.json();
        
        btn.innerHTML = originalText;
        btn.disabled = false;

        if (!response.ok) throw new Error(result.error);

        autocompleteOptions = result.autocomplete_options;
        updateManageListsCurrentValues();
        renderTable(); 

        showToast(result.message, "success");

    } catch (error) {
        showToast("Error importando valores: " + error.message, "error");
        if (document.getElementById('btn-manage-import')) document.getElementById('btn-manage-import').disabled = false;
    }
}

// --- Priority Rules ---
async function openPriorityRulesModal() {
    openModal('priority-rules-modal', async () => {
        resetRuleForm(); 
        await loadAndRenderRules();
    });
}

async function loadAndRenderRules() {
    const container = document.getElementById('rules-list-container');
    container.innerHTML = '<em>Cargando...</em>';
    try {
        const res = await fetch('/api/priority_rules/get');
        const data = await res.json();
        renderRulesList(data.rules);
        
        systemSettings = data.settings || systemSettings;
        document.getElementById('setting-scf').checked = systemSettings.enable_scf_intercompany;
        document.getElementById('setting-age-sort').checked = systemSettings.enable_age_sort;
    } catch (e) { 
        console.error(e);
        container.innerHTML = '<p style="color:red">Error al cargar reglas.</p>'; 
    }
}

function renderRulesList(rules) {
    const c = document.getElementById('rules-list-container');
    c.innerHTML = (!rules || !rules.length) ? '<p style="padding:10px; color:#999; text-align:center;">No hay reglas creadas.</p>' : '';
    
    rules.forEach(r => {
        const conditions = r.conditions || []; 
        const div = document.createElement('div'); 
        div.className = 'rule-item';
        div.style.display = "flex";
        div.style.flexDirection = "column";
        div.style.alignItems = "flex-start";
        div.style.opacity = r.active ? '1' : '0.6';
        
        let conditionsText = "Regla sin condiciones válidas";
        if (conditions.length > 0) {
            conditionsText = conditions.map(c => 
                `<span class="filtro-chip" style="font-size:0.75rem; padding:2px 6px;">${c.column} ${c.operator} "${c.value}"</span>`
            ).join(" Y ");
        } else {
            if (r.column && r.value) {
                conditionsText = `<span class="filtro-chip" style="font-size:0.75rem; padding:2px 6px; background:#fee;">${r.column} = "${r.value}" (Formato Antiguo)</span>`;
            }
        }

        div.innerHTML = `
            <div style="display:flex; justify-content:space-between; width:100%; align-items:center; margin-bottom:5px;">
                <div style="font-weight:600; color:var(--primary);">
                    ${r.reason || "Sin Nombre"} <span style="color:#666; font-weight:400;">&rarr; ${r.priority}</span>
                </div>
                <div style="display:flex; gap:5px;">
                    <button class="btn-edit-rule icon-button" title="Editar" style="width:24px; height:24px; font-size:0.8rem;"><i class="fas fa-pencil-alt"></i></button>
                    <button class="btn-delete-rule icon-button" title="Borrar" style="width:24px; height:24px; font-size:0.8rem; color:var(--danger);"><i class="fas fa-trash"></i></button>
                </div>
            </div>
            <div style="display:flex; align-items:center; gap:10px; width:100%;">
                <input type="checkbox" class="toggle-rule" ${r.active?'checked':''} title="Activar/Desactivar">
                <div style="font-size:0.85rem; color:#555;">Si: ${conditionsText}</div>
            </div>
        `;
        
        const ruleId = r.id || null;
        
        div.querySelector('.btn-delete-rule').onclick = async () => {
            if(await showConfirm("Borrar Regla", "¿Borrar esta regla permanentemente?")) {
                if (ruleId) handleDeleteRuleInRules(ruleId);
                else showToast("Esta es una regla antigua. Se recomienda borrar el archivo JSON.", "warning");
            }
        };
        
        if (ruleId) {
            div.querySelector('.toggle-rule').onchange = (e) => handleToggleRule(ruleId, e.target.checked);
            div.querySelector('.btn-edit-rule').onclick = () => loadRuleIntoForm(r);
        } else {
            div.querySelector('.toggle-rule').disabled = true;
            div.querySelector('.btn-edit-rule').disabled = true;
        }
        
        c.appendChild(div);
    });
}

function resetRuleForm() {
    document.getElementById('rule-id-editing').value = ""; 
    document.getElementById('rule-editor-title').textContent = "Nueva Regla";
    document.getElementById('btn-save-rule').textContent = "Crear Regla";
    document.getElementById('btn-save-rule').className = "btn-verde-secundario";
    document.getElementById('rule-reason').value = "";
    document.getElementById('rule-priority').value = "Media";
    const container = document.getElementById('conditions-container');
    container.innerHTML = "";
    addConditionRow(); 
}

function addConditionRow(data = null) {
    const container = document.getElementById('conditions-container');
    const rowId = "cond-row-" + Date.now() + Math.floor(Math.random() * 1000); 
    
    const row = document.createElement('div');
    row.style.display = "flex";
    row.style.gap = "5px";
    row.style.marginBottom = "5px";
    
    let colOptions = `<option value="">Columna...</option>`;
    todasLasColumnas.filter(c => !c.startsWith('_') && c !== 'Priority').forEach(c => {
        colOptions += `<option value="${c}" ${data && data.column === c ? 'selected' : ''}>${c}</option>`;
    });

    row.innerHTML = `
        <select class="cond-col" style="flex:2;">${colOptions}</select>
        <select class="cond-op" style="flex:1;">
            <option value="equals" ${data && data.operator === 'equals' ? 'selected' : ''}>Igual (=)</option>
            <option value="contains" ${data && data.operator === 'contains' ? 'selected' : ''}>Contiene</option>
            <option value=">" ${data && data.operator === '>' ? 'selected' : ''}>Mayor (>)</option>
            <option value="<" ${data && data.operator === '<' ? 'selected' : ''}>Menor (<)</option>
        </select>
        <input type="text" class="cond-val" list="${rowId}-list" placeholder="Valor" style="flex:2;" value="${data ? data.value : ''}">
        <datalist id="${rowId}-list"></datalist>
        <button class="btn-remove-row btn-rojo-secundario" style="width:30px; padding:0;">&times;</button>
    `;
    
    const colSelect = row.querySelector('.cond-col');
    const dataList = row.querySelector('datalist');
    const updateDatalist = () => {
        const col = colSelect.value;
        dataList.innerHTML = '';
        if (col && autocompleteOptions[col]) {
            autocompleteOptions[col].forEach(val => {
                const op = document.createElement('option');
                op.value = val;
                dataList.appendChild(op);
            });
        }
    };
    colSelect.addEventListener('change', updateDatalist);
    if (data && data.column) updateDatalist();

    row.querySelector('.btn-remove-row').onclick = function() {
        if(container.children.length > 1) row.remove();
        else showToast("Debe haber al menos una condición.", "warning");
    };
    
    container.appendChild(row);
}

function loadRuleIntoForm(rule) {
    document.getElementById('rule-id-editing').value = rule.id;
    document.getElementById('rule-editor-title').textContent = "Editando Regla";
    document.getElementById('btn-save-rule').textContent = "Actualizar Regla";
    document.getElementById('btn-save-rule').className = "btn-azul-secundario";
    document.getElementById('rule-priority').value = rule.priority;
    document.getElementById('rule-reason').value = rule.reason;
    const container = document.getElementById('conditions-container');
    container.innerHTML = "";
    if (rule.conditions && rule.conditions.length > 0) {
        rule.conditions.forEach(cond => addConditionRow(cond));
    } else {
        addConditionRow(); 
    }
    document.getElementById('priority-rules-modal').scrollTo({ top: 0, behavior: 'smooth' });
}

async function handleSaveRule() {
    const idEditing = document.getElementById('rule-id-editing').value;
    const priority = document.getElementById('rule-priority').value;
    const reason = document.getElementById('rule-reason').value;
    
    if (!reason) return showToast("Escriba una razón para la regla.", "warning");

    const rows = document.querySelectorAll('#conditions-container > div');
    const conditions = [];
    
    for (let row of rows) {
        const col = row.querySelector('.cond-col').value;
        const op = row.querySelector('.cond-op').value;
        const val = row.querySelector('.cond-val').value;
        if (!col || val === "") return showToast("Complete todas las condiciones (Columna y Valor).", "warning");
        conditions.push({ column: col, operator: op, value: val });
    }

    const ruleData = { id: idEditing || null, priority: priority, reason: reason, conditions: conditions };

    try {
        const res = await fetch('/api/priority_rules/save', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(ruleData)
        });
        if (!res.ok) throw new Error("Error en servidor");
        const result = await res.json();
        
        showToast(idEditing ? "Regla actualizada exitosamente." : "Regla creada exitosamente.", "success");
        resetRuleForm();
        await loadAndRenderRules();
        if (currentFileId) {
            if (result.resumen) updateResumenCard(result.resumen);
            await getFilteredData();
        }
    } catch (e) { showToast(e.message, "error"); }
}

async function handleToggleRule(id, status) {
    await fetch('/api/priority_rules/toggle', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ rule_id: id, active: status })
    });
    if (currentFileId) await getFilteredData();
}

async function handleDeleteRuleInRules(id) {
    const res = await fetch('/api/priority_rules/delete', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ rule_id: id })
    });
    const data = await res.json();
    await loadAndRenderRules();
    if (currentFileId && data.resumen) {
        updateResumenCard(data.resumen);
        await getFilteredData();
    }
    showToast("Regla eliminada.", "success");
}

async function handleSaveSettings() {
    const scf = document.getElementById('setting-scf').checked;
    const age = document.getElementById('setting-age-sort').checked;
    try {
        await fetch('/api/priority_rules/save_settings', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ enable_scf_intercompany: scf, enable_age_sort: age })
        });
        systemSettings = { enable_scf_intercompany: scf, enable_age_sort: age };
        showToast("Configuración guardada correctamente.", "success");
        if (currentFileId) await getFilteredData(); 
    } catch (e) { showToast(e.message, "error"); }
}


// ============================================================================
// 10. LÓGICA DEL CHATBOT IA
// ============================================================================

let chatOpen = false; 

function toggleChat() {
    const windowEl = document.getElementById('chat-window');
    const launcherEl = document.getElementById('chat-launcher');
    
    chatOpen = !chatOpen;
    
    if (chatOpen) {
        windowEl.classList.add('visible');
        launcherEl.classList.add('active');
        setTimeout(() => document.getElementById('chat-input').focus(), 300);
    } else {
        windowEl.classList.remove('visible');
        launcherEl.classList.remove('active');
    }
}

document.addEventListener('DOMContentLoaded', () => {
    const w = document.getElementById('chat-widget');
    if(w) { 
        chatOpen = true; 
        console.log("✅ Chatbot inicializado correctamente"); 
    }
});

async function sendMessage() {
    const inp = document.getElementById('chat-input');
    const txt = inp.value.trim();
    if(!txt) return;
    
    addChatBubble(txt, 'user');
    inp.value = '';
    inp.disabled = true;

    const loadingId = addChatBubble("...", 'bot', true);

    try {
        const response = await fetch('/api/chat_agent', {
            method: 'POST', 
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ file_id: currentFileId, message: txt })
        });
        const data = await response.json();
        
        document.getElementById(loadingId).remove();
        addChatBubble(data.response, 'bot');
        
        if(data.actions && data.actions.length > 0) {
            for(let act of data.actions) {
                console.log("Ejecutando acción IA:", act);
                
                if(act.action === 'add_filter') {
                    activeFilters.push({columna: act.columna, valor: act.valor});
                    await refreshActiveView();
                    showToast(`IA: Filtrado por ${act.columna}`, "success");
                } 
                else if(act.action === 'clear_filters') {
                    handleClearFilters();
                    showToast("IA: Filtros limpiados", "info");
                } 
                else if(act.action === 'trigger_anomalies') {
                    handleAnalyzeAnomalies();
                }
                else if(act.action === 'refresh_table') {
                    await getFilteredData(); 
                    showToast("Tabla actualizada (Reglas aplicadas).", "success");
                }
                else if(act.action === 'manage_columns') {
                    const checkboxes = document.querySelectorAll('#column-selector-wrapper input[type="checkbox"]');
                    const targetCols = act.columns.map(c => c.toLowerCase());
                    
                    checkboxes.forEach(cb => {
                        const colName = cb.value.toLowerCase();
                        if (act.mode === 'ocultar') {
                            if (targetCols.includes(colName)) cb.checked = false;
                        } else if (act.mode === 'mostrar') {
                            if (targetCols.includes(colName)) cb.checked = true;
                        } else if (act.mode === 'solo_mostrar') {
                            cb.checked = targetCols.includes(colName);
                        }
                    });
                    updateVisibleColumnsFromCheckboxes();
                    showToast("Columnas actualizadas por IA", "success");
                }
                else if(act.action === 'prepare_bulk_delete') {
                    activeFilters = [{columna: act.columna, valor: act.valor}]; 
                    await refreshActiveView();
                    
                    setTimeout(() => {
                        if(tabulatorInstance) {
                            tabulatorInstance.selectRow("visible"); 
                            handleBulkDelete(); 
                        }
                    }, 500);
                    showToast("Filtrado para eliminar. Confirma en el modal.", "warning");
                }
                else if(act.action === 'delete_single_row_trigger') {
                    const rowId = act.row_id;
                    const row = tabulatorInstance.getRow(rowId);
                    if(row) {
                        tabulatorInstance.scrollToRow(rowId, "center", true)
                            .then(async () => {
                                row.select();
                                if(await showConfirm("Eliminar Fila", `La IA sugiere eliminar la fila N° ${rowId + 1}. ¿Estás de acuerdo?`)) {
                                    handleDeleteRow(rowId);
                                }
                                row.deselect();
                            });
                    } else {
                        showToast(`La fila ${rowId + 1} no se encuentra visible.`, "warning");
                    }
                }
                else if(act.action === 'delete_column_trigger') {
                    if(await showConfirm("Eliminar Columna", `La IA sugiere borrar permanentemente la columna "${act.columna}". ¿Proceder?`)) {
                        try {
                            const res = await fetch('/api/delete_column', {
                                method: 'POST', headers: {'Content-Type': 'application/json'},
                                body: JSON.stringify({ file_id: currentFileId, columna: act.columna })
                            });
                            const result = await res.json();
                            if(!res.ok) throw new Error(result.error);
                            
                            todasLasColumnas = result.new_columns;
                            columnasVisibles = columnasVisibles.filter(c => c !== act.columna);
                            
                            populateColumnDropdowns(); 
                            renderColumnSelector();
                            renderTable(); 
                            updateActionButtonsVisibility();
                            showToast(`Columna "${act.columna}" eliminada.`, "success");
                        } catch(err) {
                            showToast("Error borrando columna: " + err.message, "error");
                        }
                    }
                }
                else if(act.action === 'delete_multiple_rows_by_id_trigger') {
                    const ids = act.row_ids;
                    const visuales = act.numeros_visuales;
                    
                    tabulatorInstance.deselectRow();
                    tabulatorInstance.selectRow(ids); 
                    
                    const selectedData = tabulatorInstance.getSelectedData();
                    if(selectedData.length > 0) {
                        const confirmMsg = `La IA sugiere eliminar ${selectedData.length} filas (N° ${visuales.join(', ')}). ¿Confirmar?`;
                        if(await showConfirm("Eliminar Múltiples Filas", confirmMsg)) {
                            handleBulkDelete(); 
                        } else {
                            tabulatorInstance.deselectRow();
                        }
                    } else {
                        showToast("No se encontraron las filas solicitadas en la vista actual.", "warning");
                    }
                }
            }
        }
    } catch(e) {
        if(document.getElementById(loadingId)) document.getElementById(loadingId).remove();
        addChatBubble("Error de conexión: " + e.message, 'bot');
    } finally {
        inp.disabled = false;
        inp.focus();
    }
}

function addChatBubble(txt, type, isLoading=false) {
    const div = document.createElement('div');
    div.className = `chat-msg ${type}`;
    div.innerText = txt;
    if(isLoading) div.id = "chat-loading-" + Date.now();
    
    const container = document.getElementById('chat-messages');
    container.appendChild(div);
    container.scrollTop = container.scrollHeight;
    return div.id;
}

function handleChatKey(e) { if(e.key === 'Enter') sendMessage(); }


// ============================================================================
// 11. GESTOR DE EVENTOS
// ============================================================================

function setupEventListeners() {
    // ------------------------------------------------------------------------
    // NUEVO: MANEJADOR GLOBAL DE CIERRE DE MODALES (Para botones 'X' en esquinas)
    // ------------------------------------------------------------------------
    document.addEventListener('click', (e) => {
        // Detectar si el click fue en un elemento con clase .btn-close-x o dentro de él
        const closeBtn = e.target.closest('.btn-close-x');
        if (closeBtn) {
            // Buscar el div modal padre más cercano cuyo ID contenga 'modal'
            const modal = closeBtn.closest('div[id*="modal"]'); 
            if (modal) {
                closeModal(modal.id);
            }
        }
    });

    // 1. Carga de Archivos
    const uploader = document.getElementById('file-uploader');
    if (uploader) uploader.addEventListener('change', handleFileUpload);

    // 2. Idioma
    const btnEs = document.getElementById('btn-lang-es');
    if (btnEs) btnEs.addEventListener('click', () => setLanguage('es'));
    const btnEn = document.getElementById('btn-lang-en');
    if (btnEn) btnEn.addEventListener('click', () => setLanguage('en'));

    // 3. Filtros
    const btnAddFilter = document.getElementById('btn-add-filter');
    if (btnAddFilter) btnAddFilter.addEventListener('click', handleAddFilter);
    
    const selectFilterCol = document.getElementById('select-columna');
    if (selectFilterCol) selectFilterCol.addEventListener('change', updateFilterAutocomplete);
    
    const filtersList = document.getElementById('active-filters-list');
    if (filtersList) filtersList.addEventListener('click', handleRemoveFilter);
    
    const filtersListGrouped = document.getElementById('active-filters-list-grouped');
    if (filtersListGrouped) filtersListGrouped.addEventListener('click', handleRemoveFilter);

    const btnCheckAll = document.getElementById('btn-check-all-cols');
    if (btnCheckAll) btnCheckAll.addEventListener('click', () => {
        document.querySelectorAll('#column-selector-wrapper input[type="checkbox"]').forEach(cb => cb.checked = true);
        updateVisibleColumnsFromCheckboxes();
    });

    const btnUncheckAll = document.getElementById('btn-uncheck-all-cols');
    if (btnUncheckAll) btnUncheckAll.addEventListener('click', () => {
        document.querySelectorAll('#column-selector-wrapper input[type="checkbox"]').forEach(cb => cb.checked = false);
        updateVisibleColumnsFromCheckboxes();
    });

    const colWrapper = document.getElementById('column-selector-wrapper');
    if (colWrapper) colWrapper.addEventListener('change', (e) => {
        if (e.target.matches('input[type="checkbox"]')) updateVisibleColumnsFromCheckboxes();
    });

    // 4. Botones Principales (Sidebar)
    const btnManage = document.getElementById('btn-manage-lists');
    if (btnManage) btnManage.addEventListener('click', openManageListsModal);

    const btnRules = document.getElementById('btn-priority-rules');
    if (btnRules) btnRules.addEventListener('click', openPriorityRulesModal);

    const btnAnomalies = document.getElementById('btn-analyze-anomalies');
    if (btnAnomalies) btnAnomalies.addEventListener('click', handleAnalyzeAnomalies);

    const btnShowDupes = document.getElementById('btn-show-duplicates');
    if (btnShowDupes) btnShowDupes.addEventListener('click', handleShowDuplicates);

    // 5. Vistas y Agrupación
    const btnViewDetailed = document.getElementById('btn-view-detailed');
    if (btnViewDetailed) btnViewDetailed.addEventListener('click', () => toggleView('detailed'));

    const btnViewGrouped = document.getElementById('btn-view-grouped');
    if (btnViewGrouped) btnViewGrouped.addEventListener('click', () => toggleView('grouped'));

    const selectGroup = document.getElementById('select-columna-agrupar');
    if (selectGroup) selectGroup.addEventListener('change', handleGroupColumnChange);

    // 6. Controles de Tabla
    const inputSearch = document.getElementById('input-search-table');
    if (inputSearch) inputSearch.addEventListener('keyup', handleSearchTable);

    const btnBulkEdit = document.getElementById('btn-bulk-edit');
    if (btnBulkEdit) btnBulkEdit.addEventListener('click', openBulkEditModal);

    const btnFindReplace = document.getElementById('btn-find-replace');
    if (btnFindReplace) btnFindReplace.addEventListener('click', openFindReplaceModal);

    const btnBulkDelete = document.getElementById('btn-bulk-delete');
    if (btnBulkDelete) btnBulkDelete.addEventListener('click', handleBulkDelete);

    const btnAddRow = document.getElementById('btn-add-row');
    if (btnAddRow) btnAddRow.addEventListener('click', handleAddRow);

    const btnUndo = document.getElementById('btn-undo-change');
    if (btnUndo) btnUndo.addEventListener('click', handleUndoChange);

    const btnCommit = document.getElementById('btn-commit-changes');
    if (btnCommit) btnCommit.addEventListener('click', handleCommitChanges);
    
    const btnAudit = document.getElementById('btn-download-audit-log');
    if (btnAudit) btnAudit.addEventListener('click', handleDownloadAuditLog);

    const btnClearFilters = document.getElementById('btn-clear-filters');
    if (btnClearFilters) btnClearFilters.addEventListener('click', handleClearFilters);
    
    const btnClearFiltersG = document.getElementById('btn-clear-filters-grouped');
    if (btnClearFiltersG) btnClearFiltersG.addEventListener('click', handleClearFilters);

    // 7. Descargas
    const btnDownExcel = document.getElementById('btn-download-excel');
    if (btnDownExcel) btnDownExcel.addEventListener('click', handleDownloadExcel);

    const btnDownExcelG = document.getElementById('btn-download-excel-grouped');
    if (btnDownExcelG) btnDownExcelG.addEventListener('click', handleDownloadExcelGrouped);

    const btnFull = document.getElementById('btn-fullscreen');
    if (btnFull) btnFull.addEventListener('click', handleFullscreen);
    
    const btnFullG = document.getElementById('btn-fullscreen-grouped');
    if (btnFullG) btnFullG.addEventListener('click', handleFullscreen);

    // 8. Modales (Botones internos)
    const btnBulkApply = document.getElementById('btn-bulk-apply');
    if (btnBulkApply) btnBulkApply.addEventListener('click', handleBulkEditApply);
    const btnBulkCancel = document.getElementById('btn-bulk-cancel');
    if (btnBulkCancel) btnBulkCancel.addEventListener('click', () => closeModal('bulk-edit-modal'));

    const btnFindApply = document.getElementById('btn-find-replace-apply');
    if (btnFindApply) btnFindApply.addEventListener('click', handleFindReplaceApply);
    const btnFindCancel = document.getElementById('btn-find-replace-cancel');
    if (btnFindCancel) btnFindCancel.addEventListener('click', () => closeModal('find-replace-modal'));

    const btnManageSave = document.getElementById('btn-manage-save');
    if (btnManageSave) btnManageSave.addEventListener('click', handleManageListsSave);
    const btnManageCancel = document.getElementById('btn-manage-cancel');
    if (btnManageCancel) btnManageCancel.addEventListener('click', () => closeModal('manage-lists-modal'));
    const btnManageDelAll = document.getElementById('btn-manage-delete-all');
    if (btnManageDelAll) btnManageDelAll.addEventListener('click', handleDeleteAllValues);
    const btnManageImport = document.getElementById('btn-manage-import');
    if (btnManageImport) btnManageImport.addEventListener('click', handleImportAutocomplete);
    
    const selectManageCol = document.getElementById('manage-list-column');
    if (selectManageCol) selectManageCol.addEventListener('change', updateManageListsCurrentValues);

    const btnRuleSave = document.getElementById('btn-save-rule');
    if (btnRuleSave) btnRuleSave.addEventListener('click', handleSaveRule);
    const btnRuleSettings = document.getElementById('btn-save-settings');
    if (btnRuleSettings) btnRuleSettings.addEventListener('click', handleSaveSettings);
    
    // NOTA: Eliminamos la asignación específica de btn-rules-close aquí porque 
    // el manejador global al principio de esta función ya lo cubre.
    
    const btnRuleClear = document.getElementById('btn-clear-rule-form');
    if (btnRuleClear) btnRuleClear.addEventListener('click', resetRuleForm);
    
    const btnAddCond = document.getElementById('btn-add-condition-row');
    if (btnAddCond) btnAddCond.addEventListener('click', () => addConditionRow());

    // ------------------------------------------------------------------------
    // ATAJOS DE TECLADO (HOTKEYS) - Lógica Centralizada
    // ------------------------------------------------------------------------
    document.addEventListener('keydown', (e) => {
        const isInput = ['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement.tagName);

        // 1. BUSCAR (Tecla F) - Solo si no escribe texto
        if ((e.key === 'f' || e.key === 'F') && !isInput && !e.ctrlKey && !e.metaKey) {
            e.preventDefault();
            const search = document.getElementById('input-search-table');
            if (search) {
                search.focus();
                search.select(); // Selecciona el texto existente para facilitar nueva búsqueda
            }
        }

        // 2. PANTALLA COMPLETA (Tecla G) - Solo si no escribe texto
        if ((e.key === 'g' || e.key === 'G') && !isInput && !e.ctrlKey && !e.metaKey) {
            e.preventDefault();
            handleFullscreen();
        }

        // 3. DESHACER (Ctrl + Z) - Solo si no escribe texto (para respetar el undo nativo de inputs)
        if ((e.ctrlKey || e.metaKey) && (e.key === 'z' || e.key === 'Z') && !isInput) {
            e.preventDefault();
            const btnUndo = document.getElementById('btn-undo-change');
            // Solo ejecutar si el botón es visible (hay historial)
            if (btnUndo && btnUndo.style.display !== 'none') {
                handleUndoChange();
            } else {
                showToast("No hay acciones para deshacer.", "info");
            }
        }

        // 4. CONSOLIDAR / GUARDAR (Ctrl + S) - Intercepta siempre para evitar "Guardar como..." del navegador
        if ((e.ctrlKey || e.metaKey) && (e.key === 's' || e.key === 'S')) {
            e.preventDefault(); // Bloquea el guardado del navegador
            const btnCommit = document.getElementById('btn-commit-changes');
            if (btnCommit && btnCommit.style.display !== 'none') {
                handleCommitChanges();
            } else {
                showToast("No hay cambios pendientes por consolidar.", "info");
            }
        }

        // 5. CERRAR MODALES (Escape)
        if (e.key === 'Escape') {
            document.querySelectorAll('div[id$="-modal"]').forEach(el => el.style.display = 'none');
            document.getElementById('modal-overlay').style.display = 'none';
            
            // Si está en fullscreen, salir también
            if (document.body.classList.contains('fullscreen-mode')) handleFullscreen();
        }
    });

    console.log("✅ Event Listeners y Hotkeys configurados correctamente.");
}

    console.log("✅ Event Listeners configurados correctamente.");
}


// ============================================================================
// 12. INICIALIZACIÓN (DOM READY)
// ============================================================================

document.addEventListener('DOMContentLoaded', async () => {
    // 1. Verificar Conexión
    const statusEl = document.getElementById('system-status');
    if(statusEl) {
        fetch('/api/get_translations')
            .then(r => {
                if(r.ok) {
                    statusEl.style.background = "#dcfce7"; 
                    statusEl.style.borderColor = "#22c55e";
                    statusEl.style.color = "#166534";
                    statusEl.innerHTML = '<i class="fas fa-check-circle"></i> Sistema Conectado y Listo';
                    setTimeout(() => { statusEl.style.display = 'none'; }, 3000);
                } else throw new Error("Backend devolvió error");
            })
            .catch(e => {
                statusEl.innerHTML = `<i class="fas fa-exclamation-triangle"></i> Error de conexión: ${e.message}`;
            });
    }

    // 2. Cargar Datos
    await loadTranslations();
    if (typeof SESSION_DATA !== 'undefined' && SESSION_DATA.file_id) {
        currentFileId = SESSION_DATA.file_id;
        todasLasColumnas = SESSION_DATA.columnas;
        columnasVisibles = [...todasLasColumnas];
        autocompleteOptions = SESSION_DATA.autocomplete_options || {};
        undoHistoryCount = SESSION_DATA.history_count || 0;

        populateColumnDropdowns(); 
        renderColumnSelector(); 
        updateVisibleColumnsFromCheckboxes();
        updateActionButtonsVisibility(); 
        refreshActiveView();
    } else {
        renderColumnSelector(); 
        updateActionButtonsVisibility();
    }
    
    // 3. Activar Eventos
    setupEventListeners();
});