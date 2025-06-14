// Content Management JavaScript
class ContentManager {
    constructor() {
        this.currentTab = 'users';
        this.currentPage = 1;
        this.searchTerm = '';
        this.perPage = 25;
        this.selectedItems = new Set();
        
        this.init();
    }
    
    init() {
        this.setupEventListeners();
        this.loadContent('users');
        this.loadSubdeadditsFilter();
    }
    
    setupEventListeners() {
        // Tab switching
        document.querySelectorAll('[data-bs-toggle="tab"]').forEach(tab => {
            tab.addEventListener('shown.bs.tab', (e) => {
                const tabId = e.target.getAttribute('data-bs-target').substring(1);
                this.switchTab(tabId);
            });
        });
        
        // Search inputs
        ['users', 'subdeaddits', 'posts', 'comments'].forEach(type => {
            const searchInput = document.getElementById(`${type}Search`);
            if (searchInput) {
                searchInput.addEventListener('input', (e) => {
                    this.searchTerm = e.target.value;
                    this.currentPage = 1;
                    this.loadContent(type);
                });
            }
        });
        
        // Select all checkboxes
        ['users', 'subdeaddits', 'posts', 'comments'].forEach(type => {
            const selectAllCheckbox = document.getElementById(`selectAll${this.capitalize(type)}`);
            if (selectAllCheckbox) {
                selectAllCheckbox.addEventListener('change', (e) => {
                    this.selectAll(type, e.target.checked);
                });
            }
        });
        
        // Bulk delete buttons
        ['users', 'subdeaddits', 'posts', 'comments'].forEach(type => {
            const deleteButton = document.getElementById(`deleteSelected${this.capitalize(type)}`);
            if (deleteButton) {
                deleteButton.addEventListener('click', () => {
                    this.bulkDelete(type);
                });
            }
        });
        
        // Posts subdeaddit filter
        const postsFilter = document.getElementById('postsSubdeadditFilter');
        if (postsFilter) {
            postsFilter.addEventListener('change', (e) => {
                this.currentPage = 1;
                this.loadContent('posts');
            });
        }
        
        // Modal save buttons
        document.getElementById('saveUserChanges')?.addEventListener('click', () => this.saveUser());
        document.getElementById('saveSubdeadditChanges')?.addEventListener('click', () => this.saveSubdeaddit());
        document.getElementById('savePostChanges')?.addEventListener('click', () => this.savePost());
        document.getElementById('saveCommentChanges')?.addEventListener('click', () => this.saveComment());
        
        // Delete confirmation
        document.getElementById('confirmDeleteBtn')?.addEventListener('click', () => this.executeDelete());
    }
    
    capitalize(str) {
        return str.charAt(0).toUpperCase() + str.slice(1);
    }
    
    switchTab(tabId) {
        this.currentTab = tabId;
        this.currentPage = 1;
        this.selectedItems.clear();
        this.searchTerm = '';
        
        // Clear search
        const searchInput = document.getElementById(`${tabId}Search`);
        if (searchInput) searchInput.value = '';
        
        this.loadContent(tabId);
    }
    
    async loadContent(type) {
        const url = new URL(`/admin/api/${type}`, window.location.origin);
        url.searchParams.set('page', this.currentPage);
        url.searchParams.set('per_page', this.perPage);
        
        if (this.searchTerm) {
            url.searchParams.set('search', this.searchTerm);
        }
        
        if (type === 'posts') {
            const subdeadditFilter = document.getElementById('postsSubdeadditFilter')?.value;
            if (subdeadditFilter) {
                url.searchParams.set('subdeaddit', subdeadditFilter);
            }
        }
        
        try {
            const response = await fetch(url);
            const data = await response.json();
            
            if (type === 'users') {
                this.renderUsers(data);
            } else if (type === 'subdeaddits') {
                this.renderSubdeaddits(data);
            } else if (type === 'posts') {
                this.renderPosts(data);
            } else if (type === 'comments') {
                this.renderComments(data);
            }
            
            this.renderPagination(type, data);
        } catch (error) {
            console.error('Error loading content:', error);
            this.showAlert('Error loading content', 'danger');
        }
    }
    
