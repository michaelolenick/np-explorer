// Google tag (gtag.js) setup, the owner's snippet from Google Analytics (G-9DBTED3NDF). It lives in this file
// rather than inline because the Content-Security-Policy allows only same-origin scripts. The measurement ID comes
// from the script tag (app/config.py GA_MEASUREMENT_ID; production only).
window.dataLayer = window.dataLayer || [];
function gtag(){dataLayer.push(arguments);}
gtag('js', new Date());

gtag('config', (document.currentScript && document.currentScript.getAttribute('data-ga-id')) || 'G-9DBTED3NDF');
