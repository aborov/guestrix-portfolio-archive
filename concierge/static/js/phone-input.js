/**
 * Enhanced Phone Input Component with Country Code Dropdown
 * Provides a dropdown with country codes, flags, and names
 */

// Country data with codes, names, and flag emojis
const COUNTRIES = [
    { code: '+1', name: 'United States', flag: '🇺🇸', iso: 'US' },
    { code: '+1', name: 'Canada', flag: '🇨🇦', iso: 'CA' },
    { code: '+7', name: 'Russia', flag: '🇷🇺', iso: 'RU' },
    { code: '+7', name: 'Kazakhstan', flag: '🇰🇿', iso: 'KZ' },
    { code: '+20', name: 'Egypt', flag: '🇪🇬', iso: 'EG' },
    { code: '+27', name: 'South Africa', flag: '🇿🇦', iso: 'ZA' },
    { code: '+30', name: 'Greece', flag: '🇬🇷', iso: 'GR' },
    { code: '+31', name: 'Netherlands', flag: '🇳🇱', iso: 'NL' },
    { code: '+32', name: 'Belgium', flag: '🇧🇪', iso: 'BE' },
    { code: '+33', name: 'France', flag: '🇫🇷', iso: 'FR' },
    { code: '+34', name: 'Spain', flag: '🇪🇸', iso: 'ES' },
    { code: '+36', name: 'Hungary', flag: '🇭🇺', iso: 'HU' },
    { code: '+39', name: 'Italy', flag: '🇮🇹', iso: 'IT' },
    { code: '+40', name: 'Romania', flag: '🇷🇴', iso: 'RO' },
    { code: '+41', name: 'Switzerland', flag: '🇨🇭', iso: 'CH' },
    { code: '+43', name: 'Austria', flag: '🇦🇹', iso: 'AT' },
    { code: '+44', name: 'United Kingdom', flag: '🇬🇧', iso: 'GB' },
    { code: '+45', name: 'Denmark', flag: '🇩🇰', iso: 'DK' },
    { code: '+46', name: 'Sweden', flag: '🇸🇪', iso: 'SE' },
    { code: '+47', name: 'Norway', flag: '🇳🇴', iso: 'NO' },
    { code: '+48', name: 'Poland', flag: '🇵🇱', iso: 'PL' },
    { code: '+49', name: 'Germany', flag: '🇩🇪', iso: 'DE' },
    { code: '+51', name: 'Peru', flag: '🇵🇪', iso: 'PE' },
    { code: '+52', name: 'Mexico', flag: '🇲🇽', iso: 'MX' },
    { code: '+53', name: 'Cuba', flag: '🇨🇺', iso: 'CU' },
    { code: '+54', name: 'Argentina', flag: '🇦🇷', iso: 'AR' },
    { code: '+55', name: 'Brazil', flag: '🇧🇷', iso: 'BR' },
    { code: '+56', name: 'Chile', flag: '🇨🇱', iso: 'CL' },
    { code: '+57', name: 'Colombia', flag: '🇨🇴', iso: 'CO' },
    { code: '+58', name: 'Venezuela', flag: '🇻🇪', iso: 'VE' },
    { code: '+60', name: 'Malaysia', flag: '🇲🇾', iso: 'MY' },
    { code: '+61', name: 'Australia', flag: '🇦🇺', iso: 'AU' },
    { code: '+62', name: 'Indonesia', flag: '🇮🇩', iso: 'ID' },
    { code: '+63', name: 'Philippines', flag: '🇵🇭', iso: 'PH' },
    { code: '+64', name: 'New Zealand', flag: '🇳🇿', iso: 'NZ' },
    { code: '+65', name: 'Singapore', flag: '🇸🇬', iso: 'SG' },
    { code: '+66', name: 'Thailand', flag: '🇹🇭', iso: 'TH' },
    { code: '+81', name: 'Japan', flag: '🇯🇵', iso: 'JP' },
    { code: '+82', name: 'South Korea', flag: '🇰🇷', iso: 'KR' },
    { code: '+84', name: 'Vietnam', flag: '🇻🇳', iso: 'VN' },
    { code: '+86', name: 'China', flag: '🇨🇳', iso: 'CN' },
    { code: '+90', name: 'Turkey', flag: '🇹🇷', iso: 'TR' },
    { code: '+91', name: 'India', flag: '🇮🇳', iso: 'IN' },
    { code: '+92', name: 'Pakistan', flag: '🇵🇰', iso: 'PK' },
    { code: '+93', name: 'Afghanistan', flag: '🇦🇫', iso: 'AF' },
    { code: '+94', name: 'Sri Lanka', flag: '🇱🇰', iso: 'LK' },
    { code: '+95', name: 'Myanmar', flag: '🇲🇲', iso: 'MM' },
    { code: '+98', name: 'Iran', flag: '🇮🇷', iso: 'IR' },
    { code: '+212', name: 'Morocco', flag: '🇲🇦', iso: 'MA' },
    { code: '+213', name: 'Algeria', flag: '🇩🇿', iso: 'DZ' },
    { code: '+216', name: 'Tunisia', flag: '🇹🇳', iso: 'TN' },
    { code: '+218', name: 'Libya', flag: '🇱🇾', iso: 'LY' },
    { code: '+220', name: 'Gambia', flag: '🇬🇲', iso: 'GM' },
    { code: '+221', name: 'Senegal', flag: '🇸🇳', iso: 'SN' },
    { code: '+222', name: 'Mauritania', flag: '🇲🇷', iso: 'MR' },
    { code: '+223', name: 'Mali', flag: '🇲🇱', iso: 'ML' },
    { code: '+224', name: 'Guinea', flag: '🇬🇳', iso: 'GN' },
    { code: '+225', name: 'Ivory Coast', flag: '🇨🇮', iso: 'CI' },
    { code: '+226', name: 'Burkina Faso', flag: '🇧🇫', iso: 'BF' },
    { code: '+227', name: 'Niger', flag: '🇳🇪', iso: 'NE' },
    { code: '+228', name: 'Togo', flag: '🇹🇬', iso: 'TG' },
    { code: '+229', name: 'Benin', flag: '🇧🇯', iso: 'BJ' },
    { code: '+230', name: 'Mauritius', flag: '🇲🇺', iso: 'MU' },
    { code: '+231', name: 'Liberia', flag: '🇱🇷', iso: 'LR' },
    { code: '+232', name: 'Sierra Leone', flag: '🇸🇱', iso: 'SL' },
    { code: '+233', name: 'Ghana', flag: '🇬🇭', iso: 'GH' },
    { code: '+234', name: 'Nigeria', flag: '🇳🇬', iso: 'NG' },
    { code: '+235', name: 'Chad', flag: '🇹🇩', iso: 'TD' },
    { code: '+236', name: 'Central African Republic', flag: '🇨🇫', iso: 'CF' },
    { code: '+237', name: 'Cameroon', flag: '🇨🇲', iso: 'CM' },
    { code: '+238', name: 'Cape Verde', flag: '🇨🇻', iso: 'CV' },
    { code: '+239', name: 'São Tomé and Príncipe', flag: '🇸🇹', iso: 'ST' },
    { code: '+240', name: 'Equatorial Guinea', flag: '🇬🇶', iso: 'GQ' },
    { code: '+241', name: 'Gabon', flag: '🇬🇦', iso: 'GA' },
    { code: '+242', name: 'Republic of the Congo', flag: '🇨🇬', iso: 'CG' },
    { code: '+243', name: 'Democratic Republic of the Congo', flag: '🇨🇩', iso: 'CD' },
    { code: '+244', name: 'Angola', flag: '🇦🇴', iso: 'AO' },
    { code: '+245', name: 'Guinea-Bissau', flag: '🇬🇼', iso: 'GW' },
    { code: '+246', name: 'British Indian Ocean Territory', flag: '🇮🇴', iso: 'IO' },
    { code: '+248', name: 'Seychelles', flag: '🇸🇨', iso: 'SC' },
    { code: '+249', name: 'Sudan', flag: '🇸🇩', iso: 'SD' },
    { code: '+250', name: 'Rwanda', flag: '🇷🇼', iso: 'RW' },
    { code: '+251', name: 'Ethiopia', flag: '🇪🇹', iso: 'ET' },
    { code: '+252', name: 'Somalia', flag: '🇸🇴', iso: 'SO' },
    { code: '+253', name: 'Djibouti', flag: '🇩🇯', iso: 'DJ' },
    { code: '+254', name: 'Kenya', flag: '🇰🇪', iso: 'KE' },
    { code: '+255', name: 'Tanzania', flag: '🇹🇿', iso: 'TZ' },
    { code: '+256', name: 'Uganda', flag: '🇺🇬', iso: 'UG' },
    { code: '+257', name: 'Burundi', flag: '🇧🇮', iso: 'BI' },
    { code: '+258', name: 'Mozambique', flag: '🇲🇿', iso: 'MZ' },
    { code: '+260', name: 'Zambia', flag: '🇿🇲', iso: 'ZM' },
    { code: '+261', name: 'Madagascar', flag: '🇲🇬', iso: 'MG' },
    { code: '+262', name: 'Réunion', flag: '🇷🇪', iso: 'RE' },
    { code: '+263', name: 'Zimbabwe', flag: '🇿🇼', iso: 'ZW' },
    { code: '+264', name: 'Namibia', flag: '🇳🇦', iso: 'NA' },
    { code: '+265', name: 'Malawi', flag: '🇲🇼', iso: 'MW' },
    { code: '+266', name: 'Lesotho', flag: '🇱🇸', iso: 'LS' },
    { code: '+267', name: 'Botswana', flag: '🇧🇼', iso: 'BW' },
    { code: '+268', name: 'Eswatini', flag: '🇸🇿', iso: 'SZ' },
    { code: '+269', name: 'Comoros', flag: '🇰🇲', iso: 'KM' },
    { code: '+290', name: 'Saint Helena', flag: '🇸🇭', iso: 'SH' },
    { code: '+291', name: 'Eritrea', flag: '🇪🇷', iso: 'ER' },
    { code: '+297', name: 'Aruba', flag: '🇦🇼', iso: 'AW' },
    { code: '+298', name: 'Faroe Islands', flag: '🇫🇴', iso: 'FO' },
    { code: '+299', name: 'Greenland', flag: '🇬🇱', iso: 'GL' },
    { code: '+350', name: 'Gibraltar', flag: '🇬🇮', iso: 'GI' },
    { code: '+351', name: 'Portugal', flag: '🇵🇹', iso: 'PT' },
    { code: '+352', name: 'Luxembourg', flag: '🇱🇺', iso: 'LU' },
    { code: '+353', name: 'Ireland', flag: '🇮🇪', iso: 'IE' },
    { code: '+354', name: 'Iceland', flag: '🇮🇸', iso: 'IS' },
    { code: '+355', name: 'Albania', flag: '🇦🇱', iso: 'AL' },
    { code: '+356', name: 'Malta', flag: '🇲🇹', iso: 'MT' },
    { code: '+357', name: 'Cyprus', flag: '🇨🇾', iso: 'CY' },
    { code: '+358', name: 'Finland', flag: '🇫🇮', iso: 'FI' },
    { code: '+359', name: 'Bulgaria', flag: '🇧🇬', iso: 'BG' },
    { code: '+370', name: 'Lithuania', flag: '🇱🇹', iso: 'LT' },
    { code: '+371', name: 'Latvia', flag: '🇱🇻', iso: 'LV' },
    { code: '+372', name: 'Estonia', flag: '🇪🇪', iso: 'EE' },
    { code: '+373', name: 'Moldova', flag: '🇲🇩', iso: 'MD' },
    { code: '+374', name: 'Armenia', flag: '🇦🇲', iso: 'AM' },
    { code: '+375', name: 'Belarus', flag: '🇧🇾', iso: 'BY' },
    { code: '+376', name: 'Andorra', flag: '🇦🇩', iso: 'AD' },
    { code: '+377', name: 'Monaco', flag: '🇲🇨', iso: 'MC' },
    { code: '+378', name: 'San Marino', flag: '🇸🇲', iso: 'SM' },
    { code: '+380', name: 'Ukraine', flag: '🇺🇦', iso: 'UA' },
    { code: '+381', name: 'Serbia', flag: '🇷🇸', iso: 'RS' },
    { code: '+382', name: 'Montenegro', flag: '🇲🇪', iso: 'ME' },
    { code: '+383', name: 'Kosovo', flag: '🇽🇰', iso: 'XK' },
    { code: '+385', name: 'Croatia', flag: '🇭🇷', iso: 'HR' },
    { code: '+386', name: 'Slovenia', flag: '🇸🇮', iso: 'SI' },
    { code: '+387', name: 'Bosnia and Herzegovina', flag: '🇧🇦', iso: 'BA' },
    { code: '+389', name: 'North Macedonia', flag: '🇲🇰', iso: 'MK' },
    { code: '+420', name: 'Czech Republic', flag: '🇨🇿', iso: 'CZ' },
    { code: '+421', name: 'Slovakia', flag: '🇸🇰', iso: 'SK' },
    { code: '+423', name: 'Liechtenstein', flag: '🇱🇮', iso: 'LI' },
    { code: '+500', name: 'Falkland Islands', flag: '🇫🇰', iso: 'FK' },
    { code: '+501', name: 'Belize', flag: '🇧🇿', iso: 'BZ' },
    { code: '+502', name: 'Guatemala', flag: '🇬🇹', iso: 'GT' },
    { code: '+503', name: 'El Salvador', flag: '🇸🇻', iso: 'SV' },
    { code: '+504', name: 'Honduras', flag: '🇭🇳', iso: 'HN' },
    { code: '+505', name: 'Nicaragua', flag: '🇳🇮', iso: 'NI' },
    { code: '+506', name: 'Costa Rica', flag: '🇨🇷', iso: 'CR' },
    { code: '+507', name: 'Panama', flag: '🇵🇦', iso: 'PA' },
    { code: '+508', name: 'Saint Pierre and Miquelon', flag: '🇵🇲', iso: 'PM' },
    { code: '+509', name: 'Haiti', flag: '🇭🇹', iso: 'HT' },
    { code: '+590', name: 'Guadeloupe', flag: '🇬🇵', iso: 'GP' },
    { code: '+591', name: 'Bolivia', flag: '🇧🇴', iso: 'BO' },
    { code: '+592', name: 'Guyana', flag: '🇬🇾', iso: 'GY' },
    { code: '+593', name: 'Ecuador', flag: '🇪🇨', iso: 'EC' },
    { code: '+594', name: 'French Guiana', flag: '🇬🇫', iso: 'GF' },
    { code: '+595', name: 'Paraguay', flag: '🇵🇾', iso: 'PY' },
    { code: '+596', name: 'Martinique', flag: '🇲🇶', iso: 'MQ' },
    { code: '+597', name: 'Suriname', flag: '🇸🇷', iso: 'SR' },
    { code: '+598', name: 'Uruguay', flag: '🇺🇾', iso: 'UY' },
    { code: '+599', name: 'Curaçao', flag: '🇨🇼', iso: 'CW' },
    { code: '+670', name: 'East Timor', flag: '🇹🇱', iso: 'TL' },
    { code: '+672', name: 'Norfolk Island', flag: '🇳🇫', iso: 'NF' },
    { code: '+673', name: 'Brunei', flag: '🇧🇳', iso: 'BN' },
    { code: '+674', name: 'Nauru', flag: '🇳🇷', iso: 'NR' },
    { code: '+675', name: 'Papua New Guinea', flag: '🇵🇬', iso: 'PG' },
    { code: '+676', name: 'Tonga', flag: '🇹🇴', iso: 'TO' },
    { code: '+677', name: 'Solomon Islands', flag: '🇸🇧', iso: 'SB' },
    { code: '+678', name: 'Vanuatu', flag: '🇻🇺', iso: 'VU' },
    { code: '+679', name: 'Fiji', flag: '🇫🇯', iso: 'FJ' },
    { code: '+680', name: 'Palau', flag: '🇵🇼', iso: 'PW' },
    { code: '+681', name: 'Wallis and Futuna', flag: '🇼🇫', iso: 'WF' },
    { code: '+682', name: 'Cook Islands', flag: '🇨🇰', iso: 'CK' },
    { code: '+683', name: 'Niue', flag: '🇳🇺', iso: 'NU' },
    { code: '+684', name: 'American Samoa', flag: '🇦🇸', iso: 'AS' },
    { code: '+685', name: 'Samoa', flag: '🇼🇸', iso: 'WS' },
    { code: '+686', name: 'Kiribati', flag: '🇰🇮', iso: 'KI' },
    { code: '+687', name: 'New Caledonia', flag: '🇳🇨', iso: 'NC' },
    { code: '+688', name: 'Tuvalu', flag: '🇹🇻', iso: 'TV' },
    { code: '+689', name: 'French Polynesia', flag: '🇵🇫', iso: 'PF' },
    { code: '+690', name: 'Tokelau', flag: '🇹🇰', iso: 'TK' },
    { code: '+691', name: 'Micronesia', flag: '🇫🇲', iso: 'FM' },
    { code: '+692', name: 'Marshall Islands', flag: '🇲🇭', iso: 'MH' },
    { code: '+850', name: 'North Korea', flag: '🇰🇵', iso: 'KP' },
    { code: '+852', name: 'Hong Kong', flag: '🇭🇰', iso: 'HK' },
    { code: '+853', name: 'Macau', flag: '🇲🇴', iso: 'MO' },
    { code: '+855', name: 'Cambodia', flag: '🇰🇭', iso: 'KH' },
    { code: '+856', name: 'Laos', flag: '🇱🇦', iso: 'LA' },
    { code: '+880', name: 'Bangladesh', flag: '🇧🇩', iso: 'BD' },
    { code: '+886', name: 'Taiwan', flag: '🇹🇼', iso: 'TW' },
    { code: '+960', name: 'Maldives', flag: '🇲🇻', iso: 'MV' },
    { code: '+961', name: 'Lebanon', flag: '🇱🇧', iso: 'LB' },
    { code: '+962', name: 'Jordan', flag: '🇯🇴', iso: 'JO' },
    { code: '+963', name: 'Syria', flag: '🇸🇾', iso: 'SY' },
    { code: '+964', name: 'Iraq', flag: '🇮🇶', iso: 'IQ' },
    { code: '+965', name: 'Kuwait', flag: '🇰🇼', iso: 'KW' },
    { code: '+966', name: 'Saudi Arabia', flag: '🇸🇦', iso: 'SA' },
    { code: '+967', name: 'Yemen', flag: '🇾🇪', iso: 'YE' },
    { code: '+968', name: 'Oman', flag: '🇴🇲', iso: 'OM' },
    { code: '+970', name: 'Palestine', flag: '🇵🇸', iso: 'PS' },
    { code: '+971', name: 'United Arab Emirates', flag: '🇦🇪', iso: 'AE' },
    { code: '+972', name: 'Israel', flag: '🇮🇱', iso: 'IL' },
    { code: '+973', name: 'Bahrain', flag: '🇧🇭', iso: 'BH' },
    { code: '+974', name: 'Qatar', flag: '🇶🇦', iso: 'QA' },
    { code: '+975', name: 'Bhutan', flag: '🇧🇹', iso: 'BT' },
    { code: '+976', name: 'Mongolia', flag: '🇲🇳', iso: 'MN' },
    { code: '+977', name: 'Nepal', flag: '🇳🇵', iso: 'NP' },
    { code: '+992', name: 'Tajikistan', flag: '🇹🇯', iso: 'TJ' },
    { code: '+993', name: 'Turkmenistan', flag: '🇹🇲', iso: 'TM' },
    { code: '+994', name: 'Azerbaijan', flag: '🇦🇿', iso: 'AZ' },
    { code: '+995', name: 'Georgia', flag: '🇬🇪', iso: 'GE' },
    { code: '+996', name: 'Kyrgyzstan', flag: '🇰🇬', iso: 'KG' },
    { code: '+998', name: 'Uzbekistan', flag: '🇺🇿', iso: 'UZ' }
];