    renderUsers(data) {
        const tbody = document.querySelector('#usersTable tbody');
        tbody.innerHTML = '';
        
        data.users.forEach(user => {
            const row = document.createElement('tr');
            row.innerHTML = `
                <td><input type="checkbox" class="item-checkbox" data-id="${user.username}"></td>
                <td>${user.username}</td>
                <td>${user.age || ''}</td>
                <td>${user.gender || ''}</td>
                <td>${user.occupation || ''}</td>
                <td>${user.posts_count}</td>
                <td>${user.comments_count}</td>
                <td>
                    <button class="btn btn-sm btn-primary" onclick="contentManager.editUser('${user.username}')">
                        <i class="bi bi-pencil"></i>
                    </button>
                    <button class="btn btn-sm btn-danger" onclick="contentManager.deleteUser('${user.username}')">
                        <i class="bi bi-trash"></i>
                    </button>
                </td>
            `;
            tbody.appendChild(row);
        });
        
        this.setupItemCheckboxes();
    }
    
    renderSubdeaddits(data) {
        const tbody = document.querySelector('#subdeadditsTable tbody');
        tbody.innerHTML = '';
        
        data.subdeaddits.forEach(sub => {
            const row = document.createElement('tr');
            row.innerHTML = `
                <td><input type="checkbox" class="item-checkbox" data-id="${sub.name}"></td>
                <td>${sub.name}</td>
                <td>${this.truncate(sub.description, 100)}</td>
                <td>${sub.posts_count}</td>
                <td>-</td>
                <td>
                    <button class="btn btn-sm btn-primary" onclick="contentManager.editSubdeaddit('${sub.name}')">
                        <i class="bi bi-pencil"></i>
                    </button>
                    <button class="btn btn-sm btn-danger" onclick="contentManager.deleteSubdeaddit('${sub.name}')">
                        <i class="bi bi-trash"></i>
                    </button>
                </td>
            `;
            tbody.appendChild(row);
        });
        
        this.setupItemCheckboxes();
    }
    
    renderPosts(data) {
        const tbody = document.querySelector('#postsTable tbody');
        tbody.innerHTML = '';
        
        data.posts.forEach(post => {
            const row = document.createElement('tr');
            const createdDate = new Date(post.created_at).toLocaleDateString();
            row.innerHTML = `
                <td><input type="checkbox" class="item-checkbox" data-id="${post.id}"></td>
                <td>${this.truncate(post.title, 50)}</td>
                <td>${post.username}</td>
                <td>${post.subdeaddit_name}</td>
                <td>${post.upvote_count}</td>
                <td>${post.comments_count}</td>
                <td>${createdDate}</td>
                <td>
                    <button class="btn btn-sm btn-primary" onclick="contentManager.editPost(${post.id})">
                        <i class="bi bi-pencil"></i>
                    </button>
                    <button class="btn btn-sm btn-danger" onclick="contentManager.deletePost(${post.id})">
                        <i class="bi bi-trash"></i>
                    </button>
                    <a href="/post/${post.id}" class="btn btn-sm btn-info" target="_blank">
                        <i class="bi bi-eye"></i>
                    </a>
                </td>
            `;
            tbody.appendChild(row);
        });
        
        this.setupItemCheckboxes();
    }
    
    renderComments(data) {
        const tbody = document.querySelector('#commentsTable tbody');
        tbody.innerHTML = '';
        
        data.comments.forEach(comment => {
            const row = document.createElement('tr');
            const createdDate = new Date(comment.created_at).toLocaleDateString();
            row.innerHTML = `
                <td><input type="checkbox" class="item-checkbox" data-id="${comment.id}"></td>
                <td>${this.truncate(comment.content, 80)}</td>
                <td>${comment.username}</td>
                <td>${this.truncate(comment.post_title, 30)}</td>
                <td>${comment.parent_id ? 'Reply' : 'Root'}</td>
                <td>${comment.upvote_count}</td>
                <td>${createdDate}</td>
                <td>
                    <button class="btn btn-sm btn-primary" onclick="contentManager.editComment(${comment.id})">
                        <i class="bi bi-pencil"></i>
                    </button>
                    <button class="btn btn-sm btn-danger" onclick="contentManager.deleteComment(${comment.id})">
                        <i class="bi bi-trash"></i>
                    </button>
                    <a href="/post/${comment.post_id}" class="btn btn-sm btn-info" target="_blank">
                        <i class="bi bi-eye"></i>
                    </a>
                </td>
            `;
            tbody.appendChild(row);
        });
        
        this.setupItemCheckboxes();
    }
    
