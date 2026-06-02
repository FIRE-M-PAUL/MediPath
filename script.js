// ============================================================
// script.js — MediPath Core Logic, Auth & Navigation
// ============================================================

(function (w) {
    const PW_ICON_EYE = '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z"/><circle cx="12" cy="12" r="3"/></svg>';
    const PW_ICON_EYE_OFF = '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9.88 9.88a3 3 0 1 0 4.24 4.24"/><path d="M10.73 5.08A10.43 10.43 0 0 1 12 5c7 0 10 7 10 7a13.16 13.16 0 0 1-1.67 2.68"/><path d="M6.61 6.61A13.526 13.526 0 0 0 2 12s3 7 10 7a9.74 9.74 0 0 0 5.39-1.61"/><line x1="2" y1="2" x2="22" y2="22"/></svg>';
    w.MediPathPasswordToggle = {
        /** @param {HTMLButtonElement|null|undefined} btn */
        setIcon(btn, plainTextVisible) {
            if (btn) btn.innerHTML = plainTextVisible ? PW_ICON_EYE_OFF : PW_ICON_EYE;
        }
    };

    // Shared phone validator — must mirror backend rules in backend/app.py.
    const PHONE_PREFIXES = ['095', '096', '076', '097', '077'];
    const PHONE_REGEX = new RegExp('^(?:' + PHONE_PREFIXES.join('|') + ')\\d{7}$');
    const PHONE_INVALID_MESSAGE =
        'Invalid phone number. Please enter a valid Zambian mobile number starting with 095, 096, 076, 097, or 077.';

    function _phonePrefixIsPartiallyValid(digits) {
        if (digits.length === 0) return true;
        if (digits.length <= 3) {
            return PHONE_PREFIXES.some(p => p.startsWith(digits));
        }
        return PHONE_PREFIXES.includes(digits.slice(0, 3));
    }

    w.MediPathPhone = {
        prefixes: PHONE_PREFIXES,
        regex: PHONE_REGEX,
        invalidMessage: PHONE_INVALID_MESSAGE,
        normalize(value) {
            return String(value == null ? '' : value).replace(/\D/g, '');
        },
        prefixIsPartiallyValid: _phonePrefixIsPartiallyValid,
        validate(value) {
            const digits = this.normalize(value);
            if (!digits) return 'Please enter your phone number.';
            if (digits.length !== 10) {
                return 'Phone number must be exactly 10 digits.';
            }
            if (!/^\d+$/.test(digits)) {
                return 'Phone number must contain numbers only.';
            }
            if (!PHONE_REGEX.test(digits)) {
                return this.invalidMessage;
            }
            return '';
        },

        /**
         * Live-validate a phone input so the user can never commit characters
         * that drift outside the approved Zambian mobile prefixes.
         *
         *   opts.errorTextEl       <span> that receives the error text
         *   opts.errorContainerEl  element whose `visible` class / display we toggle
         *   opts.onError(msg)      callback fired when typing is rejected
         *   opts.onClear()         callback fired when the field is acceptable
         *   opts.useToast          when true, also surface invalid prefix via showToast
         *   opts.toastDebounceMs   throttle for toast (default 1500ms)
         */
        attachLiveInput(input, opts = {}) {
            if (!input || input.dataset.mpPhoneBound === '1') return;
            input.dataset.mpPhoneBound = '1';

            input.setAttribute('maxlength', '10');
            input.setAttribute('inputmode', 'numeric');
            input.setAttribute('autocomplete', input.getAttribute('autocomplete') || 'tel');

            if (input.dataset.mpLastValid == null) {
                input.dataset.mpLastValid = this.normalize(input.value);
                input.value = input.dataset.mpLastValid;
            }

            const errorTextEl = opts.errorTextEl || null;
            const errorContainerEl = opts.errorContainerEl || null;
            const onError = typeof opts.onError === 'function' ? opts.onError : null;
            const onClear = typeof opts.onClear === 'function' ? opts.onClear : null;
            const useToast = opts.useToast === true;
            const toastDebounceMs = typeof opts.toastDebounceMs === 'number'
                ? opts.toastDebounceMs : 1500;
            let lastToastAt = 0;

            const showErrorMsg = (msg) => {
                if (errorTextEl) errorTextEl.textContent = msg;
                if (errorContainerEl) {
                    errorContainerEl.classList.add('visible');
                    if (errorContainerEl.style) errorContainerEl.style.display = '';
                }
                input.classList.add('input-error');
                input.classList.remove('input-success');
                input.setAttribute('aria-invalid', 'true');
                if (useToast && typeof showToast === 'function') {
                    const now = Date.now();
                    if (now - lastToastAt > toastDebounceMs) {
                        lastToastAt = now;
                        showToast(msg, 'error');
                    }
                }
                if (onError) onError(msg);
            };

            const clearErrorMsg = () => {
                if (errorTextEl) errorTextEl.textContent = '';
                if (errorContainerEl) {
                    errorContainerEl.classList.remove('visible');
                }
                input.classList.remove('input-error');
                input.setAttribute('aria-invalid', 'false');
                if (onClear) onClear();
            };

            const handleInput = () => {
                let digits = this.normalize(input.value).slice(0, 10);
                if (digits.length === 0) {
                    input.value = '';
                    input.dataset.mpLastValid = '';
                    clearErrorMsg();
                    return;
                }
                if (!_phonePrefixIsPartiallyValid(digits)) {
                    // Reject the new keystroke entirely.
                    input.value = input.dataset.mpLastValid || '';
                    showErrorMsg(PHONE_INVALID_MESSAGE);
                    return;
                }
                input.value = digits;
                input.dataset.mpLastValid = digits;
                clearErrorMsg();
            };

            const handleBlur = () => {
                const v = this.normalize(input.value);
                if (v.length > 0 && v.length < 10) {
                    showErrorMsg('Phone number must be exactly 10 digits.');
                }
            };

            // Reject pasted text that breaks the prefix rule before it lands.
            const handlePaste = (e) => {
                try {
                    const pasted = (e.clipboardData || window.clipboardData).getData('text');
                    const combined = (input.value + pasted);
                    const digits = this.normalize(combined).slice(0, 10);
                    if (digits.length && !_phonePrefixIsPartiallyValid(digits)) {
                        e.preventDefault();
                        showErrorMsg(PHONE_INVALID_MESSAGE);
                    }
                } catch (_) { /* fallback to input handler */ }
            };

            input.addEventListener('input', handleInput);
            input.addEventListener('blur', handleBlur);
            input.addEventListener('paste', handlePaste);

            // Initial sweep so a prefilled value gets validated too.
            handleInput();
        }
    };
})(typeof window !== 'undefined' ? window : globalThis);

