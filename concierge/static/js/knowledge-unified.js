// knowledge-unified.js - Unified Knowledge Management JavaScript

document.addEventListener('DOMContentLoaded', function() {
    // Ensure loading overlay is completely hidden when page loads
    hideLoading();

    // Initialize variables
    const propertyId = document.querySelector('[data-property-id]')?.dataset.propertyId;
    const propertyName = document.querySelector('[data-property-name]')?.dataset.propertyName;
    let allItems = [];
    let currentPage = 1;
    let itemsPerPage = parseInt(document.getElementById('itemsPerPage').value) || 25;
    let filteredItems = [];

    // Initialize Bootstrap components
    const addKnowledgeModal = new bootstrap.Modal(document.getElementById('addKnowledgeModal'));
    const editItemModal = new bootstrap.Modal(document.getElementById('editItemModal'));

    // Initialize event listeners
    initializeEventListeners();

    // Load knowledge items
    loadKnowledgeItems();

    // Initialize drag and drop
    initializeDragAndDrop();

    /**
     * Initialize all event listeners
     */
    function initializeEventListeners() {
        // Add Knowledge button
        document.getElementById('addKnowledgeBtn').addEventListener('click', function() {
            addKnowledgeModal.show();
        });

        // File upload form
        const fileUploadForm = document.getElementById('fileUploadForm');
        if (fileUploadForm) {
            fileUploadForm.addEventListener('submit', handleFileUpload);
        }

        // Text form
        const textForm = document.getElementById('textForm');
        if (textForm) {
            textForm.addEventListener('submit', handleTextSubmit);
        }

        // Dropzone click
        const dropzone = document.getElementById('dropzone');
        if (dropzone) {
            dropzone.addEventListener('click', function(e) {
                // Only trigger file input click if the click wasn't on the browse button
                if (e.target.tagName !== 'BUTTON') {
                    document.getElementById('knowledgeFile').click();
                }
            });
        }

        // File input change
        document.getElementById('knowledgeFile').addEventListener('change', handleFileSelect);

        // Remove file button
        document.getElementById('removeFile').addEventListener('click', function() {
            resetFileUpload();
        });

        // Save item button
        document.getElementById('saveItemBtn').addEventListener('click', saveItemChanges);

        // Delete All button
        document.getElementById('deleteAllKnowledgeBtn').addEventListener('click', deleteAllKnowledge);

        // Filter listeners
        document.getElementById('statusFilter').addEventListener('change', applyFilters);
        document.getElementById('typeFilter').addEventListener('change', applyFilters);
        document.getElementById('searchFilter').addEventListener('input', applyFilters);

        // Items per page
        document.getElementById('itemsPerPage').addEventListener('change', function() {
            itemsPerPage = parseInt(this.value);
            currentPage = 1;
            renderItems();
        });
    }

    /**
     * Initialize drag and drop functionality
     */
    function initializeDragAndDrop() {
        const dropzone = document.getElementById('dropzone');
        if (!dropzone) return;

        // Prevent default drag behaviors
        ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
            dropzone.addEventListener(eventName, preventDefaults, false);
        });

        // Highlight dropzone when item is dragged over it
        ['dragenter', 'dragover'].forEach(eventName => {
            dropzone.addEventListener(eventName, highlight, false);
        });

        // Remove highlight when item is dragged away
        ['dragleave', 'drop'].forEach(eventName => {
            dropzone.addEventListener(eventName, unhighlight, false);
        });

        // Handle dropped files
        dropzone.addEventListener('drop', handleDrop, false);

        function preventDefaults(e) {
            e.preventDefault();
            e.stopPropagation();
        }

        function highlight() {
            dropzone.classList.add('highlight');
        }

        function unhighlight() {
            dropzone.classList.remove('highlight');
        }

        function handleDrop(e) {
            const dt = e.dataTransfer;
            const files = dt.files;

            if (files.length > 0) {
                document.getElementById('knowledgeFile').files = files;
                handleFileSelect();
            }
        }
    }

    /**
     * Handle file selection
     */
    function handleFileSelect() {
        const fileInput = document.getElementById('knowledgeFile');
        const filePreview = document.getElementById('filePreview');
        const fileName = document.getElementById('fileName');
        const fileSize = document.getElementById('fileSize');
        const uploadBtn = document.getElementById('uploadFileBtn');

        if (fileInput.files.length > 0) {
            const file = fileInput.files[0];
            fileName.textContent = file.name;
            fileSize.textContent = `Size: ${formatFileSize(file.size)}`;
            filePreview.classList.remove('d-none');
            uploadBtn.disabled = false;
        } else {
            resetFileUpload();
        }
    }

    /**
     * Reset file upload form
     */
    function resetFileUpload() {
        const fileInput = document.getElementById('knowledgeFile');
        const filePreview = document.getElementById('filePreview');
        const uploadBtn = document.getElementById('uploadFileBtn');

        fileInput.value = '';
        filePreview.classList.add('d-none');
        uploadBtn.disabled = true;
    }

    /**
     * Format file size in human-readable format
     */
    function formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }

    /**
     * Handle file upload form submission
     */
    function handleFileUpload(e) {
        e.preventDefault();
        console.log('File upload form submitted');

        // Get the file name for a more specific message
        const fileInput = document.getElementById('knowledgeFile');
        const fileName = fileInput.files.length > 0 ? fileInput.files[0].name : 'file';

        // Disable the submit button to prevent multiple submissions
        const submitButton = document.getElementById('uploadFileBtn');
        if (submitButton) {
            submitButton.disabled = true;
            submitButton.innerHTML = '<span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>Processing...';
        }

        // Show the loading overlay
        showLoading(`Uploading and processing ${fileName}...`);

        // Short delay to ensure the loading overlay is displayed
        setTimeout(() => {
            const form = e.target;
            const formData = new FormData(form);

            fetch(form.action, {
                method: 'POST',
                body: formData,
                redirect: 'follow' // Allow redirects
            })
            .then(response => {
                if (!response.ok) {
                    throw new Error('Network response was not ok');
                }

                // Check if the response is a redirect or HTML
                const contentType = response.headers.get('content-type');
                if (contentType && contentType.includes('text/html')) {
                    console.log('Received HTML response, assuming successful upload');
                    // Handle as success without trying to parse JSON
                    return { success: true };
                }

                // Try to parse as JSON if it's not HTML
                return response.json().catch(() => {
                    console.log('Response is not JSON, assuming successful upload');
                    return { success: true };
                });
            })
            .then(data => {
                console.log('File upload successful:', data);
                addKnowledgeModal.hide();
                resetFileUpload();

                // Show a loading message while refreshing the items
                showLoading('Refreshing knowledge items...');

                // Load knowledge items and reset the submit button when done
                loadKnowledgeItems(false, () => {
                    if (submitButton) {
                        submitButton.disabled = false;
                        submitButton.innerHTML = 'Upload & Process';
                    }
                });
            })
            .catch(error => {
                console.error('Error uploading file:', error);
                hideLoading();
                alert('Error uploading file: ' + error.message);

                // Re-enable the submit button
                if (submitButton) {
                    submitButton.disabled = false;
                    submitButton.innerHTML = 'Upload & Process';
                }
            });
        }, 100); // Short delay to ensure the loading overlay is displayed
    }

    /**
     * Handle text submission form
     */
    function handleTextSubmit(e) {
        e.preventDefault();
        console.log('Text submission form submitted');

        // Generate a source name from content for a more specific message
        const contentText = document.getElementById('knowledge_text').value || '';
        const sourceName = contentText.substring(0, 30).trim() || 'text';

        // Disable the submit button to prevent multiple submissions
        const submitButton = e.target.querySelector('button[type="submit"]');
        if (submitButton) {
            submitButton.disabled = true;
            submitButton.innerHTML = '<span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>Processing...';
        }

        // Show the loading overlay
        showLoading(`Processing ${sourceName}...`);

        // Short delay to ensure the loading overlay is displayed
        setTimeout(() => {
            const form = e.target;
            const formData = new FormData(form);

            fetch(form.action, {
                method: 'POST',
                body: formData,
                redirect: 'follow' // Allow redirects
            })
            .then(response => {
                if (!response.ok) {
                    throw new Error('Network response was not ok');
                }

                // Check if the response is a redirect or HTML
                const contentType = response.headers.get('content-type');
                if (contentType && contentType.includes('text/html')) {
                    console.log('Received HTML response, assuming successful submission');
                    // Handle as success without trying to parse JSON
                    return { success: true };
                }

                // Try to parse as JSON if it's not HTML
                return response.json().catch(() => {
                    console.log('Response is not JSON, assuming successful submission');
                    return { success: true };
                });
            })
            .then(data => {
                console.log('Text submission successful:', data);
                addKnowledgeModal.hide();
                form.reset();

                // Show a loading message while refreshing the items
                showLoading('Refreshing knowledge items...');

                // Load knowledge items and reset the submit button when done
                loadKnowledgeItems(false, () => {
                    if (submitButton) {
                        submitButton.disabled = false;
                        submitButton.innerHTML = 'Add Text & Process';
                    }
                });
            })
            .catch(error => {
                console.error('Error adding text:', error);
                hideLoading();
                alert('Error adding text: ' + error.message);

                // Re-enable the submit button
                if (submitButton) {
                    submitButton.disabled = false;
                    submitButton.innerHTML = 'Add Text & Process';
                }
            });
        }, 100); // Short delay to ensure the loading overlay is displayed
    }

    /**
     * Load knowledge items from the server
     * @param {boolean} showLoadingIndicator - Whether to show the loading indicator
     * @param {Function} callback - Optional callback to run after loading completes
     */
    function loadKnowledgeItems(showLoadingIndicator = true, callback = null) {
        if (!propertyId) {
            console.error('Property ID not found');
            if (callback) callback();
            return;
        }

        if (showLoadingIndicator) {
            showLoading('Loading knowledge items...');
        }

        fetch(`/api/knowledge-items?propertyId=${propertyId}`)
            .then(response => {
                if (!response.ok) {
                    throw new Error('Network response was not ok');
                }
                return response.json();
            })
            .then(data => {
                if (data.success) {
                    allItems = data.items || [];
                    applyFilters();
                } else {
                    console.error('Error loading knowledge items:', data.error);
                    throw new Error(data.error || 'Failed to load knowledge items');
                }
            })
            .catch(error => {
                console.error('Error loading knowledge items:', error);
                document.getElementById('knowledgeItems').innerHTML = `
                    <tr>
                        <td colspan="5" class="text-center py-4 text-danger">
                            <i class="bi bi-exclamation-triangle me-2"></i>
                            Error loading knowledge items: ${error.message}
                        </td>
                    </tr>
                `;
            })
            .finally(() => {
                hideLoading();
                if (callback) callback();
            });
    }

    /**
     * Apply filters to knowledge items
     */
    function applyFilters() {
        const statusFilter = document.getElementById('statusFilter').value;
        const typeFilter = document.getElementById('typeFilter').value;
        const searchFilter = document.getElementById('searchFilter').value.toLowerCase();

        filteredItems = allItems.filter(item => {
            // Status filter
            if (statusFilter !== 'all' && item.status !== statusFilter) {
                return false;
            }

            // Type filter
            if (typeFilter !== 'all' && item.type !== typeFilter) {
                return false;
            }

            // Search filter
            if (searchFilter) {
                const content = (item.content || '').toLowerCase();
                const tags = (item.tags || []).join(' ').toLowerCase();
                return content.includes(searchFilter) || tags.includes(searchFilter);
            }

            return true;
        });

        currentPage = 1;
        renderItems();
    }

    /**
     * Render items to the table
     */
    function renderItems() {
        const tableBody = document.getElementById('knowledgeItems');
        const itemCount = document.getElementById('itemCount');

        // Update item count
        itemCount.textContent = `${filteredItems.length} items`;

        // Sort items to prioritize pending items at the top
        const sortedItems = [...filteredItems].sort((a, b) => {
            // First, prioritize pending items to appear at the top
            const aPending = (a.status === 'pending');
            const bPending = (b.status === 'pending');

            if (aPending && !bPending) return -1;
            if (!aPending && bPending) return 1;

            // Then sort by created_at (newest first) within each group
            const aDate = new Date(a.created_at || 0);
            const bDate = new Date(b.created_at || 0);
            return bDate - aDate;
        });

        // Calculate pagination
        const totalPages = Math.ceil(sortedItems.length / itemsPerPage);
        const startIndex = (currentPage - 1) * itemsPerPage;
        const endIndex = Math.min(startIndex + itemsPerPage, sortedItems.length);
        const itemsToShow = sortedItems.slice(startIndex, endIndex);

        // Render pagination
        renderPagination(totalPages);

        // Render items
        if (itemsToShow.length === 0) {
            tableBody.innerHTML = `
                <tr>
                    <td colspan="5" class="text-center py-4">
                        No knowledge items found matching your filters.
                    </td>
                </tr>
            `;
            return;
        }

        let html = '';
        itemsToShow.forEach(item => {
            const statusBadge = getStatusBadge(item.status);
            const typeBadge = getTypeBadge(item.type);
            const tags = (item.tags || []).map(tag => `<span class="badge bg-secondary me-1">${tag}</span>`).join('');

            // Add highlighting class for pending items
            const isPending = (item.status === 'pending');
            const rowClass = isPending ? 'knowledge-item pending-item' : 'knowledge-item';

            html += `
                <tr class="${rowClass}" data-id="${item.id}">
                    <td>${typeBadge}</td>
                    <td>${tags || '<span class="text-muted">No tags</span>'}</td>
                    <td class="content-cell">${item.content || ''}</td>
                    <td>${statusBadge}</td>
                    <td class="item-actions">
                        ${getActionButtons(item)}
                    </td>
                </tr>
            `;
        });

        tableBody.innerHTML = html;

        // Add event listeners to action buttons
        addActionButtonListeners();
    }

    /**
     * Render pagination controls
     */
    function renderPagination(totalPages) {
        const pagination = document.getElementById('pagination');

        if (totalPages <= 1) {
            pagination.innerHTML = '';
            return;
        }

        let html = '';

        // Previous button
        html += `
            <li class="page-item ${currentPage === 1 ? 'disabled' : ''}">
                <a class="page-link" href="#" data-page="${currentPage - 1}" aria-label="Previous">
                    <span aria-hidden="true">&laquo;</span>
                </a>
            </li>
        `;

        // Page numbers
        const maxPages = 5;
        let startPage = Math.max(1, currentPage - Math.floor(maxPages / 2));
        let endPage = Math.min(totalPages, startPage + maxPages - 1);

        if (endPage - startPage + 1 < maxPages) {
            startPage = Math.max(1, endPage - maxPages + 1);
        }

        for (let i = startPage; i <= endPage; i++) {
            html += `
                <li class="page-item ${i === currentPage ? 'active' : ''}">
                    <a class="page-link" href="#" data-page="${i}">${i}</a>
                </li>
            `;
        }

        // Next button
        html += `
            <li class="page-item ${currentPage === totalPages ? 'disabled' : ''}">
                <a class="page-link" href="#" data-page="${currentPage + 1}" aria-label="Next">
                    <span aria-hidden="true">&raquo;</span>
                </a>
            </li>
        `;

        pagination.innerHTML = html;

        // Add event listeners to pagination links
        document.querySelectorAll('#pagination .page-link').forEach(link => {
            link.addEventListener('click', function(e) {
                e.preventDefault();
                const page = parseInt(this.dataset.page);
                if (page !== currentPage && page >= 1 && page <= totalPages) {
                    currentPage = page;
                    renderItems();
                }
            });
        });
    }

    /**
     * Get status badge HTML
     */
    function getStatusBadge(status) {
        switch (status) {
            case 'pending':
                return '<span class="badge badge-pending">Pending Review</span>';
            case 'approved':
                return '<span class="badge badge-approved">Approved</span>';
            case 'rejected':
                return '<span class="badge badge-rejected">Rejected</span>';
            case 'error':
            case 'processing_error':
                return '<span class="badge badge-error">Error</span>';
            default:
                return `<span class="badge bg-secondary">${status || 'Unknown'}</span>`;
        }
    }

    /**
     * Get type badge HTML
     */
    function getTypeBadge(type) {
        let badgeClass = 'bg-secondary';

        switch (type) {
            case 'rule':
                badgeClass = 'bg-danger';
                break;
            case 'instruction':
                badgeClass = 'bg-warning text-dark';
                break;
            case 'amenity':
                badgeClass = 'bg-success';
                break;
            case 'information':
                badgeClass = 'bg-info';
                break;
            case 'places':
                badgeClass = 'bg-primary';
                break;
        }

        return `<span class="badge ${badgeClass}">${type ? type.charAt(0).toUpperCase() + type.slice(1) : 'Unknown'}</span>`;
    }

    /**
     * Get action buttons HTML based on item status
     */
    function getActionButtons(item) {
        let buttons = '';

        // View button removed as content is now fully displayed in the table

        // Edit button for all items
        buttons += `<button class="btn btn-sm btn-outline-secondary me-1 edit-item-btn" data-id="${item.id}" title="Edit">
        <i class="bi bi-pencil"></i>
        </button>`;
        
        // Copy button for all items
        buttons += `<button class="btn btn-sm btn-outline-info me-1 copy-item-btn" data-id="${item.id}" title="Copy to new item">
            <i class="bi bi-copy"></i>
        </button>`;

        // Approve button for pending items - make it more prominent
        if (item.status === 'pending') {
            buttons += `<button class="btn btn-sm btn-success me-1 approve-item-btn pulse-button" data-id="${item.id}" title="Approve this item">
                <i class="bi bi-check-lg"></i>
            </button>`;
        }

        // Delete button for all items
        buttons += `<button class="btn btn-sm btn-outline-danger delete-item-btn" data-id="${item.id}" title="Delete">
            <i class="bi bi-trash"></i>
        </button>`;

        return buttons;
    }

    /**
     * Add event listeners to action buttons
     */
    function addActionButtonListeners() {
        // View item buttons removed as content is now fully displayed in the table

        // Copy item buttons
        document.querySelectorAll('.copy-item-btn').forEach(btn => {
            btn.addEventListener('click', function() {
                const itemId = this.dataset.id;
                copyItem(itemId);
            });
        });

        // Edit item buttons
        document.querySelectorAll('.edit-item-btn').forEach(btn => {
            btn.addEventListener('click', function() {
                const itemId = this.dataset.id;
                editItem(itemId);
            });
        });

        // Approve item buttons
        document.querySelectorAll('.approve-item-btn').forEach(btn => {
            btn.addEventListener('click', function() {
                const itemId = this.dataset.id;
                approveItem(itemId);
            });
        });

        // Delete item buttons
        document.querySelectorAll('.delete-item-btn').forEach(btn => {
            btn.addEventListener('click', function() {
                const itemId = this.dataset.id;
                deleteItem(itemId);
            });
        });
    }

    /**
     * Copy item content to Add Knowledge modal
     */
    function copyItem(itemId) {
        const item = allItems.find(item => item.id === itemId);
        if (!item) return;

        // Open the Add Knowledge modal
        addKnowledgeModal.show();

        // Switch to the Raw Text tab
        const textTab = document.getElementById('text-tab');
        const textTabPane = document.getElementById('text-tab-pane');
        const uploadTab = document.getElementById('upload-tab');
        const uploadTabPane = document.getElementById('upload-tab-pane');

        // Remove active class from upload tab and add to text tab
        uploadTab.classList.remove('active');
        uploadTab.setAttribute('aria-selected', 'false');
        uploadTabPane.classList.remove('show', 'active');

        textTab.classList.add('active');
        textTab.setAttribute('aria-selected', 'true');
        textTabPane.classList.add('show', 'active');

        // Populate the form field with the item's content
        document.getElementById('knowledge_text').value = item.content || '';

        // Focus on the text area for immediate editing
        setTimeout(() => {
            document.getElementById('knowledge_text').focus();
        }, 100);
    }

    // View item function removed as content is now fully displayed in the table

    /**
     * Edit item
     */
    function editItem(itemId) {
        const item = allItems.find(item => item.id === itemId);
        if (!item) return;

        document.getElementById('editItemModalLabel').textContent = 'Edit Knowledge Item';
        document.getElementById('editItemId').value = item.id;
        document.getElementById('editType').value = item.type || 'information';
        document.getElementById('editTags').value = (item.tags || []).join(', ');
        document.getElementById('editContent').value = item.content || '';

        // Enable form fields
        document.getElementById('editType').disabled = false;
        document.getElementById('editTags').disabled = false;
        document.getElementById('editContent').disabled = false;

        // Show save button
        document.getElementById('saveItemBtn').style.display = 'block';

        editItemModal.show();
    }

    /**
     * Save item changes
     */
    function saveItemChanges() {
        const itemId = document.getElementById('editItemId').value;
        const updatedType = document.getElementById('editType').value;
        const updatedTags = document.getElementById('editTags').value.split(',').map(tag => tag.trim()).filter(tag => tag);
        const updatedContent = document.getElementById('editContent').value;

        if (!itemId) return;

        showLoading('Saving changes...');

        fetch(`/api/knowledge-items/${itemId}/update`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                type: updatedType,
                tags: updatedTags,
                content: updatedContent
            })
        })
        .then(response => {
            if (!response.ok) {
                throw new Error('Network response was not ok');
            }
            return response.json();
        })
        .then(data => {
            if (data.success) {
                editItemModal.hide();

                // Show a loading message while refreshing the items
                showLoading('Refreshing knowledge items...');
                loadKnowledgeItems(false);
            } else {
                throw new Error(data.error || 'Failed to update item');
            }
        })
        .catch(error => {
            console.error('Error updating item:', error);
            hideLoading();
            alert('Error updating item: ' + error.message);
        });
        // Note: We don't call hideLoading() here because loadKnowledgeItems will handle that
    }

    /**
     * Approve item
     */
    function approveItem(itemId) {
        const item = allItems.find(item => item.id === itemId);
        if (!item) return;

        if (!confirm(`Are you sure you want to approve this knowledge item?`)) {
            return;
        }

        showLoading('Approving knowledge item...');

        fetch(`/properties/${propertyId}/knowledge/approve_qna`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                qna_id: itemId,
                status: 'approved',
                question: item.tags ? item.tags[0] : '',
                answer: item.content || ''
            })
        })
        .then(response => {
            if (!response.ok) {
                throw new Error('Network response was not ok');
            }
            return response.json();
        })
        .then(data => {
            if (data.success) {
                // Show a loading message while refreshing the items
                showLoading('Refreshing knowledge items...');
                loadKnowledgeItems(false);
            } else {
                throw new Error(data.error || 'Failed to approve item');
            }
        })
        .catch(error => {
            console.error('Error approving item:', error);
            hideLoading();
            alert('Error approving item: ' + error.message);
        });
        // Note: We don't call hideLoading() here because loadKnowledgeItems will handle that
    }

    /**
     * Delete item
     */
    function deleteItem(itemId) {
        if (!confirm(`Are you sure you want to delete this knowledge item? This action cannot be undone.`)) {
            return;
        }

        showLoading('Deleting knowledge item...');

        fetch(`/api/knowledge-items/${itemId}/delete`, {
            method: 'DELETE'
        })
        .then(response => {
            if (!response.ok) {
                throw new Error('Network response was not ok');
            }
            return response.json();
        })
        .then(data => {
            if (data.success) {
                // Show a loading message while refreshing the items
                showLoading('Refreshing knowledge items...');
                loadKnowledgeItems(false);
            } else {
                throw new Error(data.error || 'Failed to delete item');
            }
        })
        .catch(error => {
            console.error('Error deleting item:', error);
            hideLoading();
            alert('Error deleting item: ' + error.message);
        });
        // Note: We don't call hideLoading() here because loadKnowledgeItems will handle that
    }



    /**
     * Delete all knowledge
     */
    function deleteAllKnowledge() {
        console.log('Delete all knowledge button clicked');

        if (!confirm(`WARNING: You are about to delete ALL knowledge items for property "${propertyName}". This action CANNOT be undone. Are you sure?`)) {
            return;
        }

        // Double confirmation with text input
        const confirmationText = prompt("Type 'DELETE' below to confirm irreversible deletion:");
        if (confirmationText !== 'DELETE') {
            return;
        }

        // Disable the delete all button to prevent multiple clicks
        const deleteAllBtn = document.getElementById('deleteAllKnowledgeBtn');
        if (deleteAllBtn) {
            deleteAllBtn.disabled = true;
            deleteAllBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>Deleting...';
        }

        // Show the loading overlay
        showLoading('Deleting all knowledge items...');

        // Short delay to ensure the loading overlay is displayed
        setTimeout(() => {
            fetch(`/api/properties/${propertyId}/knowledge`, {
                method: 'DELETE'
            })
            .then(response => {
                if (!response.ok) {
                    throw new Error('Network response was not ok');
                }
                return response.json();
            })
            .then(data => {
                console.log('Delete all knowledge successful:', data);

                if (data.success) {
                    // Show a success message
                    alert('All knowledge has been successfully deleted.');

                    // Show a loading message while refreshing the items
                    showLoading('Refreshing knowledge items...');

                    // Load knowledge items and reset button when done
                    loadKnowledgeItems(false, () => {
                        // Reset the delete all button after everything is done
                        if (deleteAllBtn) {
                            deleteAllBtn.disabled = false;
                            deleteAllBtn.innerHTML = '<i class="bi bi-trash-fill me-1"></i> Delete All';
                        }
                    });
                } else {
                    throw new Error(data.error || 'Failed to delete all knowledge');
                }
            })
            .catch(error => {
                console.error('Error deleting all knowledge:', error);
                hideLoading();
                alert('Error deleting all knowledge: ' + error.message);

                // Re-enable the delete all button
                if (deleteAllBtn) {
                    deleteAllBtn.disabled = false;
                    deleteAllBtn.innerHTML = '<i class="bi bi-trash-fill me-1"></i> Delete All';
                }
            });
        }, 100); // Short delay to ensure the loading overlay is displayed
    }

    // Truncate text function removed as content is now fully displayed in the table

    /**
     * Show loading overlay with optional custom message
     * @param {string} message - Optional message to display
     */
    function showLoading(message = 'Processing...') {
        console.log('Showing loading overlay with message:', message);

        const overlay = document.getElementById('loadingOverlay');
        const loadingText = document.getElementById('loadingText');

        if (!overlay) {
            console.error('Loading overlay element not found');
            return;
        }

        // Set the loading message
        if (loadingText) {
            loadingText.textContent = message;
        }

        // Make sure it's not already showing
        if (overlay.classList.contains('active')) {
            console.log('Loading overlay already active, updating message only');
            return;
        }

        // First set display to flex to ensure proper centering
        overlay.style.display = 'flex';

        // Force a reflow to ensure the display change takes effect before adding the active class
        void overlay.offsetHeight;

        // Remove any inline styles that might interfere
        overlay.style.opacity = '';

        // Then add the active class for the transition
        requestAnimationFrame(() => {
            overlay.classList.add('active');
            console.log('Added active class to loading overlay');
        });

        // Prevent scrolling on the body while loading
        document.body.style.overflow = 'hidden';
    }

    /**
     * Hide loading overlay
     */
    function hideLoading() {
        console.log('Hiding loading overlay');

        const overlay = document.getElementById('loadingOverlay');
        if (!overlay) {
            console.error('Loading overlay element not found');
            return;
        }

        // Remove the active class to trigger the fade out transition
        overlay.classList.remove('active');
        console.log('Removed active class from loading overlay');

        // Wait for the transition to complete before hiding completely
        setTimeout(() => {
            // Only hide if it's still not active (in case showLoading was called again)
            if (!overlay.classList.contains('active')) {
                overlay.style.display = 'none';
                console.log('Set loading overlay display to none');

                // Re-enable scrolling
                document.body.style.overflow = '';
            }
        }, 300); // Match this to the CSS transition duration
    }
});