    renderPagination(type, data) {
        const pagination = document.getElementById(`${type}Pagination`);
        pagination.innerHTML = '';
        
        if (data.pages <= 1) return;
        
        // Previous button
        if (data.current_page > 1) {
            const prevLi = document.createElement('li');
            prevLi.className = 'page-item';
            prevLi.innerHTML = `<a class="page-link" href="#" onclick="contentManager.goToPage(${data.current_page - 1})">Previous</a>`;
            pagination.appendChild(prevLi);
        }
        
        // Page numbers
        const startPage = Math.max(1, data.current_page - 2);
        const endPage = Math.min(data.pages, data.current_page + 2);
        
        for (let i = startPage; i <= endPage; i++) {
            const li = document.createElement('li');
            li.className = `page-item ${i === data.current_page ? 'active' : ''}`;
            li.innerHTML = `<a class="page-link" href="#" onclick="contentManager.goToPage(${i})">${i}</a>`;
            pagination.appendChild(li);
        }
        
        // Next button
        if (data.current_page < data.pages) {
            const nextLi = document.createElement('li');
            nextLi.className = 'page-item';
            nextLi.innerHTML = `<a class="page-link" href="#" onclick="contentManager.goToPage(${data.current_page + 1})">Next</a>`;
            pagination.appendChild(nextLi);
        }
    }
    
    goToPage(page) {
        this.currentPage = page;
        this.loadContent(this.currentTab);
    }
    
    setupItemCheckboxes() {
        document.querySelectorAll('.item-checkbox').forEach(checkbox => {
            checkbox.addEventListener('change', (e) => {
                const id = e.target.getAttribute('data-id');
                if (e.target.checked) {
                    this.selectedItems.add(id);
                } else {
                    this.selectedItems.delete(id);
                    // Uncheck select all if any item is unchecked
                    const selectAllCheckbox = document.getElementById(`selectAll${this.capitalize(this.currentTab)}`);
                    if (selectAllCheckbox) selectAllCheckbox.checked = false;
                }
            });
        });
    }
    
    selectAll(type, checked) {
        document.querySelectorAll('.item-checkbox').forEach(checkbox => {
            checkbox.checked = checked;
            const id = checkbox.getAttribute('data-id');
            if (checked) {
                this.selectedItems.add(id);
            } else {
                this.selectedItems.delete(id);
            }
        });
    }
    
    truncate(text, length) {
        if (!text) return '';
        return text.length > length ? text.substring(0, length) + '...' : text;
    }
    
    async loadSubdeadditsFilter() {
        try {
            const response = await fetch('/admin/api/subdeaddits?per_page=1000');
            const data = await response.json();
            
            const select = document.getElementById('postsSubdeadditFilter');
            if (select) {
                data.subdeaddits.forEach(sub => {
                    const option = document.createElement('option');
                    option.value = sub.name;
                    option.textContent = sub.name;
                    select.appendChild(option);
                });
            }
        } catch (error) {
            console.error('Error loading subdeaddits filter:', error);
        }
    }
    
    // Edit functions
    async editUser(username) {
        try {
            const response = await fetch(`/admin/api/users?search=${username}&per_page=1`);
            const data = await response.json();
            const user = data.users.find(u => u.username === username);
            
            if (!user) return;
            
            // Populate form
            document.getElementById('editUserId').value = username;
            document.getElementById('editUserUsername').value = user.username;
            document.getElementById('editUserAge').value = user.age || '';
            document.getElementById('editUserGender').value = user.gender || '';
            document.getElementById('editUserOccupation').value = user.occupation || '';
            document.getElementById('editUserEducation').value = user.education || '';
            document.getElementById('editUserBio').value = user.bio || '';
            document.getElementById('editUserInterests').value = user.interests || '';
            document.getElementById('editUserPersonality').value = user.personality_traits || '';
            document.getElementById('editUserWritingStyle').value = user.writing_style || '';
            
            // Show modal
            new bootstrap.Modal(document.getElementById('editUserModal')).show();
        } catch (error) {
            console.error('Error loading user:', error);
            this.showAlert('Error loading user data', 'danger');
        }
    }
    
    async editSubdeaddit(name) {
        try {
            const response = await fetch(`/admin/api/subdeaddits?search=${name}&per_page=1`);
            const data = await response.json();
            const sub = data.subdeaddits.find(s => s.name === name);
            
            if (!sub) return;
            
            // Populate form
            document.getElementById('editSubdeadditId').value = name;
            document.getElementById('editSubdeadditName').value = sub.name;
            document.getElementById('editSubdeadditDescription').value = sub.description || '';
            document.getElementById('editSubdeadditPostTypes').value = sub.post_types || '';
            
            // Show modal
            new bootstrap.Modal(document.getElementById('editSubdeadditModal')).show();
        } catch (error) {
            console.error('Error loading subdeaddit:', error);
            this.showAlert('Error loading subdeaddit data', 'danger');
        }
    }
    