/**
 * Initialize enhanced phone input for a given input element
 * @param {string} inputId - The ID of the phone input element
 * @param {Object} options - Configuration options
 */
function initializePhoneInput(inputId, options = {}) {
    const input = document.getElementById(inputId);
    if (!input) {
        console.error(`Phone input element with ID '${inputId}' not found`);
        return;
    }

    const defaultOptions = {
        defaultCountry: 'US',
        placeholder: '(555) 123-4567',
        autoFormat: true,
        required: true
    };

    const config = { ...defaultOptions, ...options };
    
    // Create the enhanced phone input structure
    createPhoneInputStructure(input, config);
    
    // Initialize functionality
    setupPhoneInputBehavior(inputId, config);
}

/**
 * Create the HTML structure for the enhanced phone input
 */
function createPhoneInputStructure(originalInput, config) {
    const container = document.createElement('div');
    container.className = 'phone-input-container';
    container.style.cssText = `
        position: relative;
        display: flex;
        border: 2px solid #e5e7eb;
        border-radius: 12px;
        overflow: visible;
        background: white;
        transition: all 0.3s ease;
    `;

    // Country dropdown
    const countryDropdown = document.createElement('div');
    countryDropdown.className = 'country-dropdown';
    countryDropdown.style.cssText = `
        position: relative;
        background: #f9fafb;
        border-right: 1px solid #e5e7eb;
        cursor: pointer;
        user-select: none;
        min-width: 80px;
        display: flex;
        align-items: center;
        padding: 0 12px;
        transition: background-color 0.2s ease;
        z-index: 1;
    `;

    // Selected country display
    const selectedCountry = document.createElement('div');
    selectedCountry.className = 'selected-country';
    selectedCountry.style.cssText = `
        display: flex;
        align-items: center;
        gap: 6px;
        font-size: 14px;
        font-weight: 500;
    `;

    // Find default country
    const defaultCountryData = COUNTRIES.find(c => c.iso === config.defaultCountry) || COUNTRIES[0];
    
    selectedCountry.innerHTML = `
        <span class="country-flag" style="font-size: 16px;">${defaultCountryData.flag}</span>
        <span class="country-code" style="color: #374151;">${defaultCountryData.code}</span>
        <svg class="dropdown-arrow" style="width: 12px; height: 12px; color: #6b7280; transition: transform 0.2s ease;" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"></path>
        </svg>
    `;

    // Country dropdown menu
    const dropdownMenu = document.createElement('div');
    dropdownMenu.className = 'country-dropdown-menu';
    dropdownMenu.style.cssText = `
        position: absolute;
        top: 100%;
        left: 0;
        right: 0;
        background: white;
        border: 2px solid #e5e7eb;
        border-top: none;
        border-radius: 0 0 12px 12px;
        max-height: 200px;
        overflow-y: auto;
        z-index: 9999;
        display: none;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
        min-width: 200px;
    `;

    // Populate dropdown menu
    COUNTRIES.forEach(country => {
        const option = document.createElement('div');
        option.className = 'country-option';
        option.style.cssText = `
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 8px 12px;
            cursor: pointer;
            font-size: 14px;
            transition: background-color 0.2s ease;
        `;
        
        option.innerHTML = `
            <span style="font-size: 16px;">${country.flag}</span>
            <span style="flex: 1; color: #374151;">${country.name}</span>
            <span style="color: #6b7280; font-weight: 500;">${country.code}</span>
        `;
        
        option.addEventListener('mouseenter', () => {
            option.style.backgroundColor = '#f3f4f6';
        });
        
        option.addEventListener('mouseleave', () => {
            option.style.backgroundColor = 'transparent';
        });
        
        option.addEventListener('click', () => {
            selectCountry(country, selectedCountry, dropdownMenu, originalInput);
        });
        
        dropdownMenu.appendChild(option);
    });

    // Phone number input
    const phoneInput = document.createElement('input');
    phoneInput.type = 'tel';
    phoneInput.className = originalInput.className;
    phoneInput.placeholder = config.placeholder;
    phoneInput.required = config.required;
    phoneInput.style.cssText = `
        flex: 1;
        border: none;
        outline: none;
        padding: 12px 16px;
        font-size: 16px;
        background: transparent;
    `;
    
    // Copy attributes from original input
    phoneInput.id = originalInput.id;
    phoneInput.name = originalInput.name;
    if (originalInput.value) phoneInput.value = originalInput.value;

    // Assemble the structure
    countryDropdown.appendChild(selectedCountry);
    countryDropdown.appendChild(dropdownMenu);
    container.appendChild(countryDropdown);
    container.appendChild(phoneInput);



    // Replace original input
    originalInput.parentNode.replaceChild(container, originalInput);

    // Store references for later use
    container.phoneInput = phoneInput;
    container.countryDropdown = countryDropdown;
    container.selectedCountry = selectedCountry;
    container.dropdownMenu = dropdownMenu;
    container.currentCountry = defaultCountryData;
}