// -- 1. Backend API Integration --
const API_BASE = 'http://127.0.0.1:5005/api';
let _csrfToken = null;

const API = {
    async getCsrfToken(force = false) {
        if (_csrfToken && !force) return _csrfToken;
        try {
            const response = await fetch(`${API_BASE}/csrf-token`, { method: 'GET' });
            const payload = await response.json();
            _csrfToken = payload.csrf_token || null;
            return _csrfToken;
        } catch (e) {
            console.error('Failed to load CSRF token:', e);
            return null;
        }
    },
    async request(endpoint, method = 'GET', data = null) {
        const upperMethod = String(method || 'GET').toUpperCase();
        const headers = { 'Content-Type': 'application/json' };
        if (['POST', 'PUT', 'PATCH', 'DELETE'].includes(upperMethod)) {
            const token = await this.getCsrfToken();
            if (token) headers['X-CSRFToken'] = token;
        }
        const options = {
            method,
            headers
        };
        if (data) options.body = JSON.stringify(data);
        
        try {
            const response = await fetch(`${API_BASE}${endpoint}`, options);
            if (response.status === 401 && endpoint === '/auth/login') {
                let payload = {};
                try {
                    payload = await response.json();
                } catch (_) {}
                return {
                    success: false,
                    message: payload.message || 'Invalid credentials.',
                    unauthorized: true
                };
            }
            if (response.status === 401) {
                const message = 'Your session has expired. Please log in again.';
                try { showToast(message, 'error'); } catch (_) {}
                try { localStorage.removeItem('mediPath_session'); } catch (_) {}
                if (!window.location.pathname.endsWith('login.html')) {
                    window.location.href = window.location.pathname.includes('/admin/')
                        ? 'admin-login.html'
                        : 'login.html';
                }
                return { success: false, message, unauthorized: true };
            }
            const ct = (response.headers.get('content-type') || '').toLowerCase();
            let result;
            if (ct.includes('application/json')) {
                result = await response.json();
            } else {
                const text = await response.text();
                if (!response.ok) {
                    throw new Error(`Server error (${response.status}). Please restart the backend or try again.`);
                }
                try {
                    result = JSON.parse(text);
                } catch (_) {
                    throw new Error('Invalid response from server.');
                }
            }
            if (!response.ok) {
                if (response.status === 400 && (result.message || '').toLowerCase().includes('csrf')) {
                    await this.getCsrfToken(true);
                }
                throw new Error(result.message || 'API Request Failed');
            }
            return result;
        } catch (error) {
            console.error(`API Error (${endpoint}):`, error);
            showToast(error.message, 'error');
            return { success: false, message: error.message };
        }
    },
    get(endpoint) { return this.request(endpoint, 'GET'); },
    post(endpoint, data) { return this.request(endpoint, 'POST', data); },
    put(endpoint, data) { return this.request(endpoint, 'PUT', data); },
    delete(endpoint) { return this.request(endpoint, 'DELETE'); },

    // Auth
    login(email, password, role) { return this.request('/auth/login', 'POST', { email, password, role }); },
    register(data, role) { return this.request('/auth/register', 'POST', { ...data, role }); },
    logout() { return this.request('/auth/logout'); },
    getMe() { return this.request('/auth/me'); },

    // Core Data
    getDoctors(params = null) {
        if (params && typeof params === 'object') {
            const qs = new URLSearchParams(params).toString();
            return this.request(`/doctors?${qs}`);
        }
        return this.request('/doctors');
    },
    getAppointments() { return this.request('/appointments/user'); },
    bookAppointment(data) { return this.request('/appointments', 'POST', data); },
    createClinicalAppointment(data) { return this.request('/clinical/appointments', 'POST', data); },
    getClinicalAppointments() { return this.request('/clinical/appointments'); },
    getNotifications() { return this.request('/notifications'); },
    getRecentActivity() { return this.request('/activity/recent'); },
    markNotificationRead(id) { return this.request(`/notifications/${id}/read`, 'POST'); },
    analyzeSymptoms(symptoms) { return this.request('/symptom-analyze', 'POST', { symptoms }); },
    getDashboardStats() { return this.request('/dashboard/stats'); },
    getMedicalRecords() { return this.request('/medical-records'); },
    addMedicalRecord(data) { return this.request('/medical-records', 'POST', data); },
    updateMedicalRecord(id, data) { return this.request(`/medical-records/${id}`, 'PUT', data); },
    deleteMedicalRecord(id) { return this.request(`/medical-records/${id}`, 'DELETE'); },

    // Admin
    getUsers(params = null) {
        if (params && typeof params === 'object') {
            const qs = new URLSearchParams(params).toString();
            return this.request(`/patients?${qs}`);
        }
        return this.request('/admin/users');
    },
    getAdminAppointments() { return this.request('/admin/appointments'); },
    getPendingDoctors() { return this.request('/admin/pending-doctors'); },
    getAdminClinicalDoctors() { return this.request('/admin/clinical-doctors'); },
    getAdminApprovedDoctors() { return this.request('/admin/approved-doctors'); },
    getDoctorDetail(id) { return this.request(`/admin/doctor-detail/${id}`); },
    updateClinicalAppointment(id, data) { return this.request(`/clinical/appointments/${id}`, 'PUT', data); },
    verifyDoctor(id, action, reason = '') { return this.request('/admin/verify-doctor', 'POST', { doctor_id: id, action, reason }); },
    promoteUser(userId) { return this.request('/admin/promote', 'POST', { user_id: userId }); },
    deletePatient(userId) { return this.request(`/patients/${userId}`, 'DELETE'); },
    adminCancelAppointment(id, reason) { return this.request(`/admin/appointments/${id}/cancel`, 'POST', { reason }); },
    getAdminReportSummary() { return this.request('/admin/reports/summary'); },
    getDoctorProfile() { return this.request('/doctor/profile'); },
    getDoctorMyPatients() { return this.request('/doctor/my-patients'); },
    getDoctorPatient(patientUserId) { return this.request(`/doctor/patients/${patientUserId}`); },
    getDoctorPatientMedicalRecords(patientUserId) { return this.request(`/doctor/patients/${patientUserId}/medical-records`); },
    getDoctorPatientAppointments(patientUserId) { return this.request(`/doctor/patients/${patientUserId}/appointments`); },
    async getDoctorNotifications() {
        try {
            const response = await fetch(`${API_BASE}/doctor/notifications`, {
                method: 'GET',
                headers: { 'Content-Type': 'application/json' }
            });
            if (response.status === 404) {
                // Older backend process may not yet include this endpoint.
                return { success: true, items: [] };
            }
            const payload = await response.json();
            if (!response.ok) {
                return { success: false, items: [], message: payload.message || 'Failed to load notifications.' };
            }
            return payload;
        } catch (_) {
            return { success: true, items: [] };
        }
    },
    updateDoctorProfile(data) { return this.request('/doctor/profile', 'PUT', data); },
    getMessageConversations() { return this.request('/messages/conversations'); },
    getMessageThread(peerId) { return this.request(`/messages/thread/${peerId}`); },
    sendMessage(payload) { return this.request('/messages', 'POST', payload); },
    forcePasswordChange(newPassword) { return this.request('/auth/force-password-change', 'POST', { new_password: newPassword }); }
};