    async editPost(id) {
        try {
            const response = await fetch(`/admin/api/posts?per_page=1000`);
            const data = await response.json();
            const post = data.posts.find(p => p.id === id);
            
            if (!post) return;
            
            // Populate form
            document.getElementById('editPostId').value = id;
            document.getElementById('editPostTitle').value = post.title;
            document.getElementById('editPostContent').value = post.content;
            document.getElementById('editPostUpvotes').value = post.upvote_count;
            document.getElementById('editPostType').value = post.post_type || '';
            
            // Show modal
            new bootstrap.Modal(document.getElementById('editPostModal')).show();
        } catch (error) {
            console.error('Error loading post:', error);
            this.showAlert('Error loading post data', 'danger');
        }
    }
    
    async editComment(id) {
        try {
            const response = await fetch(`/admin/api/comments?per_page=1000`);
            const data = await response.json();
            const comment = data.comments.find(c => c.id === id);
            
            if (!comment) return;
            
            // Populate form
            document.getElementById('editCommentId').value = id;
            document.getElementById('editCommentContent').value = comment.content;
            document.getElementById('editCommentUpvotes').value = comment.upvote_count;
            
            // Show modal
            new bootstrap.Modal(document.getElementById('editCommentModal')).show();
        } catch (error) {
            console.error('Error loading comment:', error);
            this.showAlert('Error loading comment data', 'danger');
        }
    }
    
    // Save functions
    async saveUser() {
        const username = document.getElementById('editUserId').value;
        const data = {
            age: parseInt(document.getElementById('editUserAge').value) || null,
            gender: document.getElementById('editUserGender').value,
            occupation: document.getElementById('editUserOccupation').value,
            education: document.getElementById('editUserEducation').value,
            bio: document.getElementById('editUserBio').value,
            interests: document.getElementById('editUserInterests').value,
            personality_traits: document.getElementById('editUserPersonality').value,
            writing_style: document.getElementById('editUserWritingStyle').value
        };
        
        try {
            const response = await fetch(`/admin/api/users/${username}`, {
                method: 'PUT',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(data)
            });
            
            const result = await response.json();
            if (result.success) {
                bootstrap.Modal.getInstance(document.getElementById('editUserModal')).hide();
                this.loadContent('users');
                this.showAlert('User updated successfully', 'success');
            } else {
                this.showAlert('Error updating user: ' + result.error, 'danger');
            }
        } catch (error) {
            console.error('Error saving user:', error);
            this.showAlert('Error saving user', 'danger');
        }
    }
    
    async saveSubdeaddit() {
        const name = document.getElementById('editSubdeadditId').value;
        const data = {
            description: document.getElementById('editSubdeadditDescription').value,
            post_types: document.getElementById('editSubdeadditPostTypes').value
        };
        
        try {
            const response = await fetch(`/admin/api/subdeaddits/${name}`, {
                method: 'PUT',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(data)
            });
            
            const result = await response.json();
            if (result.success) {
                bootstrap.Modal.getInstance(document.getElementById('editSubdeadditModal')).hide();
                this.loadContent('subdeaddits');
                this.showAlert('Subdeaddit updated successfully', 'success');
            } else {
                this.showAlert('Error updating subdeaddit: ' + result.error, 'danger');
            }
        } catch (error) {
            console.error('Error saving subdeaddit:', error);
            this.showAlert('Error saving subdeaddit', 'danger');
        }
    }
    
    async savePost() {
        const id = document.getElementById('editPostId').value;
        const data = {
            title: document.getElementById('editPostTitle').value,
            content: document.getElementById('editPostContent').value,
            upvote_count: parseInt(document.getElementById('editPostUpvotes').value) || 0,
            post_type: document.getElementById('editPostType').value
        };
        
        try {
            const response = await fetch(`/admin/api/posts/${id}`, {
                method: 'PUT',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(data)
            });
            
            const result = await response.json();
            if (result.success) {
                bootstrap.Modal.getInstance(document.getElementById('editPostModal')).hide();
                this.loadContent('posts');
                this.showAlert('Post updated successfully', 'success');
            } else {
                this.showAlert('Error updating post: ' + result.error, 'danger');
            }
        } catch (error) {
            console.error('Error saving post:', error);
            this.showAlert('Error saving post', 'danger');
        }
    }
    
    async saveComment() {
        const id = document.getElementById('editCommentId').value;
        const data = {
            content: document.getElementById('editCommentContent').value,
            upvote_count: parseInt(document.getElementById('editCommentUpvotes').value) || 0
        };
        
        try {
            const response = await fetch(`/admin/api/comments/${id}`, {
                method: 'PUT',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(data)
            });
            
            const result = await response.json();
            if (result.success) {
                bootstrap.Modal.getInstance(document.getElementById('editCommentModal')).hide();
                this.loadContent('comments');
                this.showAlert('Comment updated successfully', 'success');
            } else {
                this.showAlert('Error updating comment: ' + result.error, 'danger');
            }
        } catch (error) {
            console.error('Error saving comment:', error);
            this.showAlert('Error saving comment', 'danger');
        }
    }
    