/**
 * Select a country and update the display
 */
function selectCountry(country, selectedCountryElement, dropdownMenu, originalInput) {
    // Update selected country display
    selectedCountryElement.innerHTML = `
        <span class="country-flag" style="font-size: 16px;">${country.flag}</span>
        <span class="country-code" style="color: #374151;">${country.code}</span>
        <svg class="dropdown-arrow" style="width: 12px; height: 12px; color: #6b7280; transition: transform 0.2s ease;" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"></path>
        </svg>
    `;
    
    // Close dropdown
    dropdownMenu.style.display = 'none';
    selectedCountryElement.querySelector('.dropdown-arrow').style.transform = 'rotate(0deg)';
    
    // Update current country
    const container = selectedCountryElement.closest('.phone-input-container');
    container.currentCountry = country;
    
    // Clear and focus phone input
    const phoneInput = container.phoneInput;
    phoneInput.value = '';
    phoneInput.focus();
}

/**
 * Setup behavior for the phone input
 */
function setupPhoneInputBehavior(inputId, config) {
    const container = document.querySelector(`#${inputId}`).closest('.phone-input-container');
    const phoneInput = container.phoneInput;
    const countryDropdown = container.countryDropdown;
    const dropdownMenu = container.dropdownMenu;
    const selectedCountry = container.selectedCountry;

    // Dropdown toggle
    countryDropdown.addEventListener('click', (e) => {
        e.stopPropagation();
        const isOpen = dropdownMenu.style.display === 'block';

        if (isOpen) {
            dropdownMenu.style.display = 'none';
            selectedCountry.querySelector('.dropdown-arrow').style.transform = 'rotate(0deg)';
        } else {
            dropdownMenu.style.display = 'block';
            selectedCountry.querySelector('.dropdown-arrow').style.transform = 'rotate(180deg)';
        }
    });

    // Close dropdown when clicking outside
    document.addEventListener('click', () => {
        dropdownMenu.style.display = 'none';
        selectedCountry.querySelector('.dropdown-arrow').style.transform = 'rotate(0deg)';
    });

    // Phone number formatting
    if (config.autoFormat) {
        phoneInput.addEventListener('input', (e) => {
            formatPhoneNumber(e.target, container.currentCountry);
        });
    }

    // Focus styles
    phoneInput.addEventListener('focus', () => {
        container.style.borderColor = '#2a9d8f';
        container.style.boxShadow = '0 0 0 3px rgba(42, 157, 143, 0.1)';
    });

    phoneInput.addEventListener('blur', () => {
        container.style.borderColor = '#e5e7eb';
        container.style.boxShadow = 'none';
    });

    // Hover styles
    container.addEventListener('mouseenter', () => {
        if (document.activeElement !== phoneInput) {
            container.style.borderColor = '#d1d5db';
        }
    });

    container.addEventListener('mouseleave', () => {
        if (document.activeElement !== phoneInput) {
            container.style.borderColor = '#e5e7eb';
        }
    });
}