// Legacy shim to prevent breaking other scripts immediately (will migrate over time)
const Db = {
    init() { console.log("Backend Initialized: Persistence now handled by SQLite."); },
    async get(key) {
        if (key === 'doctors') return (await API.getDoctors());
        if (key === 'appointments') return (await API.getAppointments());
        return [];
    }
};

Db.init();

// -- 2. Authentication Logic --
const Auth = {
    async login(email, password, role = 'patient') {
        const result = await API.login(email, password, role);
        if (result.success) {
            localStorage.setItem('mediPath_session', JSON.stringify(result.user));
            return { success: true, pending: result.user.status === 'pending_approval' };
        }
        return result; 
    },
    async register(data, role = 'patient') {
        const result = await API.register(data, role);
        return result;
    },
    async logout() {
        await API.logout();
        localStorage.removeItem('mediPath_session');
        const isAdminFolder = window.location.pathname.includes('/admin/');
        window.location.href = isAdminFolder ? 'admin-login.html' : 'index.html';
    },
    getUser() { 
        const s = localStorage.getItem('mediPath_session'); 
        return s ? JSON.parse(s) : null; 
    },
    async refreshSession() {
        const result = await API.getMe();
        if (result.success) {
            localStorage.setItem('mediPath_session', JSON.stringify(result.user));
            return result.user;
        }
        return null;
    },
    requireAuth(role) { 
        const user = this.getUser();
        const path = window.location.pathname;
        const isAdminFolder = path.includes('/admin/');
        
        if (!user) {
            if (role === 'admin' || isAdminFolder) window.location.href = isAdminFolder ? 'admin-login.html' : 'admin/admin-login.html';
            else if (role === 'doctor') window.location.href = isAdminFolder ? '../doctor-login.html' : 'doctor-login.html';
            else window.location.href = isAdminFolder ? '../login.html' : 'login.html';
        } else if (role && user.role !== role) {
            if (user.role === 'admin') window.location.href = isAdminFolder ? 'admin-dashboard.html' : 'admin/admin-dashboard.html';
            else if (user.role === 'doctor') window.location.href = isAdminFolder ? '../doctor-dashboard.html' : 'doctor-dashboard.html';
            else window.location.href = isAdminFolder ? '../dashboard.html' : 'dashboard.html';
        } else if (user && user.role === 'doctor' && user.status === 'pending_approval') {
            const isPendingPage = path.endsWith('doctor-pending.html');
            if (!isPendingPage) window.location.href = isAdminFolder ? '../doctor-pending.html' : 'doctor-pending.html';
        }
    },
    redirectIfGated() {
        const path = window.location.pathname;
        const filename = path.split('/').pop() || 'index.html';
        const user = this.getUser();
        const isAdminFolder = path.includes('/admin/');

        // 1. Guest-only pages (redirect if logged in AS THAT ROLE)
        const guestOnlyPages = ['login.html', 'register.html', 'doctor-login.html', 'doctor-register.html', 'admin-login.html'];
        if (guestOnlyPages.includes(filename) && user) {
            if (user.role === 'admin' && isAdminFolder) {
                window.location.href = 'admin-dashboard.html';
                return;
            }
            if (user.role === 'doctor' && filename.includes('doctor')) {
                if (user.status === 'pending_approval') {
                    window.location.href = isAdminFolder ? '../doctor-pending.html' : 'doctor-pending.html';
                } else {
                    window.location.href = isAdminFolder ? '../doctor-dashboard.html' : 'doctor-dashboard.html';
                }
                return;
            }
            if (user.role === 'patient' && (filename === 'login.html' || filename === 'register.html')) {
                window.location.href = isAdminFolder ? '../dashboard.html' : 'dashboard.html';
                return;
            }
            return;
        }

        // 2. Role-based gated pages
        const patientPages = ['dashboard.html', 'appointments.html', 'messages.html'];
        const doctorPages  = ['doctor-dashboard.html', 'doctor-appointments.html', 'doctor-profile.html', 'doctor-messages.html'];
        
        if (!isAdminFolder) {
            if (patientPages.includes(filename) && (!user || user.role !== 'patient')) {
                window.location.href = 'login.html';
                return;
            }
            if (doctorPages.includes(filename) && (!user || (user.role !== 'doctor' || user.status === 'pending_approval'))) {
                window.location.href = user && user.status === 'pending_approval' ? 'doctor-pending.html' : 'doctor-login.html';
                return;
            }
        } else {
            if (filename !== 'admin-login.html' && (!user || user.role !== 'admin')) {
                window.location.href = 'admin-login.html';
                return;
            }
        }
    }
};

