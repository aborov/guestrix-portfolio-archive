import config from './config.js';

document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('calculatorForm');
    const statusEl = document.getElementById('calcStatus');

    function setStatus(msg, isError = false) {
        if (!statusEl) return;
        statusEl.style.display = 'block';
        statusEl.style.color = isError ? '#b00020' : '#1b5e20';
        statusEl.textContent = msg;
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

                const blob = await response.blob();
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                const safeZip = zipCode.replace(/[^0-9]/g, '');
                a.download = `Guestrix_Earnings_Estimate_${safeZip}.xlsx`;
                document.body.appendChild(a);
                a.click();
                a.remove();
                window.URL.revokeObjectURL(url);
                setStatus('Your Excel estimate has been downloaded.');
            } catch (err) {
                console.error(err);
                setStatus('Sorry, something went wrong. Please try again later.', true);
            }
        });
    }
});


