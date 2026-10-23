let currentUserId = localStorage.getItem('career_bot_user_id') || null;
        let currentSessionId = localStorage.getItem('career_bot_session_id') || null;
        let currentUserData = null;
        let googleClientId = "";
        let googleIdentityInitialized = false;
        let pendingAuthAction = null;

        window.addEventListener('DOMContentLoaded', async () => {
            await initializeAuth();
            if (currentUserId) {
                await loadUserProfile();
            }
            await loadSessions();
            if (currentSessionId) {
                await loadSessionMessages(currentSessionId);
            }
        });

        /* ===== GOOGLE & CANDIDATE AUTHENTICATION ===== */
        async function initializeAuth() {
            try {
                const res = await fetch('/auth/config');
                if (res.ok) {
                    const data = await res.json();
                    googleClientId = data.google_client_id || "";

                    if (googleClientId) waitForGoogleIdentity();
                }
            } catch (err) {
                console.warn('Auth config init note:', err);
            }

            // Restore stored user profile visual state if present
            const storedName = localStorage.getItem('career_bot_user_name');
            const storedEmail = localStorage.getItem('career_bot_user_email');
            const storedPic = localStorage.getItem('career_bot_user_pic');

            if (currentUserId && (storedName || storedEmail)) {
                renderUserAccountBadge({
                    id: currentUserId,
                    name: storedName || 'Candidate',
                    email: storedEmail || '',
                    picture_url: storedPic || ''
                });
            }
        }

        function waitForGoogleIdentity(attempts = 20) {
            if (googleClientId && window.google && google.accounts && google.accounts.id) {
                setupGoogleIdentity(googleClientId);
            } else if (attempts > 0) {
                window.setTimeout(() => waitForGoogleIdentity(attempts - 1), 250);
            }
        }
        function setupGoogleIdentity(clientId) {
            googleClientId = clientId;
            if (!window.google || !google.accounts || !google.accounts.id) return;
            try {
                if (!googleIdentityInitialized) {
                    google.accounts.id.initialize({ client_id: googleClientId, callback: handleGoogleCredentialResponse, auto_select: false });
                    googleIdentityInitialized = true;
                }
                renderGoogleLoginButton();
            } catch (e) { console.warn('Google setup error:', e); }
        }

        function renderGoogleLoginButton() {
            const slot = document.getElementById('modal_google_btn_slot');
            if (!slot || !googleIdentityInitialized) return;
            slot.innerHTML = '';
            google.accounts.id.renderButton(slot, { theme: 'filled_blue', size: 'large', text: 'continue_with', shape: 'pill', width: 320 });
        }

        function requireAuthentication(continuation) {
            if (currentUserId) return true;
            pendingAuthAction = continuation;
            openAuthModal();
            return false;
        }

        function runPendingAuthAction() {
            const continuation = pendingAuthAction;
            pendingAuthAction = null;
            if (typeof continuation === 'function') window.setTimeout(continuation, 0);
        }

        async function handleGoogleCredentialResponse(response) {
            if (!response || !response.credential) return;

            try {
                let clientDecoded = {};
                try {
                    const base64Url = response.credential.split('.')[1];
                    const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
                    clientDecoded = JSON.parse(decodeURIComponent(atob(base64).split('').map(c => {
                        return '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2);
                    }).join('')));
                } catch (e) {
                    console.warn('Local JWT parse note:', e);
                }

                const res = await fetch('/auth/google', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        credential: response.credential,
                        email: clientDecoded.email || null,
                        name: clientDecoded.name || null,
                        google_id: clientDecoded.sub || null,
                        picture: clientDecoded.picture || null
                    })
                });

                if (!res.ok) {
                    throw new Error('Failed to authenticate with Google.');
                }

                const user = await res.json();
                onUserAuthenticated(user, true);
                closeAuthModal();
            } catch (err) {
                console.error('Google Sign-in error:', err);
                alert('Authentication failed: ' + err.message);
            }
        }

        function onUserAuthenticated(user, checkFirstTime = false) {
            currentUserId = user.id;
            currentUserData = user;

            localStorage.setItem('career_bot_user_id', user.id);
            if (user.name) localStorage.setItem('career_bot_user_name', user.name);
            if (user.email) localStorage.setItem('career_bot_user_email', user.email);
            if (user.picture_url) localStorage.setItem('career_bot_user_pic', user.picture_url);

            renderUserAccountBadge(user);
            refreshRaceResultCard();
            populateProfileForm(user);
            loadSessions();

            // Reveal the sidebar profile card
            const sidebarBadge = document.getElementById('sidebar_profile_badge');
            if (sidebarBadge) {
                sidebarBadge.style.display = 'block';
                document.getElementById('sidebar_profile_name').textContent = user.name || user.email || 'Candidate';
            }

            if (pendingAuthAction) {
                runPendingAuthAction();
            } else if (checkFirstTime && (!user.education || !user.skills)) {
                openProfileModal();
            }
        }

        function renderUserAccountBadge(user) {
            document.getElementById('btn_login_trigger').style.display = 'none';
            const googleBtn = document.getElementById('google_btn_container');
            if (googleBtn) googleBtn.style.display = 'none';

            const badge = document.getElementById('user_account_badge');
            if (badge) badge.style.display = 'inline-flex';

            const userDisplayName = document.getElementById('user_display_name');
            if (userDisplayName) userDisplayName.textContent = user.name || 'Candidate';
            const userDisplayEmail = document.getElementById('user_display_email');
            if (userDisplayEmail) userDisplayEmail.textContent = user.email || 'Verified Profile';

            const avatarImg = document.getElementById('user_avatar_img');
            const avatarInitials = document.getElementById('user_avatar_initials');

            const nameParts = (user.name || '').trim().split(/\s+/).filter(Boolean);
            let initials = 'U';
            if (nameParts.length >= 2) {
                initials = (nameParts[0][0] + nameParts[nameParts.length - 1][0]).toUpperCase();
            } else if (nameParts.length === 1) {
                initials = nameParts[0].slice(0, 2).toUpperCase();
            } else if (user.email) {
                initials = user.email.slice(0, 2).toUpperCase();
            }

            if (avatarImg && avatarInitials) {
                if (user.picture_url) {
                    avatarImg.src = user.picture_url;
                    avatarImg.style.display = 'block';
                    avatarInitials.style.display = 'none';
                } else {
                    avatarImg.style.display = 'none';
                    avatarInitials.style.display = 'flex';
                    avatarInitials.textContent = initials;
                }
            }

            const sidebarBadge = document.getElementById('sidebar_profile_badge');
            if (sidebarBadge) {
                sidebarBadge.style.display = 'flex';
                const sidebarName = document.getElementById('sidebar_profile_name');
                if (sidebarName) sidebarName.textContent = user.name || user.email || 'Candidate';
                const sidebarInitials = document.getElementById('sidebar_user_initials');
                if (sidebarInitials) sidebarInitials.textContent = initials;
            }

            // Sync Advisor Context right panel
            const ctxName = document.getElementById('ctx_user_name');
            if (ctxName) ctxName.textContent = user.name || user.email || '[Not set]';
            if (user.current_role) {
                const ctxRole = document.getElementById('ctx_target_domain');
                if (ctxRole) ctxRole.textContent = user.current_role;
            }
            if (user.years_of_experience) {
                const ctxExp = document.getElementById('ctx_experience');
                if (ctxExp) ctxExp.textContent = user.years_of_experience;
            }
            if (user.skills) {
                const ctxSkills = document.getElementById('ctx_skills');
                if (ctxSkills) ctxSkills.textContent = user.skills;
            }
        }

        function signOutUser() {
            currentUserId = null;
            currentUserData = null;
            localStorage.removeItem('career_bot_user_id');
            localStorage.removeItem('career_bot_user_name');
            localStorage.removeItem('career_bot_user_email');
            localStorage.removeItem('career_bot_user_pic');
            localStorage.removeItem('career_bot_session_id');

            const sidebarName = document.getElementById('sidebar_profile_name');
            if (sidebarName) sidebarName.textContent = 'Candidate';
            const sidebarInitials = document.getElementById('sidebar_user_initials');
            if (sidebarInitials) sidebarInitials.textContent = 'CA';

            const ctxName = document.getElementById('ctx_user_name');
            if (ctxName) ctxName.textContent = '[Not set]';
            const ctxRole = document.getElementById('ctx_target_domain');
            if (ctxRole) ctxRole.textContent = '[Not set]';
            const ctxExp = document.getElementById('ctx_experience');
            if (ctxExp) ctxExp.textContent = '[Not set]';
            const ctxSkills = document.getElementById('ctx_skills');
            if (ctxSkills) ctxSkills.textContent = '[Not set]';

            // Restore the branded login entry point.
            document.getElementById('btn_login_trigger').style.display = 'inline-flex';
            document.getElementById('user_account_badge').style.display = 'none';

            // Clear inputs
            document.getElementById('prof_name').value = '';
            document.getElementById('prof_email').value = '';
            document.getElementById('prof_education').value = '';
            document.getElementById('prof_role').value = '';
            document.getElementById('prof_experience').value = '';
            document.getElementById('prof_skills').value = '';

            startNewSession();
        }

        function openAuthModal() {
            document.getElementById('auth_modal_overlay').classList.add('open');
            if (googleClientId) waitForGoogleIdentity();
        }

        function closeAuthModal() {
            document.getElementById('auth_modal_overlay').classList.remove('open');
        }

        /* ===== PROFILE MODAL ===== */
        function openProfileModal() {
            document.getElementById('profile_modal_overlay').classList.add('open');
        }

        function closeProfileModal() {
            document.getElementById('profile_modal_overlay').classList.remove('open');
        }

        async function saveCandidateProfile() {
            const payload = {
                name: document.getElementById('prof_name').value.trim(),
                email: document.getElementById('prof_email').value.trim(),
                education: document.getElementById('prof_education').value.trim(),
                current_role: document.getElementById('prof_role').value.trim(),
                years_of_experience: document.getElementById('prof_experience').value.trim(),
                skills: document.getElementById('prof_skills').value.trim()
            };

            try {
                const url = currentUserId ? `/profile/${currentUserId}` : '/profile';
                const method = currentUserId ? 'PUT' : 'POST';
                const res = await fetch(url, {
                    method,
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });

                if (res.ok) {
                    const data = await res.json();
                    currentUserId = data.id;
                    localStorage.setItem('career_bot_user_id', currentUserId);
                    if (data.name) localStorage.setItem('career_bot_user_name', data.name);
                    if (data.email) localStorage.setItem('career_bot_user_email', data.email);

                    renderUserAccountBadge(data);
                    closeProfileModal();
                }
            } catch (err) {
                console.error('Error saving profile:', err);
            }
        }

        async function loadUserProfile() {
            try {
                const res = await fetch(`/profile/${currentUserId}`);
                if (res.ok) {
                    const p = await res.json();
                    populateProfileForm(p);
                }
            } catch (err) {
                console.error('Error loading profile:', err);
            }
        }

        function populateProfileForm(p) {
            if (!p) return;
            document.getElementById('prof_name').value = p.name || '';
            document.getElementById('prof_email').value = p.email || '';
            document.getElementById('prof_education').value = p.education || '';
            document.getElementById('prof_role').value = p.current_role || '';
            document.getElementById('prof_experience').value = p.years_of_experience || '';
            document.getElementById('prof_skills').value = p.skills || '';

            const sidebarName = document.getElementById('sidebar_profile_name');
            if (sidebarName) sidebarName.textContent = p.name || p.email || 'Candidate';

            const nameParts = (p.name || '').trim().split(/\s+/).filter(Boolean);
            let initials = 'U';
            if (nameParts.length >= 2) {
                initials = (nameParts[0][0] + nameParts[nameParts.length - 1][0]).toUpperCase();
            } else if (nameParts.length === 1) {
                initials = nameParts[0].slice(0, 2).toUpperCase();
            } else if (p.email) {
                initials = p.email.slice(0, 2).toUpperCase();
            }
            const sidebarInitials = document.getElementById('sidebar_user_initials');
            if (sidebarInitials) sidebarInitials.textContent = initials;

            const ctxName = document.getElementById('ctx_user_name');
            if (ctxName) ctxName.textContent = p.name || p.email || '[Not set]';
            const ctxRole = document.getElementById('ctx_target_domain');
            if (ctxRole) ctxRole.textContent = p.current_role || '[Not set]';
            const ctxExp = document.getElementById('ctx_experience');
            if (ctxExp) ctxExp.textContent = p.years_of_experience || '[Not set]';
            const ctxSkills = document.getElementById('ctx_skills');
            if (ctxSkills) ctxSkills.textContent = p.skills || '[Not set]';
        }

        /* ===== SESSIONS ===== */
        async function loadSessions() {
            try {
                const url = currentUserId ? `/sessions?user_id=${currentUserId}` : '/sessions';
                const res = await fetch(url);
                if (!res.ok) return;
                const sessions = await res.json();
                const container = document.getElementById('session_list_container');

                if (!sessions.length) {
                    container.innerHTML = '<div class="session-empty-text">Your past consultations will appear here.</div>';
                    return;
                }

                container.innerHTML = sessions.map(s => `
                    <div class="session-card ${s.id === currentSessionId ? 'active' : ''}"
                         onclick="selectSession('${s.id}')"
                         title="${escapeHtml(s.title || 'Consultation')}">
                        ${escapeHtml(s.title || 'Consultation')}
                    </div>
                `).join('');
            } catch (err) {
                console.error('Error loading sessions:', err);
            }
        }

        async function selectSession(sessionId) {
            currentSessionId = sessionId;
            localStorage.setItem('career_bot_session_id', sessionId);
            await loadSessionMessages(sessionId);
            await loadSessions();
        }

        function startNewSession() {
            currentSessionId = null;
            localStorage.removeItem('career_bot_session_id');
            const stream = document.getElementById('messages_stream');
            if (stream) {
                stream.innerHTML = '';
            }
            if (typeof updateConversationVisibility === 'function') {
                updateConversationVisibility();
            }
            loadSessions();
        }

        async function loadSessionMessages(sessionId) {
            try {
                const res = await fetch(`/sessions/${sessionId}/messages`);
                if (!res.ok) return;
                const messages = await res.json();
                if (!messages.length) { startNewSession(); return; }

                const stream = document.getElementById('messages_stream');
                stream.innerHTML = '';

                messages.forEach(m => {
                    if (m.role === 'user') {
                        renderUserMessage(m.content);
                    } else {
                        renderAssistantMessage(m.content, {
                            interests: m.extracted_interests,
                            career_category: m.career_category,
                            explanation: m.explanation,
                            job_titles: m.job_titles,
                            open_jobs: m.open_jobs
                        });
                    }
                });
                scrollStreamToBottom();
            } catch (err) {
                console.error('Error loading session messages:', err);
            }
        }






        function refreshRaceResultCard() {
            const date = document.getElementById('race_result_date');
            if (!date) return;
            const formattedDate = new Intl.DateTimeFormat('en-IN', { day: 'numeric', month: 'short', year: 'numeric' }).format(new Date());
            date.textContent = `Contest date: ${formattedDate}`;
            const heroDate = document.getElementById('race_contest_date');
            if (heroDate) heroDate.textContent = formattedDate;
        }

        async function loadRaceStatus() {
            try {
                const response = await fetch('/race/status');
                if (!response.ok) return;
                const race = await response.json();
                const label = document.getElementById('race_seat_status');
                if (label) label.textContent = `${race.seats_left}/${race.capacity} seats available`;
                const button = document.getElementById('race_checkout_button');
                if (button && race.seats_left === 0) { button.disabled = true; button.textContent = 'Today\'s Race Is Full'; }
            } catch (error) {
                console.error('Unable to load AI Race status:', error);
            }
        }

        async function shareRaceInvite() {
            const inviteUrl = `${window.location.origin}/#ai_race`;
            const message = 'Join me in today\'s AI Race - only 20 seats. Rank #1 takes it all!';
            try {
                if (navigator.share) await navigator.share({ title: 'AI Race', text: message, url: inviteUrl });
                else { await navigator.clipboard.writeText(inviteUrl); alert('Invite link copied to clipboard.'); }
            } catch (error) {
                if (error.name !== 'AbortError') console.error('Unable to share AI Race invite:', error);
            }
        }

        async function startRaceCheckout() {
            if (!requireAuthentication(startRaceCheckout)) return;
            const status = document.getElementById('race_payment_status');
            const button = document.getElementById('race_checkout_button');
            button.disabled = true;
            status.textContent = 'Preparing secure UPI checkout...';
            try {
                const response = await fetch('/race/orders', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ user_id: currentUserId || null }) });
                const order = await response.json();
                if (!response.ok) throw new Error(order.detail || 'Unable to start payment.');
                if (!window.Razorpay) throw new Error('Razorpay Checkout did not load.');
                const checkout = new Razorpay({
                    key: order.key_id, amount: order.amount, currency: order.currency, name: 'HireKrkeDekho AI Race', description: 'Daily AI Race entry', order_id: order.order_id,
                    theme: { color: '#6366f1' }, method: { upi: true },
                    handler: async payment => {
                        const verify = await fetch('/race/verify', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ entry_id: order.entry_id, ...payment }) });
                        const result = await verify.json();
                        if (!verify.ok) throw new Error(result.detail || 'Payment verification failed.');
                        status.textContent = 'Entry confirmed. You are in today\'s AI Race!';
                        loadRaceStatus();
        refreshRaceResultCard();
                    },
                    modal: { ondismiss: async () => { await fetch('/race/cancel', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ entry_id: order.entry_id }) }); button.disabled = false; status.textContent = 'Payment cancelled. Your seat was released.'; loadRaceStatus(); } }
                });
                checkout.open();
            } catch (error) {
                status.textContent = error.message;
                button.disabled = false;
            }
        }
        function openRaceModal() {
            if (!requireAuthentication(openRaceModal)) return;
            document.getElementById('race_modal_overlay').classList.add('open');
        }

        function closeRaceModal() {
            document.getElementById('race_modal_overlay').classList.remove('open');
        }
        function openPremiumModal() {
            if (!requireAuthentication(openPremiumModal)) return;
            document.getElementById('premium_modal_overlay').classList.add('open');
        }

        function closePremiumModal() {
            document.getElementById('premium_modal_overlay').classList.remove('open');
        }
        function openConsultation() {
            if (!requireAuthentication(openConsultation)) return;
            if (window.location.pathname !== '/consultation') {
                window.location.assign('/consultation');
                return;
            }
            document.body.classList.add('consultation-active');
            const shell = document.querySelector('.consultation-shell');
            if (shell) shell.setAttribute('aria-hidden', 'false');
            document.getElementById('user_input_field')?.focus();
        }

        function closeConsultation() {
            loadRaceStatus();
        refreshRaceResultCard();
        if (window.location.pathname === '/consultation') {
                window.location.assign('/');
                return;
            }
            document.body.classList.remove('consultation-active');
            const shell = document.querySelector('.consultation-shell');
            if (shell) shell.setAttribute('aria-hidden', 'true');
        }

        function openRoadmapModal(title, guide) {
            document.getElementById('roadmap_modal_title').textContent = 'Free 3-Week Roadmap';
            document.getElementById('roadmap_modal_subtitle').textContent = title;
            const list = document.getElementById('roadmap_modal_list');
            list.innerHTML = guide.map((item, index) => {
                const bullets = String(item).split(/\s*[,;]\s*/).filter(Boolean);
                return `<li><span class="roadmap-week">Week ${index + 1}</span><ul>${bullets.map(bullet => `<li>${escapeHtml(bullet)}</li>`).join('')}</ul></li>`;
            }).join('');
            document.getElementById('roadmap_modal_overlay').classList.add('open');
        }

        function closeRoadmapModal() {
            document.getElementById('roadmap_modal_overlay').classList.remove('open');
        }
        /* ===== CHAT DISPATCH ===== */
        function submitHeroPrompt() {
            const input = document.getElementById('hero_prompt_input');
            const val = input ? input.value.trim() : '';
            if (!val) return;
            input.value = '';
            sendQuickPrompt(val);
        }

        function sendQuickPrompt(promptText) {
            document.getElementById('user_input_field').value = promptText;
            submitMessage();
            const target = document.getElementById('app_workspace');
            if (target) target.scrollIntoView({ behavior: 'smooth' });
        }

        async function submitMessage() {
            if (!requireAuthentication(submitMessage)) return;
            const inputEl = document.getElementById('user_input_field');
            const text = inputEl.value.trim();
            if (!text) return;

            inputEl.value = '';
            renderUserMessage(text);
            scrollStreamToBottom();

            const loadingId = renderLoadingCard();
            scrollStreamToBottom();

            const sendBtn = document.getElementById('btn_send_action');
            sendBtn.disabled = true;

            try {
                const res = await fetch('/chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        user_input: text,
                        session_id: currentSessionId,
                        user_id: currentUserId
                    })
                });

                removeLoadingCard(loadingId);

                if (!res.ok) {
                    const err = await res.json().catch(() => ({}));
                    throw new Error(err.detail || `Server returned error ${res.status}`);
                }

                const data = await res.json();
                currentSessionId = data.session_id;
                localStorage.setItem('career_bot_session_id', currentSessionId);

                renderAssistantMessage(data.message, data);
                scrollStreamToBottom();
                loadSessions();
            } catch (err) {
                removeLoadingCard(loadingId);
                const isDailyLimit = err.message.includes('Daily limit reached') || err.message.includes('3 free AI consultations') || err.message.includes('Daily AI capacity');
                const errMsg = isDailyLimit ? 'Daily limit reached. Come back tomorrow for new openings.' : 'An error occurred during talent assessment: ' + err.message + '. Please retry.';
                renderAssistantMessage(errMsg, { daily_limit_reached: true });
                scrollStreamToBottom();
            } finally {
                sendBtn.disabled = false;
                document.getElementById('user_input_field').focus();
            }
        }

        function updateConversationVisibility() {
            const stream = document.getElementById('messages_stream');
            const hero = document.getElementById('center_empty_hero');
            if (!hero || !stream) return;
            const hasMessages = stream.children.length > 0;
            if (hasMessages) {
                hero.classList.add('hero-hidden');
            } else {
                hero.classList.remove('hero-hidden');
            }
        }

        /* ===== MESSAGE RENDERERS ===== */
        function renderUserMessage(text) {
            const stream = document.getElementById('messages_stream');
            const row = document.createElement('div');
            row.className = 'message-row user';
            row.innerHTML = `
                <div class="msg-bubble-user">${escapeHtml(text)}</div>
            `;
            stream.appendChild(row);
            updateConversationVisibility();
        }

        function renderAssistantMessage(message, extra = {}) {
            const stream = document.getElementById('messages_stream');
            const row = document.createElement('div');
            row.className = 'message-row assistant';

            const hasInterests = Array.isArray(extra.interests) && extra.interests.length > 0;
            const hasOpenJobs = Array.isArray(extra.open_jobs) && extra.open_jobs.length > 0;
            const hasLegacyJobs = Array.isArray(extra.job_titles) && extra.job_titles.length > 0;

            let insightsHtml = '';

            let jobsHtml = '';
            if (hasOpenJobs) {
                const cardsHtml = extra.open_jobs.map(job => {
                    const skillsPills = Array.isArray(job.skills_required)
                        ? job.skills_required.map(s => `<span class="job-skill-chip">${escapeHtml(s)}</span>`).join('')
                        : '';

                    const applyUrl = job.apply_url || `https://www.linkedin.com/jobs/search/?keywords=${encodeURIComponent(job.title)}&location=India&f_TPR=r604800`;

                    return `
                        <div class="job-card">
                            <div>
                                <div class="job-card-top">
                                    <div class="job-role-title">${escapeHtml(job.title)}</div>
                                </div>
                                <div class="job-company-meta">
                                    <span class="meta-item">
                                        India &middot; ${escapeHtml(job.job_type || 'Hybrid')}
                                    </span>
                                </div>
                                ${job.salary_range ? `
                                    <div class="job-salary-tag">
                                        <span class="currency-symbol">&#8377;</span>
                                        <span>${escapeHtml(job.salary_range.replace(/^\$+\s*/, ''))}</span>
                                    </div>
                                ` : ''}
                                ${job.description ? `<div class="job-desc-snippet">${escapeHtml(job.description)}</div>` : ''}
                                ${skillsPills ? `<div class="job-skills-list">${skillsPills}</div>` : ''}
                            </div>
                            <div class="job-card-actions">
                                <button type="button" class="btn-apply-job btn-roadmap" data-title="${escapeHtml(job.title)}" data-guide="${escapeHtml(JSON.stringify(job.prep_guide || []))}" onclick="openRoadmapModal(this.dataset.title, JSON.parse(this.dataset.guide))">Free 3-Week Roadmap</button>
                                <a href="${escapeHtml(applyUrl)}" target="_blank" rel="noopener noreferrer" class="btn-apply-job">
                                    <span>View on LinkedIn</span>
                                    <svg class="icon icon-sm" viewBox="0 0 24 24"><path d="M19 19H5V5h7V3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2-2v-7h-2v7zM14 3v2h3.59l-9.83 9.83 1.41 1.41L19 6.41V10h2V3h-7z"/></svg>
                                </a>
                            </div>
                        </div>
                    `;
                }).join('');

                let actionFooterHtml = '';
                if (extra.daily_limit_reached || extra.remaining_requests === 0) {
                    actionFooterHtml = `<div class="daily-limit-banner">Oops! Daily limit reached. Come back tomorrow for new openings.</div>`;
                } else {
                    actionFooterHtml = `<button type="button" class="btn-show-more-jobs" onclick="sendQuickPrompt('Show more matching roles that are different from the previous recommendations.')">Show more openings (+2)</button>`;
                }

                jobsHtml = `
                    <div class="open-jobs-section">
                        <div class="jobs-section-heading">
                            Curated Open Positions &amp; Roles
                        </div>
                        <div class="job-cards-grid">
                            ${cardsHtml}
                        </div>
                        ${actionFooterHtml}
                    </div>
                `;
            } else if (hasLegacyJobs) {
                const listItems = extra.job_titles.map(title => `
                    <div class="job-card" style="padding:10px 14px;">
                        <div style="font-weight:600; color:#fff; font-size:0.86rem; margin-bottom:6px;">${escapeHtml(title)}</div>
                        <a href="https://www.linkedin.com/jobs/search/?keywords=${encodeURIComponent(title)}&location=India&f_TPR=r604800" target="_blank" rel="noopener noreferrer" class="btn-apply-job">
                            <span>View Openings</span>
                            <svg class="icon icon-sm" viewBox="0 0 24 24"><path d="M19 19H5V5h7V3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7h-2v7zM14 3v2h3.59l-9.83 9.83 1.41 1.41L19 6.41V10h2V3h-7z"/></svg>
                        </a>
                    </div>
                `).join('');

                jobsHtml = `
                    <div class="open-jobs-section">
                        <div class="jobs-section-heading">Recommended Role Opportunities</div>
                        <div class="job-cards-grid">${listItems}</div>
                    </div>
                `;
            }

                const isLimitText = message.includes('Daily limit reached');
                row.innerHTML = `
                    <div class="msg-sender-icon hk-bot-avatar">
                        <img src="/static/bot-logo.png" alt="HK" class="bot-logo-img">
                    </div>
                    <div class="msg-body-wrapper">
                        <div class="msg-card-assistant">
                            <div class="msg-text-main ${isLimitText ? 'daily-limit-text' : ''}">${escapeHtml(message)}</div>
                            ${insightsHtml}
                            ${jobsHtml}
                        </div>
                    </div>
                `;

            stream.appendChild(row);
            updateConversationVisibility();
        }

        function renderLoadingCard() {
            const stream = document.getElementById('messages_stream');
            const id = 'loader_' + Date.now();
            const row = document.createElement('div');
            row.id = id;
            row.className = 'message-row assistant';
            row.innerHTML = `
                <div class="msg-sender-icon hk-bot-avatar">
                    <img src="/static/bot-logo.png" alt="HK" class="bot-logo-img">
                </div>
                <div class="msg-body-wrapper">
                    <div class="msg-card-assistant" style="padding:14px 18px;">
                        <div class="typing-loader"><span></span><span></span><span></span></div>
                    </div>
                </div>
            `;
            stream.appendChild(row);
            updateConversationVisibility();
            return id;
        }

        function removeLoadingCard(id) {
            const el = document.getElementById(id);
            if (el) el.remove();
            updateConversationVisibility();
        }

        function scrollStreamToBottom() {
            const scrollWrap = document.getElementById('center_scroll_wrapper');
            if (scrollWrap) {
                scrollWrap.scrollTop = scrollWrap.scrollHeight;
            }
            const stream = document.getElementById('messages_stream');
            if (stream) {
                stream.scrollTop = stream.scrollHeight;
            }
        }

        function toggleMobileSidebar() {
            const rail = document.getElementById('consultation_left_rail');
            const backdrop = document.getElementById('sidebar_backdrop_overlay');
            if (rail) {
                const isOpen = rail.classList.toggle('mobile-open');
                if (backdrop) {
                    backdrop.classList.toggle('active', isOpen);
                }
            }
        }

        function toggleMobileContextPanel() {
            const panel = document.getElementById('consultation_right_panel');
            const backdrop = document.getElementById('context_backdrop_overlay');
            if (panel) {
                const isOpen = panel.classList.toggle('mobile-open');
                if (backdrop) {
                    backdrop.classList.toggle('active', isOpen);
                }
            }
        }

        function toggleSiteMobileNav() {
            const nav = document.getElementById('site_nav_links');
            const overlay = document.getElementById('site_nav_drawer_overlay');
            const btn = document.getElementById('site_mobile_menu_btn');
            if (nav) {
                const isOpen = nav.classList.toggle('mobile-nav-open');
                if (overlay) overlay.classList.toggle('open', isOpen);
                if (btn) btn.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
                document.body.style.overflow = isOpen ? 'hidden' : '';
            }
        }

        function closeSiteMobileNav() {
            const nav = document.getElementById('site_nav_links');
            const overlay = document.getElementById('site_nav_drawer_overlay');
            const btn = document.getElementById('site_mobile_menu_btn');
            if (nav) nav.classList.remove('mobile-nav-open');
            if (overlay) overlay.classList.remove('open');
            if (btn) btn.setAttribute('aria-expanded', 'false');
            document.body.style.overflow = '';
        }

        // Close drawers on Escape key
        window.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                closeSiteMobileNav();
                const rail = document.getElementById('consultation_left_rail');
                const railBackdrop = document.getElementById('sidebar_backdrop_overlay');
                if (rail && rail.classList.contains('mobile-open')) {
                    rail.classList.remove('mobile-open');
                    if (railBackdrop) railBackdrop.classList.remove('active');
                }
                const panel = document.getElementById('consultation_right_panel');
                const panelBackdrop = document.getElementById('context_backdrop_overlay');
                if (panel && panel.classList.contains('mobile-open')) {
                    panel.classList.remove('mobile-open');
                    if (panelBackdrop) panelBackdrop.classList.remove('active');
                }
            }
        });

        function escapeHtml(str) {
            if (str === null || str === undefined) return '';
            return String(str)
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#039;');
        }
        loadRaceStatus();
        refreshRaceResultCard();
        if (window.location.pathname === '/consultation') {
            window.addEventListener('DOMContentLoaded', openConsultation);
        }

        /* ===== ANTIGRAVITY-INSPIRED CURSOR BACKGROUND INTERACTION ===== */
        (function initAntigravityCursor() {
            if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

            const canvas = document.createElement('canvas');
            canvas.className = 'cursor-canvas-bg';
            const orb = document.createElement('div');
            orb.className = 'cursor-glow-orb';
            document.body.prepend(canvas);
            document.body.prepend(orb);

            const ctx = canvas.getContext('2d');
            let width = (canvas.width = window.innerWidth);
            let height = (canvas.height = window.innerHeight);

            window.addEventListener('resize', () => {
                width = canvas.width = window.innerWidth;
                height = canvas.height = window.innerHeight;
            });

            const particles = [];
            let mouseX = -1000;
            let mouseY = -1000;
            let targetX = -1000;
            let targetY = -1000;

            window.addEventListener('pointermove', (e) => {
                targetX = e.clientX;
                targetY = e.clientY;

                if (Math.random() < 0.6) {
                    particles.push({
                        x: e.clientX,
                        y: e.clientY,
                        vx: (Math.random() - 0.5) * 0.8,
                        vy: (Math.random() - 0.5) * 0.8,
                        size: Math.random() * 2 + 1,
                        alpha: 0.7,
                        color: Math.random() > 0.5 ? '99, 102, 241' : '6, 182, 212'
                    });
                }
            });

            function animate() {
                mouseX += (targetX - mouseX) * 0.12;
                mouseY += (targetY - mouseY) * 0.12;
                orb.style.transform = `translate3d(${mouseX}px, ${mouseY}px, 0)`;

                ctx.clearRect(0, 0, width, height);

                for (let i = particles.length - 1; i >= 0; i--) {
                    const p = particles[i];
                    p.x += p.vx;
                    p.y += p.vy;
                    p.alpha -= 0.015;

                    if (p.alpha <= 0) {
                        particles.splice(i, 1);
                        continue;
                    }

                    ctx.beginPath();
                    ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
                    ctx.fillStyle = `rgba(${p.color}, ${p.alpha})`;
                    ctx.shadowColor = `rgba(${p.color}, 0.5)`;
                    ctx.shadowBlur = 6;
                    ctx.fill();
                }

                requestAnimationFrame(animate);
            }
            requestAnimationFrame(animate);
        })();