Auth.redirectIfGated();

// -- 3. Navigation UI Logic --
const Nav = {
    init() {
        const user = Auth.getUser();
        const navAuth = document.querySelector('.nav-auth');
        const navMenu = document.querySelector('.nav-menu');
        const isAdminPage = window.location.pathname.includes('/admin/');

        if (isAdminPage) return;

        // 1. Update Auth Buttons
        if (navAuth) {
            if (user) {
                navAuth.innerHTML = `
                    <div class="user-menu" style="display: flex; align-items: center; gap: 1rem;">
                        <span class="user-name" style="font-weight: 700; font-size: 0.9rem; color: var(--primary-color);">
                            ${user.role === 'doctor' ? 'Dr. ' : ''}${user.name.split(' ')[0]}
                        </span>
                        <button onclick="Auth.logout()" class="btn btn-outline btn-sm">Sign Out</button>
                    </div>
                `;
            } else {
                navAuth.innerHTML = `
                    <a href="login.html" class="btn btn-outline btn-sm">Login</a>
                    <a href="register.html" class="btn btn-primary btn-sm">Register</a>
                `;
            }
        }

        // 2. Update Menu Items based on Role
        if (navMenu && user) {
            if (user.role === 'doctor') {
                navMenu.innerHTML = `
                    <li><a href="doctor-dashboard.html" class="nav-item" data-page="doctor-dashboard">Dashboard</a></li>
                    <li><a href="doctor-appointments.html" class="nav-item" data-page="doctor-appointments">Appointments</a></li>
                    <li><a href="doctor-messages.html" class="nav-item" data-page="doctor-messages">Messages</a></li>
                    <li><a href="doctor-profile.html" class="nav-item" data-page="doctor-profile">Profile</a></li>
                `;
            } else {
                navMenu.innerHTML = `
                    <li><a href="dashboard.html" class="nav-item" data-page="dashboard">Dashboard</a></li>
                    <li><a href="doctors.html" class="nav-item" data-page="doctors">Find Doctor</a></li>
                    <li><a href="appointments.html" class="nav-item" data-page="appointments">Appointments</a></li>
                    <li><a href="user/messages.html" class="nav-item" data-page="messages">Messages</a></li>
                    <li><a href="ai-assistant.html" class="nav-item" data-page="ai-assistant">AI Assistant</a></li>
                    <li><a href="emergency.html" class="nav-item emergency-link" data-page="emergency">🚨 Emergency</a></li>
                `;
            }
        }

        this.setActiveLink();
    },
    setActiveLink() {
        const path = window.location.pathname;
        const filename = path.split('/').pop() || 'index.html';
        document.querySelectorAll('.nav-item').forEach(link => {
            const href = link.getAttribute('href');
            if (href === filename) link.classList.add('active');
            else link.classList.remove('active');
        });
    }
};

