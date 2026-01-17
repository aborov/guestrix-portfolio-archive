/*
 * Date utilities for consistent date handling across the frontend
 * 
 * This module provides functions to handle reservation dates consistently
 * and avoid timezone-related display issues between hosts and guests.
 */

/**
 * Parse a date string safely, treating it as a date-only value
 * 
 * @param {string|null|undefined} dateStr - Date string in YYYY-MM-DD format or ISO datetime
 * @returns {Date|null} - Date object or null if invalid
 */
function parseDateSafely(dateStr) {
    if (!dateStr || typeof dateStr !== 'string') {
        return null;
    }

    try {
        // If the date string contains time info, extract just the date part
        let dateOnlyStr = dateStr;
        if (dateStr.includes('T')) {
            dateOnlyStr = dateStr.split('T')[0];
        }

        // Validate format (YYYY-MM-DD)
        if (!/^\d{4}-\d{2}-\d{2}$/.test(dateOnlyStr)) {
            return null;
        }

        // Create date object treating it as local date (avoid timezone conversion)
        const [year, month, day] = dateOnlyStr.split('-').map(Number);
        return new Date(year, month - 1, day); // month is 0-indexed
    } catch (e) {
        console.warn('Error parsing date:', dateStr, e);
        return null;
    }
}

/**
 * Format a date for display, consistently showing the same date regardless of user timezone
 * 
 * @param {string|Date|null|undefined} dateInput - Date to format
 * @param {string} format - Format type: 'short' (Jan 15, 2024), 'long' (January 15, 2024), 'iso' (2024-01-15)
 * @returns {string} - Formatted date string
 */
function formatDateForDisplay(dateInput, format = 'short') {
    if (!dateInput) {
        return 'Invalid Date';
    }

    let dateObj;
    if (typeof dateInput === 'string') {
        dateObj = parseDateSafely(dateInput);
    } else if (dateInput instanceof Date) {
        dateObj = dateInput;
    } else {
        return 'Invalid Date';
    }

    if (!dateObj) {
        return 'Invalid Date';
    }

    try {
        const options = {
            timeZone: 'UTC' // This ensures consistent display regardless of user timezone
        };

        switch (format) {
            case 'short':
                return dateObj.toLocaleDateString('en-US', {
                    ...options,
                    month: 'short',
                    day: 'numeric',
                    year: 'numeric'
                }); // Jan 15, 2024
            case 'long':
                return dateObj.toLocaleDateString('en-US', {
                    ...options,
                    month: 'long',
                    day: 'numeric',
                    year: 'numeric'
                }); // January 15, 2024
            case 'iso':
                return dateObj.toISOString().split('T')[0]; // 2024-01-15
            default:
                return dateObj.toLocaleDateString('en-US', {
                    ...options,
                    month: 'short',
                    day: 'numeric',
                    year: 'numeric'
                }); // Default to short
        }
    } catch (e) {
        console.warn('Error formatting date:', dateInput, e);
        return 'Invalid Date';
    }
}

/**
 * Check if a reservation is currently active (guest is staying)
 * 
 * @param {string} startDate - Start date in YYYY-MM-DD format
 * @param {string} endDate - End date in YYYY-MM-DD format
 * @returns {boolean} - True if reservation is active today
 */
function isReservationActive(startDate, endDate) {
    if (!startDate || !endDate) {
        return false;
    }

    try {
        const start = parseDateSafely(startDate);
        const end = parseDateSafely(endDate);
        const today = new Date();
        
        // Reset time to compare dates only
        today.setHours(0, 0, 0, 0);
        
        if (!start || !end) {
            return false;
        }

        return start <= today && today <= end;
    } catch (e) {
        console.warn('Error checking reservation status:', startDate, endDate, e);
        return false;
    }
}

/**
 * Check if a reservation is upcoming (starts in the future)
 * 
 * @param {string} startDate - Start date in YYYY-MM-DD format
 * @returns {boolean} - True if reservation starts in the future
 */
function isReservationUpcoming(startDate) {
    if (!startDate) {
        return false;
    }

    try {
        const start = parseDateSafely(startDate);
        const today = new Date();
        
        // Reset time to compare dates only
        today.setHours(0, 0, 0, 0);
        
        if (!start) {
            return false;
        }

        return start > today;
    } catch (e) {
        console.warn('Error checking upcoming reservation:', startDate, e);
        return false;
    }
}

/**
 * Get reservation status badge class and text
 * 
 * @param {string} startDate - Start date in YYYY-MM-DD format
 * @param {string} endDate - End date in YYYY-MM-DD format
 * @returns {Object} - Object with badge class and text
 */
function getReservationStatus(startDate, endDate) {
    if (isReservationActive(startDate, endDate)) {
        return {
            class: 'bg-success',
            text: 'Active'
        };
    } else if (isReservationUpcoming(startDate)) {
        return {
            class: 'bg-info',
            text: 'Upcoming'
        };
    } else {
        return {
            class: 'bg-secondary',
            text: 'Past'
        };
    }
}

/**
 * Sort reservations by date priority (active first, then upcoming, then past)
 * 
 * @param {Array} reservations - Array of reservation objects
 * @returns {Array} - Sorted array of reservations
 */
function sortReservationsByDate(reservations) {
    return reservations.sort((a, b) => {
        const aStart = parseDateSafely(a.startDate);
        const aEnd = parseDateSafely(a.endDate);
        const bStart = parseDateSafely(b.startDate);
        const bEnd = parseDateSafely(b.endDate);

        // Handle invalid dates
        if (!aStart || !aEnd) return 1;
        if (!bStart || !bEnd) return -1;

        const today = new Date();
        today.setHours(0, 0, 0, 0);

        // Determine status for each reservation
        const aActive = aStart <= today && today <= aEnd;
        const bActive = bStart <= today && today <= bEnd;
        const aUpcoming = aStart > today;
        const bUpcoming = bStart > today;

        // Active reservations first
        if (aActive && !bActive) return -1;
        if (!aActive && bActive) return 1;

        // Then upcoming reservations
        if (aUpcoming && !bUpcoming) return -1;
        if (!aUpcoming && bUpcoming) return 1;

        // Within same category, sort by date
        if (aUpcoming && bUpcoming) {
            // For upcoming, sooner comes first
            return aStart - bStart;
        } else {
            // For past, more recent comes first
            return bEnd - aEnd;
        }
    });
}

// Export functions for use in other modules
window.DateUtils = {
    parseDateSafely,
    formatDateForDisplay,
    isReservationActive,
    isReservationUpcoming,
    getReservationStatus,
    sortReservationsByDate
}; 