/**
 * Format phone number based on country
 */
function formatPhoneNumber(input, country) {
    let value = input.value.replace(/\D/g, '');
    
    if (country.code === '+1') {
        // US/Canada formatting: (555) 123-4567
        if (value.length >= 6) {
            value = `(${value.slice(0, 3)}) ${value.slice(3, 6)}-${value.slice(6, 10)}`;
        } else if (value.length >= 3) {
            value = `(${value.slice(0, 3)}) ${value.slice(3)}`;
        } else if (value.length > 0) {
            value = `(${value}`;
        }
    }
    // Add more country-specific formatting as needed
    
    input.value = value;
}

/**
 * Parse a complete phone number to extract country and local parts
 * @param {string} phoneNumber - Complete phone number with country code
 * @returns {Object} - {countryCode: 'US', localNumber: '5551234567', fullCode: '+1'}
 */
function parsePhoneNumber(phoneNumber) {
    if (!phoneNumber || !phoneNumber.startsWith('+')) {
        return { countryCode: 'US', localNumber: phoneNumber || '', fullCode: '+1' };
    }

    // Sort countries by code length (longest first) to match correctly
    const sortedCountries = [...COUNTRIES].sort((a, b) => b.code.length - a.code.length);

    for (const country of sortedCountries) {
        if (phoneNumber.startsWith(country.code)) {
            const localNumber = phoneNumber.substring(country.code.length);
            return {
                countryCode: country.iso,
                localNumber: localNumber,
                fullCode: country.code
            };
        }
    }

    // Default fallback
    return { countryCode: 'US', localNumber: phoneNumber.substring(1), fullCode: '+1' };
}

/**
 * Get the complete phone number with country code
 */
function getCompletePhoneNumber(inputId) {
    const container = document.querySelector(`#${inputId}`).closest('.phone-input-container');
    if (!container) return '';

    const phoneInput = container.phoneInput;
    const country = container.currentCountry;
    const phoneNumber = phoneInput.value.replace(/\D/g, '');

    return phoneNumber ? `${country.code}${phoneNumber}` : '';
}

// Export for global use
window.initializePhoneInput = initializePhoneInput;
window.getCompletePhoneNumber = getCompletePhoneNumber;
window.parsePhoneNumber = parsePhoneNumber;