// ============================================================
// 4. DOMContentLoaded — Initialize All Features
// ============================================================
document.addEventListener('DOMContentLoaded', () => {
    // Initialize Navigation
    Nav.init();

    // ---- B. Active nav link highlight ----
    setActiveNavLink();

    // ---- C. Mobile hamburger toggle ----
    initMobileMenu();

    // ---- D. Navbar scroll effect ----
    initNavbarScroll();

    // ---- E. Dark mode persistence ----
    initDarkMode();

    // ---- F. Fade-in on scroll ----
    initScrollAnimations();

    // ---- G. Page-specific init ----
    const path = window.location.pathname;
    if (path.endsWith('dashboard.html'))   initUserDashboard();
    if (path.endsWith('appointments.html')) initBookingForm();
});

// ============================================================
// 4. Active Nav Link — Highlight Current Page
// ============================================================
function setActiveNavLink() {
    const path     = window.location.pathname;
    const filename = path.split('/').pop() || 'index.html';

    const pageMap = {
        'index.html':        'index',
        '':                  'index',
        'dashboard.html':    'dashboard',
        'doctors.html':      'doctors',
        'appointments.html': 'appointments',
        'contact.html':      'contact',
        'ai-assistant.html': 'ai-assistant',
        'emergency.html':    'emergency',
        'login.html':        'login',
        'register.html':     'register'
    };

    const currentPage = pageMap[filename];

    document.querySelectorAll('.nav-item[data-page]').forEach(item => {
        item.classList.remove('active');
        const page = item.getAttribute('data-page');
        if (currentPage && page === currentPage) {
            item.classList.add('active');
        }
        // Treat dashboard.html as 'home' for logged-in users
        if (currentPage === 'dashboard' && page === 'index') {
            item.classList.add('active');
        }
    });
}

// ============================================================
// 5. Mobile Menu Toggle
// ============================================================
function initMobileMenu() {
    const hamburger = document.getElementById('hamburger');
    const navMenu   = document.getElementById('nav-menu');
    const navAuth   = document.getElementById('nav-auth');

    if (!hamburger) return;

    hamburger.addEventListener('click', () => {
        const isOpen = hamburger.classList.toggle('open');
        hamburger.setAttribute('aria-expanded', isOpen);

        if (navMenu)  navMenu.classList.toggle('mobile-open', isOpen);
        if (navAuth)  navAuth.classList.toggle('mobile-open', isOpen);
    });

    // Close menu when a nav link is clicked
    document.querySelectorAll('.nav-item').forEach(item => {
        item.addEventListener('click', () => {
            hamburger.classList.remove('open');
            hamburger.setAttribute('aria-expanded', 'false');
            if (navMenu) navMenu.classList.remove('mobile-open');
            if (navAuth) navAuth.classList.remove('mobile-open');
        });
    });

    // Close on outside click
    document.addEventListener('click', (e) => {
        const navbar = document.querySelector('.navbar');
        if (navbar && !navbar.contains(e.target)) {
            hamburger.classList.remove('open');
            hamburger.setAttribute('aria-expanded', 'false');
            if (navMenu) navMenu.classList.remove('mobile-open');
            if (navAuth) navAuth.classList.remove('mobile-open');
        }
    });
}

// ============================================================
// 6. Navbar Scroll Effect
// ============================================================
function initNavbarScroll() {
    const navbar = document.querySelector('.navbar');
    if (!navbar) return;

    window.addEventListener('scroll', () => {
        navbar.classList.toggle('scrolled', window.scrollY > 30);
    }, { passive: true });
}

// ============================================================
// 7. Dark Mode
// ============================================================
function initDarkMode() {
    const toggle = document.getElementById('dark-mode-toggle');
    // Restore saved preference
    const saved = localStorage.getItem('mediPath_theme');
    if (saved) {
        document.body.dataset.theme = saved;
        if (toggle) toggle.textContent = saved === 'dark' ? '☀️' : '🌙';
    }

    if (!toggle) return;
    toggle.addEventListener('click', () => {
        const isDark = document.body.dataset.theme === 'dark';
        document.body.dataset.theme = isDark ? 'light' : 'dark';
        toggle.textContent = isDark ? '🌙' : '☀️';
        localStorage.setItem('mediPath_theme', document.body.dataset.theme);
    });
}

// ============================================================
// 8. Scroll Animations (Intersection Observer)
// ============================================================
function initScrollAnimations() {
    const targets = document.querySelectorAll('.fade-in');
    if (!targets.length) return;

    const observer = new IntersectionObserver((entries) => {
        entries.forEach((entry, i) => {
            if (entry.isIntersecting) {
                setTimeout(() => entry.target.classList.add('visible'), i * 80);
                observer.unobserve(entry.target);
            }
        });
    }, { threshold: 0.1, rootMargin: '0px 0px -40px 0px' });

    targets.forEach(t => observer.observe(t));
}

