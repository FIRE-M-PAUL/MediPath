// admin/admin.js - Shared Admin Logic
document.addEventListener('DOMContentLoaded', () => {
    // 1. Mandatory Auth Check
    if (typeof Auth !== 'undefined') {
        Auth.requireAuth('admin');
    }

    // 2. Render Sidebar
    const mainContent = document.querySelector('.main-content');
    if (mainContent) {
        initAdminUI();
        initMobileNav();
    }
});

function initMobileNav() {
    // Create overlay if not present
    if (!document.querySelector('.sidebar-overlay')) {
        const overlay = document.createElement('div');
        overlay.className = 'sidebar-overlay';
        overlay.onclick = toggleSidebar;
        document.body.appendChild(overlay);
    }
}

window.toggleSidebar = function() {
    const sidebar = document.querySelector('.sidebar');
    const overlay = document.querySelector('.sidebar-overlay');
    if (sidebar && overlay) {
        const isOpen = sidebar.classList.toggle('open');
        overlay.classList.toggle('visible', isOpen);
        document.body.classList.toggle('sidebar-open', isOpen);
    }
};

function initAdminUI() {
    const currentPage = window.location.pathname.split('/').pop() || 'admin-dashboard.html';
    
    // Highlight active sidebar link
    document.querySelectorAll('.sidebar-link').forEach(link => {
        const target = link.getAttribute('href');
        if (target === currentPage) {
            link.classList.add('active');
        } else {
            link.classList.remove('active');
        }
    });

    // Check for stats on dashboard
    if (currentPage === 'admin-dashboard.html') {
        updateDashboardStats();
    }
}

async function updateDashboardStats() {
    const doctors = await API.getDoctors();
    const appts = await API.getAdminAppointments();
    const pendingResult = await API.getPendingDoctors();
    const usersResult = await API.getUsers();

    // Backend returns raw arrays — guard against both array and error-object responses
    const pendingDocs = Array.isArray(pendingResult) ? pendingResult
                      : (Array.isArray(pendingResult.data) ? pendingResult.data : []);
    const usersArray  = Array.isArray(usersResult) ? usersResult : [];
    const patients = usersArray.filter(u => u.role === 'patient');
    
    // Dashboard Stats
    const statDocs = document.getElementById('stat-doctors');
    const statAppts = document.getElementById('stat-appointments');
    const statPending = document.getElementById('stat-pending');
    const statPatients = document.getElementById('stat-patients');

    if (statDocs) statDocs.textContent = doctors.length || 0;
    if (statAppts) statAppts.textContent = appts.length || 0;
    if (statPending) statPending.textContent = pendingDocs.length || 0;
    if (statPatients) statPatients.textContent = patients.length || 0;

    // Sidebar Badge Logic
    updateSidebarBadges(pendingDocs.length);

    // Dashboard "Action Required" Visibility
    const actionCard = document.getElementById('pending-action-card');
    if (actionCard) {
        actionCard.style.display = pendingDocs.length > 0 ? 'block' : 'none';
        const pendingCountText = document.getElementById('pending-count-text');
        if (pendingCountText) pendingCountText.textContent = pendingDocs.length;
    }
}

function updateSidebarBadges(count) {
    const verifyLink = document.querySelector('a[href="admin-doctors.html"]');
    if (verifyLink) {
        let badge = verifyLink.querySelector('.nav-badge');
        if (count > 0) {
            if (!badge) {
                badge = document.createElement('span');
                badge.className = 'nav-badge';
                badge.style.cssText = 'background:#ef4444; color:white; font-size:0.7rem; padding:0.1rem 0.4rem; border-radius:10px; margin-left:auto; font-weight:700;';
                verifyLink.style.display = 'flex';
                verifyLink.style.alignItems = 'center';
                verifyLink.appendChild(badge);
            }
            badge.textContent = count;
        } else if (badge) {
            badge.remove();
        }
    }
}

function logoutAdmin() {
    Auth.logout();
    window.location.href = 'admin-login.html';
}

// Global functions for data management (will be used by specific pages)
window.approveDoctor = async function(id) {
    const result = await API.verifyDoctor(id, 'approve');
    if (result.success) {
        showToast('Physician approved successfully.', 'success');
        if (typeof renderDoctorsTable === 'function') renderDoctorsTable();
        updateDashboardStats();
    }
};

window.rejectDoctor = async function(id) {
    const reason = prompt("Please provide a reason for rejection (e.g., Invalid License Number):");
    if (reason === null) return;
    
    const finalReason = reason.trim() || "Information provided does not meet our verification standards.";
    const result = await API.verifyDoctor(id, 'reject', finalReason);
    
    if (result.success) {
        showToast('Physician application rejected.', 'error');
        if (typeof renderDoctorsTable === 'function') renderDoctorsTable();
        updateDashboardStats();
    }
};

window.promoteToAdmin = async function(userId) {
    if (confirm("Are you sure you want to promote this user to Administrator? This action grants full system access.")) {
        const result = await API.promoteUser(userId);
        if (result.success) {
            showToast(result.message, 'success');
            if (typeof renderPatientsTable === 'function') renderPatientsTable();
        }
    }
};

window.cancelAppt = async function(id) {
    const reason = prompt("Please state the reason for cancellation:");
    if (reason === null) return;

    const finalReason = reason.trim() || "Administrative override.";
    const result = await API.adminCancelAppointment(id, finalReason);
    if (result && result.success) {
        showToast('Appointment cancelled by admin.', 'success');
        if (typeof renderApptsTable === 'function') renderApptsTable();
        return;
    }
    showToast(result?.message || 'Unable to cancel appointment.', 'error');
};

window.deletePatient = async function(userId) {
    if (!confirm('Delete this patient and related records? This cannot be undone.')) return;
    const result = await API.deletePatient(userId);
    if (result && result.success) {
        showToast(result.message || 'Patient deleted.', 'success');
        if (typeof renderPatientsTable === 'function') renderPatientsTable();
        return;
    }
    showToast(result?.message || 'Failed to delete patient.', 'error');
};
