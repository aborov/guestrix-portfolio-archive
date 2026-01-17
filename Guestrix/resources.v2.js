import config from './config.js';

document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('calculatorForm');
    const statusEl = document.getElementById('calcStatus');
    const feeForm = document.getElementById('feeForm');
    const feeStatusEl = document.getElementById('feeStatus');
    const feeResultTable = document.getElementById('feeResultTable');
    const feeChart = document.getElementById('feeChart');
    // Optimizer
    const optimizerForm = document.getElementById('optimizerForm');
    const optStatusEl = document.getElementById('optStatus');
    const optimizerResults = document.getElementById('optimizerResults');
    const beforeTitleEl = document.getElementById('beforeTitle');
    const beforeDescEl = document.getElementById('beforeDesc');
    const afterTitleEl = document.getElementById('afterTitle');
    const afterDescEl = document.getElementById('afterDesc');
    const scoreAppealEl = document.getElementById('scoreAppeal');
    const scoreBookingEl = document.getElementById('scoreBooking');
    const scoreSearchEl = document.getElementById('scoreSearch');
    const scoreTrustEl = document.getElementById('scoreTrust');
    const tipsAppealEl = document.getElementById('tipsAppeal');
    const tipsBookingEl = document.getElementById('tipsBooking');
    const tipsSearchEl = document.getElementById('tipsSearch');
    const tipsTrustEl = document.getElementById('tipsTrust');
    const whatsappJoinLink = document.getElementById('whatsappJoinLink');

    // Feedback popup
    const feedbackPopup = document.getElementById('feedbackPopup');
    const starContainer = document.getElementById('starContainer');
    const submitRatingBtn = document.getElementById('submitRatingBtn');
    const ratingStatus = document.getElementById('ratingStatus');
    let lastSubmissionId = null;
    let selectedRating = 0;

    function setStatus(msg, isError = false) {
        if (!statusEl) return;
        statusEl.style.display = 'block';
        statusEl.style.color = isError ? '#b00020' : '#1b5e20';
        statusEl.textContent = msg;
    }

    function setFeeStatus(msg, isError = false) {
        if (!feeStatusEl) return;
        feeStatusEl.style.display = 'block';
        feeStatusEl.style.color = isError ? '#b00020' : '#1b5e20';
        feeStatusEl.textContent = msg;
    }

    function setOptStatus(msg, isError = false) {
        if (!optStatusEl) return;
        optStatusEl.style.display = 'block';
        optStatusEl.style.color = isError ? '#b00020' : '#1b5e20';
        optStatusEl.textContent = msg;
    }

    function showFeedbackPopup(submissionId) {
        if (!feedbackPopup || !starContainer || !submitRatingBtn) return;
        lastSubmissionId = submissionId || null;
        selectedRating = 0;
        // reset stars
        starContainer.querySelectorAll('.star').forEach((el) => { el.style.color = '#ccc'; });
        ratingStatus.style.display = 'none';
        feedbackPopup.style.display = 'block';
    }

    if (starContainer) {
        starContainer.addEventListener('click', (e) => {
            const t = e.target;
            if (!(t && t.classList && t.classList.contains('star'))) return;
            const v = Number(t.getAttribute('data-v')) || 0;
            selectedRating = v;
            starContainer.querySelectorAll('.star').forEach((el) => {
                const ev = Number(el.getAttribute('data-v')) || 0;
                el.style.color = ev <= v ? '#f4b400' : '#ccc';
            });
        });
    }

    if (submitRatingBtn) {
        submitRatingBtn.addEventListener('click', async () => {
            if (!lastSubmissionId || !selectedRating) {
                ratingStatus.style.display = 'block';
                ratingStatus.style.color = '#b00020';
                ratingStatus.textContent = 'Please select a rating first.';
                return;
            }
            try {
                const resp = await fetch(`${config.api.endpoint}/waitlist/rating`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ id: lastSubmissionId, rating: selectedRating })
                });
                if (!resp.ok) throw new Error('Failed to save rating');
                ratingStatus.style.display = 'block';
                ratingStatus.style.color = '#1b5e20';
                ratingStatus.textContent = 'Thanks for the feedback!';
                setTimeout(() => { feedbackPopup.style.display = 'none'; }, 1200);
            } catch (e) {
                ratingStatus.style.display = 'block';
                ratingStatus.style.color = '#b00020';
                ratingStatus.textContent = 'Could not save rating. Please try later.';
            }
        });
    }

    function calculateAndRenderFeeTool() {
        if (!feeResultTable || !feeChart) return;
        const night = parseFloat(document.getElementById('nightly').value) || 0;
        const nights = parseInt(document.getElementById('nights').value, 10) || 0;
        const cleaning = parseFloat(document.getElementById('cleaning').value) || 0;

        const base = night * nights + cleaning;
        // Airbnb PMS BEFORE Oct 27: 3% host fee, ~14% guest fee
        const abnbBefore_guestFee = base * 0.14;
        const abnbBefore_hostPayout = base * (1 - 0.03);
        const abnbBefore_guestTotal = base + abnbBefore_guestFee;

        // Airbnb PMS AFTER Oct 27: 15.5% host-only fee, no guest fee
        const abnbAfter_guestFee = 0;
        const abnbAfter_hostPayout = base * (1 - 0.155);
        const abnbAfter_guestTotal = base;

        // Adjusted Airbnb Nightly to match pre-change payout
        const targetPayout = abnbBefore_hostPayout;
        const baseAdj = targetPayout / (1 - 0.155);
        const nightlyAdj = nights > 0 ? (baseAdj - cleaning) / nights : 0;
        const abnbAdj_guestFee = 0;
        const abnbAdj_hostPayout = targetPayout;
        const abnbAdj_guestTotal = baseAdj;

        // VRBO: ~8% effective host fee; show ~8% guest service fee for display
        const vrbo_guestFee = base * 0.08;
        const vrbo_hostPayout = base * (1 - 0.08);
        const vrbo_guestTotal = base + vrbo_guestFee;

        // Booking.com: ~15% commission, no guest fee
        const booking_guestFee = 0;
        const booking_hostPayout = base * (1 - 0.15);
        const booking_guestTotal = base;

        feeResultTable.innerHTML = `
            <tr style="background: rgba(42, 157, 143, 0.1);">
              <th style="text-align:left; padding:8px; border:1px solid var(--gray-200);">Platform & Scenario</th>
              <th style="text-align:right; padding:8px; border:1px solid var(--gray-200);">Nightly Rate ($)</th>
              <th style="text-align:right; padding:8px; border:1px solid var(--gray-200);">Guest Service Fee</th>
              <th style="text-align:right; padding:8px; border:1px solid var(--gray-200);">Total Guest Price</th>
              <th style="text-align:right; padding:8px; border:1px solid var(--gray-200);"><b>Host Payout ($)</b></th>
            </tr>
            ${[
                ['Airbnb (PMS) BEFORE Oct 27', night, abnbBefore_guestFee, abnbBefore_guestTotal, abnbBefore_hostPayout],
                ['Airbnb (PMS) AFTER Oct 27', night, abnbAfter_guestFee, abnbAfter_guestTotal, abnbAfter_hostPayout],
                ['Airbnb Adjusted Price (PMS)*', nightlyAdj, abnbAdj_guestFee, abnbAdj_guestTotal, abnbAdj_hostPayout],
                ['VRBO', night, vrbo_guestFee, vrbo_guestTotal, vrbo_hostPayout],
                ['Booking.com', night, booking_guestFee, booking_guestTotal, booking_hostPayout]
            ].map(([name, nightlyShown, guestFee, guestTotal, payout]) => `
            <tr>
              <td style="text-align:left; padding:8px; border:1px solid var(--gray-200);">${name}</td>
              <td style="padding:8px; border:1px solid var(--gray-200);">$${Number(nightlyShown).toFixed(2)}</td>
              <td style="padding:8px; border:1px solid var(--gray-200);">${guestFee ? `$${guestFee.toFixed(2)}` : '$0.00'}</td>
              <td style="padding:8px; border:1px solid var(--gray-200);">$${guestTotal.toFixed(2)}</td>
              <td style="padding:8px; border:1px solid var(--gray-200);"><b>$${payout.toFixed(2)}</b></td>
            </tr>`).join('')}
        `;

        // Remove any existing footnotes first, then add new one
        const existingFootnotes = feeChart.parentNode.querySelectorAll('p[style*="font-style:italic"]');
        existingFootnotes.forEach(footnote => footnote.remove());
        
        // Add footnote after the chart
        feeChart.insertAdjacentHTML('afterend', '<p style="font-size:0.85rem; color:#666; margin-top:0.5rem; font-style:italic;">* Airbnb Adjusted Price to achieve the same payout as before Oct 27 (with PMS)</p>');

        const max = Math.max(abnbBefore_hostPayout, abnbAfter_hostPayout, abnbAdj_hostPayout, vrbo_hostPayout, booking_hostPayout) || 1;
        const multiplier = (max > 300 ? 210 / max : 1);

        feeChart.innerHTML = `
          <h4 class="section-title" style="font-size:1.25rem; margin-bottom:1rem; text-align:center;">Host Payout Comparison</h4>
          <div style='height: 220px; display: flex; align-items: flex-end; justify-content:center; gap:14px;'>
            ${[
              ['#ee6055', abnbBefore_hostPayout, 'Airbnb BEFORE'],
              ['#f39c12', abnbAfter_hostPayout, 'Airbnb AFTER'],
              ['#7cb342', abnbAdj_hostPayout, 'Airbnb Adjusted*'],
              ['#2a9d8f', vrbo_hostPayout, 'Vrbo'],
              ['#161032', booking_hostPayout, 'Booking']
            ].map(([color, val]) => `
              <div style="position:relative; width:60px;">
                <div style="height:${(val*multiplier).toFixed(0)}px; background:${color}; width:60px; border-radius:4px;"></div>
                <div style="position:absolute; bottom:${(val*multiplier).toFixed(0)}px; left:0; width:60px; text-align:center; font-size:0.8rem; transform:translateY(-6px); color:#333;">$${val.toFixed(0)}</div>
              </div>
            `).join('')}
          </div>
          <div style="display:flex; gap:10px; margin-top:6px; justify-content:center;">
            <span style="text-align:center; width:60px;">Airbnb
            BEFORE</span>
            <span style="text-align:center; width:60px;">Airbnb AFTER</span>
            <span style="text-align:center; width:60px;">Airbnb Adj.*</span>
            <span style="text-align:center; width:60px;">Vrbo</span>
            <span style="text-align:center; width:60px;">Booking</span>
          </div>
        `;
    }

    if (feeForm) {
        // Initial render with defaults
        calculateAndRenderFeeTool();

        feeForm.addEventListener('submit', async (e) => {
            e.preventDefault();

            const firstName = (document.getElementById('feeFirstName')?.value || '').trim();
            const lastName = (document.getElementById('feeLastName')?.value || '').trim();
            const email = (document.getElementById('feeEmail')?.value || '').trim();
            const nightly = parseFloat(document.getElementById('nightly').value) || 0;
            const nights = parseInt(document.getElementById('nights').value, 10) || 0;
            const cleaning = parseFloat(document.getElementById('cleaning').value) || 0;
            // Advanced fields removed from calculation per new spec

            // Render results immediately
            calculateAndRenderFeeTool();
            setFeeStatus('Calculating, saving, and generating your PDF...');

            try {
                const response = await fetch(`${config.api.endpoint}/waitlist/fee-comparison`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        firstName,
                        lastName,
                        email,
                        nightly,
                        nights,
                        cleaning,
                        tax: 0,
                        otherFees: 0,
                        discount: 0,
                        marketing: 0,
                        message: 'Fee Comparison Tool'
                    })
                });
                if (!response.ok) {
                    const errText = await response.text();
                    throw new Error(errText || 'Failed to save submission');
                }
                const data = await response.json().catch(() => null);
                if (data && data.fileName && data.mimeType && data.dataBase64) {
                    const url = `data:${data.mimeType};base64,${data.dataBase64}`;
                    const a = document.createElement('a');
                    a.href = url;
                    const safeName = `${(firstName||'')}_${(lastName||'')}`.replace(/[^a-z0-9_\-]+/ig, '').replace(/^_+|_+$/g, '');
                    a.download = data.fileName || `Guestrix_Fee_Comparison_${safeName||'Guest'}.pdf`;
                    document.body.appendChild(a);
                    a.click();
                    a.remove();
                }
                setFeeStatus('Saved. Your comparison is shown below and a PDF was downloaded.');
                if (data && data.id) {
                    showFeedbackPopup(data.id);
                }
            } catch (err) {
                console.error(err);
                setFeeStatus('Compared locally. Saving failed, but you can still view results.', true);
            }
        });
    }

    if (form) {
        form.addEventListener('submit', async (e) => {
            e.preventDefault();

            const zipCode = document.getElementById('zipCode').value.trim();
            const firstName = document.getElementById('firstName').value.trim();
            const lastName = document.getElementById('lastName').value.trim();
            const email = document.getElementById('email').value.trim();

            if (!zipCode || !/^\d{5}$/.test(zipCode)) {
                setStatus('Please enter a valid 5-digit ZIP code.', true);
                return;
            }

            setStatus('Generating your Excel estimate...');

            try {
                const response = await fetch(`${config.api.endpoint}/waitlist/calculator`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({ zipCode, firstName, lastName, email })
                });

                if (!response.ok) {
                    const errText = await response.text();
                    throw new Error(errText || 'Failed to generate file');
                }

                // Expect JSON with id + base64 data
                const { id, fileName, mimeType, dataBase64 } = await response.json();
                // Use a base64 data URL to avoid any binary decoding issues across browsers
                const url = `data:${mimeType || 'application/octet-stream'};base64,${dataBase64}`;
                const a = document.createElement('a');
                a.href = url;
                a.download = fileName || `Guestrix_Earnings_Estimate_${zipCode.replace(/[^0-9]/g, '')}.xlsx`;
                document.body.appendChild(a);
                a.click();
                a.remove();
                setStatus('Your Excel estimate has been downloaded.');
                if (id) {
                    showFeedbackPopup(id);
                }
            } catch (err) {
                console.error(err);
                setStatus('Sorry, something went wrong. Please try again later.', true);
            }
        });
    }

    // Listing Optimizer
    if (optimizerForm) {
        optimizerForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const firstName = (document.getElementById('optFirstName')?.value || '').trim();
            const lastName = (document.getElementById('optLastName')?.value || '').trim();
            const email = (document.getElementById('optEmail')?.value || '').trim();
            const title = (document.getElementById('optTitle')?.value || '').trim();
            const description = (document.getElementById('optDescription')?.value || '').trim();
            if (!title || !description) {
                setOptStatus('Please provide both title and description.', true);
                return;
            }
            setOptStatus('Optimizing your listing...');
            try {
                const resp = await fetch(`${config.api.endpoint}/waitlist/listing-optimizer`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ firstName, lastName, email, title, description })
                });
                if (!resp.ok) {
                    const t = await resp.text();
                    throw new Error(t || 'Failed to optimize');
                }
                const { id, result } = await resp.json();
                // Render results
                if (beforeTitleEl) beforeTitleEl.textContent = title;
                if (beforeDescEl) beforeDescEl.textContent = description;
                if (afterTitleEl) afterTitleEl.textContent = result?.optimizedTitle || '';
                if (afterDescEl) afterDescEl.textContent = result?.optimizedDescription || '';
                function listToUl(el, arr) {
                    if (!el) return;
                    el.innerHTML = (arr || []).map((s) => `<li>${s}</li>`).join('');
                }
                // Render horizontal score bars
                function renderScoreBar(container, value) {
                    if (!container) return;
                    const v = Math.max(0, Math.min(100, Number(value) || 0));
                    container.innerHTML = `
                        <div class="score-row">
                          <div class="score-value">${v}/100</div>
                          <div class="score-track"><div class="score-fill" style="width:${v}%;"></div></div>
                        </div>
                    `;
                }
                renderScoreBar(scoreAppealEl, result?.scores?.guestAppeal);
                renderScoreBar(scoreBookingEl, result?.scores?.bookingPotential);
                renderScoreBar(scoreSearchEl, result?.scores?.searchVisibility);
                renderScoreBar(scoreTrustEl, result?.scores?.trustClarity);
                listToUl(tipsAppealEl, result?.suggestions?.guestAppeal);
                listToUl(tipsBookingEl, result?.suggestions?.bookingPotential);
                listToUl(tipsSearchEl, result?.suggestions?.searchVisibility);
                listToUl(tipsTrustEl, result?.suggestions?.trustClarity);
                if (optimizerResults) optimizerResults.style.display = 'block';
                setOptStatus('Done. See the optimized version and tips below.');
                if (id) showFeedbackPopup(id);
            } catch (err) {
                console.error(err);
                setOptStatus('Optimization failed. Please try again later.', true);
            }
        });
    }

    // Track WhatsApp join link clicks
    if (whatsappJoinLink) {
        whatsappJoinLink.addEventListener('click', async () => {
            try {
                await fetch(`${config.api.endpoint}/waitlist/fee-comparison`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ message: 'Whatsapp link clicked', track: true })
                });
            } catch (_) { /* ignore */ }
        });
    }
});