// ============================================================
// 9. Auth Helpers
// ============================================================
function logout()      { Auth.logout(); }
function adminLogout() { window.location.href = 'admin-login.html'; }

// ============================================================
// 10. User Dashboard
// ============================================================
const CLINICAL_DOCTOR_ID_NAMES = {
    1: 'Dr. John Banda',
    2: 'Dr. Mary Phiri',
    3: 'Dr. Peter Mwansa',
    4: 'Dr. Grace Tembo',
    5: 'Dr. Kelvin Zulu',
    6: 'Dr. Ruth Mulenga'
};

function _escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text == null ? '' : String(text);
    return div.innerHTML;
}

/** Next upcoming non-cancelled appointment for reminder banner (clinical + legacy user appts). */
function findNextUpcomingPatientAppointment(clinicalRows, legacyRows) {
    const now = Date.now();
    const candidates = [];

    (clinicalRows || []).forEach((a) => {
        if (!a || !a.appointment_date) return;
        const st = String(a.status || '').toLowerCase();
        if (st === 'cancelled') return;
        const t = new Date(a.appointment_date).getTime();
        if (Number.isNaN(t) || t <= now) return;
        const label = CLINICAL_DOCTOR_ID_NAMES[a.doctor_id] || `Doctor #${a.doctor_id}`;
        candidates.push({ t, label, date: a.appointment_date });
    });

    (legacyRows || []).forEach((a) => {
        if (!a || !a.dateTime) return;
        const st = String(a.status || '').toLowerCase();
        if (st === 'cancelled' || st === 'rejected') return;
        const t = new Date(a.dateTime).getTime();
        if (Number.isNaN(t) || t <= now) return;
        const label = a.doctorName || 'Your doctor';
        candidates.push({ t, label, date: a.dateTime });
    });

    if (!candidates.length) return null;
    candidates.sort((x, y) => x.t - y.t);
    return candidates[0];
}

function formatActivityTime(isoText) {
    const date = new Date(isoText);
    if (Number.isNaN(date.getTime())) return 'Just now';
    const now = new Date();
    const diffMs = now - date;
    const oneDay = 24 * 60 * 60 * 1000;
    if (diffMs < oneDay && now.getDate() === date.getDate()) {
        return `Today, ${date.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })}`;
    }
    const yesterday = new Date(now.getTime() - oneDay);
    if (yesterday.getDate() === date.getDate() && yesterday.getMonth() === date.getMonth() && yesterday.getFullYear() === date.getFullYear()) {
        return `Yesterday, ${date.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })}`;
    }
    return date.toLocaleString('en-US', { dateStyle: 'medium', timeStyle: 'short' });
}

function renderActivityList(items) {
    const host = document.getElementById('activity-list');
    if (!host) return;
    const list = Array.isArray(items) ? items : [];
    if (!list.length) {
        host.innerHTML = `
            <div class="empty-state">
                <span>🕐</span>
                <p>No recent activity in the last 7 days.</p>
            </div>
        `;
        return;
    }
    host.innerHTML = list.map((item) => `
        <div class="activity-item">
            <div class="activity-dot ${item.dot || 'dot-blue'}">${item.icon || '🕐'}</div>
            <div>
                <p class="activity-text">${_escapeHtml(item.text || 'Activity')}</p>
                <p class="activity-time">${_escapeHtml(formatActivityTime(item.timestamp))}</p>
            </div>
        </div>
    `).join('');
}

function initUserDashboard() {
    const user = Auth.getUser();
    if (!user) return;

    const welcomeHeader = document.querySelector('.dashboard-header h2');
    if (welcomeHeader) welcomeHeader.textContent = `Welcome back, ${user.name.split(' ')[0]} 👋`;

    Promise.all([
        API.getClinicalAppointments(),
        API.getAppointments(),
        API.getDashboardStats(),
        API.getNotifications(),
        API.getRecentActivity()
    ]).then(([appts, legacyAppts, statsRes, notes, activities]) => {
        const userAppts = Array.isArray(appts) ? appts : [];
        const legacy = Array.isArray(legacyAppts) ? legacyAppts : [];

        const notifBanner = document.getElementById('notif-banner');
        const notifText = document.getElementById('notif-banner-text');
        if (notifBanner && notifText && user.role === 'patient') {
            const next = findNextUpcomingPatientAppointment(userAppts, legacy);
            if (next) {
                const when = new Date(next.date);
                const whenStr = Number.isNaN(when.getTime())
                    ? next.date
                    : when.toLocaleString('en-US', { dateStyle: 'medium', timeStyle: 'short' });
                notifText.innerHTML =
                    `🔔 <strong>Reminder:</strong> You have an upcoming appointment with ${_escapeHtml(next.label)} — <span id="notif-date">${_escapeHtml(whenStr)}</span>`;
                notifBanner.classList.remove('notif-banner-hidden');
            } else {
                notifText.innerHTML = '';
                notifBanner.classList.add('notif-banner-hidden');
            }
        }

        const upcomingStat = document.getElementById('stat-upcoming');
        if (upcomingStat) upcomingStat.textContent = userAppts.filter(a => a.status !== 'Cancelled').length;

        const tbody = document.querySelector('.table-responsive tbody') ||
                    document.getElementById('user-appointments-tbody');
        if (tbody) {
            if (userAppts.length === 0) {
                tbody.innerHTML = `<tr><td colspan="3" class="text-center text-light">No clinical activity found.</td></tr>`;
            } else {
                tbody.innerHTML = userAppts.map(a => `
                    <tr>
                        <td>${formatDate(a.appointment_date)}</td>
                        <td>Consult w/ Doctor #${a.doctor_id}</td>
                        <td>${getStatusBadge(a.status)}</td>
                    </tr>
                `).join('');
            }
        }

        if (statsRes && statsRes.success && statsRes.stats) {
            const mapping = {
                'stat-total-patients': statsRes.stats.total_patients,
                'stat-total-doctors': statsRes.stats.total_doctors,
                'stat-total-appointments': statsRes.stats.total_appointments,
                'stat-total-emergencies': statsRes.stats.total_emergencies,
                'stat-total-records': statsRes.stats.total_medical_records,
                'dash-total-appts': statsRes.stats.total_appointments
            };
            Object.keys(mapping).forEach((id) => {
                const el = document.getElementById(id);
                if (el) el.textContent = mapping[id];
            });
        }

        const noteList = document.getElementById('notifications-list');
        if (noteList && Array.isArray(notes)) {
            noteList.innerHTML = notes.slice(0, 6).map(n =>
                `<li style="margin-bottom:0.5rem;"><strong>[${n.status}]</strong> ${n.message}</li>`
            ).join('');
        }

        renderActivityList(activities);
    });

    // Keep activity feed fresh while the dashboard is open.
    setInterval(async () => {
        const latest = await API.getRecentActivity();
        renderActivityList(latest);
    }, 30000);
}