    // Delete functions
    deleteUser(username) {
        this.showDeleteConfirmation('user', username, `Are you sure you want to delete user "${username}"?`);
    }
    
    deleteSubdeaddit(name) {
        this.showDeleteConfirmation('subdeaddit', name, `Are you sure you want to delete subdeaddit "${name}"?`);
    }
    
    deletePost(id) {
        this.showDeleteConfirmation('post', id, `Are you sure you want to delete this post?`);
    }
    
    deleteComment(id) {
        this.showDeleteConfirmation('comment', id, `Are you sure you want to delete this comment?`);
    }
    
    bulkDelete(type) {
        if (this.selectedItems.size === 0) {
            this.showAlert('No items selected', 'warning');
            return;
        }
        
        const count = this.selectedItems.size;
        const message = `Are you sure you want to delete ${count} ${type}?`;
        this.showDeleteConfirmation(`bulk-${type}`, Array.from(this.selectedItems), message);
    }
    
    showDeleteConfirmation(type, id, message) {
        this.pendingDelete = { type, id };
        
        document.getElementById('deleteConfirmMessage').textContent = message;
        
        // Show impact warning for cascading deletes
        const warningDiv = document.getElementById('deleteImpactWarning');
        if (type === 'user' || type === 'subdeaddit' || type === 'post' || type === 'comment') {
            warningDiv.style.display = 'block';
            if (type === 'user') {
                document.getElementById('deleteImpactText').textContent = 'This will also delete all posts and comments by this user.';
            } else if (type === 'subdeaddit') {
                document.getElementById('deleteImpactText').textContent = 'This will also delete all posts and comments in this subdeaddit.';
            } else if (type === 'post') {
                document.getElementById('deleteImpactText').textContent = 'This will also delete all comments on this post.';
            } else if (type === 'comment') {
                document.getElementById('deleteImpactText').textContent = 'This will also delete all replies to this comment.';
            }
        } else {
            warningDiv.style.display = 'none';
        }
        
        new bootstrap.Modal(document.getElementById('deleteConfirmModal')).show();
    }
    
    async executeDelete() {
        const { type, id } = this.pendingDelete;
        
        try {
            let response;
            
            if (type.startsWith('bulk-')) {
                const bulkType = type.replace('bulk-', '');
                const endpoint = `/admin/api/${bulkType}/bulk-delete`;
                const bodyKey = bulkType === 'users' ? 'usernames' : 
                               bulkType === 'subdeaddits' ? 'names' :
                               bulkType === 'posts' ? 'post_ids' : 'comment_ids';
                
                response = await fetch(endpoint, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({[bodyKey]: id})
                });
            } else {
                let endpoint;
                if (type === 'user') endpoint = `/admin/api/users/${id}`;
                else if (type === 'subdeaddit') endpoint = `/admin/api/subdeaddits/${id}`;
                else if (type === 'post') endpoint = `/admin/api/posts/${id}`;
                else if (type === 'comment') endpoint = `/admin/api/comments/${id}`;
                
                response = await fetch(endpoint, { method: 'DELETE' });
            }
            
            const result = await response.json();
            if (result.success) {
                bootstrap.Modal.getInstance(document.getElementById('deleteConfirmModal')).hide();
                this.selectedItems.clear();
                this.loadContent(this.currentTab);
                
                let message = 'Deleted successfully';
                if (result.deleted) {
                    const deleted = result.deleted;
                    message = `Deleted: ${Object.entries(deleted).map(([k,v]) => `${v} ${k}`).join(', ')}`;
                }
                this.showAlert(message, 'success');
            } else {
                this.showAlert('Error deleting: ' + result.error, 'danger');
            }
        } catch (error) {
            console.error('Error deleting:', error);
            this.showAlert('Error deleting content', 'danger');
        }
    }
    
    showAlert(message, type) {
        // Create alert element
        const alert = document.createElement('div');
        alert.className = `alert alert-${type} alert-dismissible fade show position-fixed`;
        alert.style.cssText = 'top: 20px; right: 20px; z-index: 9999; min-width: 300px;';
        alert.innerHTML = `
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;
        
        document.body.appendChild(alert);
        
        // Auto-dismiss after 5 seconds
        setTimeout(() => {
            if (alert.parentNode) {
                alert.remove();
            }
        }, 5000);
    }
}

// Initialize content manager when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    window.contentManager = new ContentManager();
});