// ============================================================
// 11. Booking Form Logic
// ============================================================
function initBookingForm() {
    const user = Auth.getUser();
    const nameInput  = document.getElementById('booking-name');
    const phoneInput = document.getElementById('booking-phone');
    const emailInput = document.getElementById('booking-email');
    const dateInput  = document.getElementById('booking-date');
    const doctorSelect = document.getElementById('booking-doctor');

    // 1. Pre-fill user data if logged in
    if (user) {
        if (nameInput)  { nameInput.value  = user.name || '';  nameInput.readOnly = true; }
        if (phoneInput) { phoneInput.value = user.phone || ''; phoneInput.readOnly = !!user.phone; }
        if (emailInput) { emailInput.value = user.email || ''; emailInput.readOnly = true; }
    }

    // 1b. Attach live phone validation (skip if the field is read-only-prefilled).
    if (phoneInput && !phoneInput.readOnly && window.MediPathPhone) {
        MediPathPhone.attachLiveInput(phoneInput, {
            errorTextEl: document.getElementById('error-phone'),
            errorContainerEl: document.getElementById('error-phone')
        });
    }

    // 2. Prevent past dates
    if (dateInput) {
        const today = new Date().toISOString().split('T')[0];
        dateInput.setAttribute('min', today);
    }

    // 3. Populate doctor dropdown dynamically from backend.
    if (doctorSelect) {
        API.getDoctors().then((doctors) => {
            if (!Array.isArray(doctors) || doctors.length === 0) return;
            const options = [
                `<option value="" disabled selected>Choose a specialist...</option>`
            ];
            doctors.forEach((doc) => {
                const label = `${doc.name || 'Doctor'} — ${doc.specialty || 'General Doctor'}`;
                const bookingId = Number(doc.booking_id || doc.id);
                options.push(`<option value="${bookingId}">${_escapeHtml(label)}</option>`);
            });
            doctorSelect.innerHTML = options.join('');
        });
    }
}

// Booking Form Submission & Validation
let _bookingInFlight = false;
const bookingForm = document.getElementById('booking-form');
if (bookingForm) {
    bookingForm.addEventListener('submit', (e) => {
        e.preventDefault();
        if (_bookingInFlight) return;
        
        // Reset Error Messages
        document.querySelectorAll('.error-msg').forEach(el => el.textContent = '');

        const name   = document.getElementById('booking-name').value.trim();
        const phone  = document.getElementById('booking-phone').value.trim();
        const email  = document.getElementById('booking-email').value.trim();
        const doctor = document.getElementById('booking-doctor').value;
        const date   = document.getElementById('booking-date').value;
        const time   = document.getElementById('booking-time').value;
        const symp   = document.getElementById('symptoms').value;

        let isValid = true;

        // Validation Rules
        if (!name) {
            document.getElementById('error-name').textContent = 'Please enter your name';
            isValid = false;
        }

        const phoneError = MediPathPhone.validate(phone);
        if (phoneError) {
            document.getElementById('error-phone').textContent = phoneError;
            isValid = false;
        }

        if (!email || !email.includes('@')) {
            document.getElementById('error-email').textContent = 'Enter a valid email address';
            isValid = false;
        }

        if (!doctor) {
            document.getElementById('error-doctor').textContent = 'Please select a doctor';
            isValid = false;
        }

        if (!date) {
            document.getElementById('error-date').textContent = 'Please select a date';
            isValid = false;
        }

        if (!time) {
            document.getElementById('error-time').textContent = 'Please select a time';
            isValid = false;
        }

        if (!isValid) return;

        if (!MediPathPhone.regex.test(MediPathPhone.normalize(phone))) {
            document.getElementById('error-phone').textContent = MediPathPhone.invalidMessage;
            return;
        }
        if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
            document.getElementById('error-email').textContent = 'Invalid email address';
            return;
        }
        if (new Date(`${date}T00:00:00`) < new Date(new Date().toDateString())) {
            document.getElementById('error-date').textContent = 'Date must be valid';
            return;
        }

        // Success Flow
        const user = Auth.getUser();
        const doctorSelectEl = document.getElementById('booking-doctor');
        const selectedDoctorLabel = doctorSelectEl.options[doctorSelectEl.selectedIndex]?.textContent || 'Selected doctor';
        const doctorId = Number(doctor);
        if (!Number.isInteger(doctorId) || doctorId <= 0) {
            showToast('Please select a valid doctor', 'error');
            return;
        }
        const appointmentDate = new Date(`${date} ${time}`).toISOString();
        const submitBtn = document.getElementById('submit-booking');
        const submitLabel = submitBtn ? submitBtn.textContent : '';
        _bookingInFlight = true;
        if (submitBtn) {
            submitBtn.disabled = true;
            submitBtn.textContent = 'Booking…';
        }
        API.createClinicalAppointment({
            doctor_id: doctorId,
            appointment_date: appointmentDate,
            notes: symp
        }).then((result) => {
            if (!result || result.success === false) {
                showToast(result?.message || 'Failed to book appointment', 'error');
                _bookingInFlight = false;
                if (submitBtn) {
                    submitBtn.disabled = false;
                    submitBtn.textContent = submitLabel;
                }
                return;
            }

            // Show Confirmation Box
            const overlay = document.getElementById('confirmation-overlay');
            if (overlay) {
                document.getElementById('confirm-doctor').textContent = selectedDoctorLabel;
                document.getElementById('confirm-date').textContent   = date;
                document.getElementById('confirm-time').textContent   = time;
                overlay.style.display = 'flex';
                bookingForm.reset();
                if (user) initBookingForm();
                setTimeout(() => {
                    window.location.href = 'dashboard.html';
                }, 4000);
            } else {
                showToast('Appointment booked successfully!', 'success');
                setTimeout(() => window.location.href = 'dashboard.html', 1500);
            }
        }).catch(() => {
            showToast('Failed to book appointment', 'error');
            _bookingInFlight = false;
            if (submitBtn) {
                submitBtn.disabled = false;
                submitBtn.textContent = submitLabel;
            }
        });
    });
}

// ============================================================
// 14. Doctor Search
// ============================================================
const doctorSearch = document.getElementById('doctor-search');
const docCards     = document.querySelectorAll('.doctor-card');

if (doctorSearch && docCards.length) {
    doctorSearch.addEventListener('input', (e) => {
        const term = e.target.value.toLowerCase().trim();
        docCards.forEach(card => {
            const name = card.querySelector('h3')?.textContent.toLowerCase() || '';
            const spec = card.querySelector('.specialty')?.textContent.toLowerCase() || '';
            card.style.display = (!term || name.includes(term) || spec.includes(term)) ? '' : 'none';
        });
    });
}

// ============================================================
// 15. Toast Notification
// ============================================================
function showToast(message, type = 'info') {
    // Remove any existing toast
    const existing = document.getElementById('mp-toast');
    if (existing) existing.remove();

    const toast = document.createElement('div');
    toast.id = 'mp-toast';
    const bg = type === 'success' ? '#10b981' : type === 'error' ? '#ef4444' : '#2563eb';

    toast.style.cssText = `
        position: fixed; bottom: 2rem; right: 2rem; z-index: 9999;
        background: ${bg}; color: white;
        padding: 1rem 1.5rem; border-radius: 12px;
        font-family: 'Poppins', sans-serif; font-weight: 600; font-size: 0.9rem;
        box-shadow: 0 10px 30px rgba(0,0,0,0.2);
        max-width: 340px; line-height: 1.4;
        animation: slideInToast 0.35s ease;
    `;

    const style = document.createElement('style');
    style.textContent = `
        @keyframes slideInToast {
            from { opacity:0; transform:translateY(20px); }
            to   { opacity:1; transform:translateY(0); }
        }
    `;
    document.head.appendChild(style);
    toast.textContent = message;
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 3500);
}

// ============================================================
// 16. Utilities
// ============================================================
function formatDate(dateTimeStr) {
    if (!dateTimeStr) return 'N/A';
    const d = new Date(dateTimeStr);
    return isNaN(d) ? dateTimeStr : d.toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' });
}

function getStatusBadge(status) {
    const s = (status || '').toLowerCase();
    switch (s) {
        case 'approved':
        case 'confirmed':
            return '<span class="badge badge-approved" style="background:#10b98120; color:#10b981; border:1px solid #10b98140;">Confirmed</span>';
        case 'pending':
        case 'pending approval': return '<span class="badge badge-pending" style="background:#f59e0b20; color:#f59e0b; border:1px solid #f59e0b40;">Pending</span>';
        case 'cancelled':
        case 'rejected':  return '<span class="badge badge-cancelled" style="background:#ef444420; color:#ef4444; border:1px solid #ef444440;">Cancelled</span>';
        case 'completed': return '<span class="badge" style="background:#6366f120; color:#6366f1; border:1px solid #6366f140;">Completed</span>';
        default:          return `<span class="badge">${status}</span>`;
    }
}
