/**
 * FORMYLA Mobile Navigation
 * Burger menu for mobile devices
 */

function toggleMobileNav() {
    const nav = document.getElementById('navLinks');
    const burger = document.querySelector('.nav-burger');
    if (!nav || !burger) return;
    
    const isOpen = nav.classList.toggle('open');
    burger.classList.toggle('active', isOpen);
    document.body.classList.toggle('nav-open', isOpen);
    
    // Update aria
    burger.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
}

function closeMobileNav() {
    const nav = document.getElementById('navLinks');
    const burger = document.querySelector('.nav-burger');
    if (!nav || !burger) return;
    
    nav.classList.remove('open');
    burger.classList.remove('active');
    document.body.classList.remove('nav-open');
    burger.setAttribute('aria-expanded', 'false');
}

// Close on nav link click
document.addEventListener('DOMContentLoaded', function() {
    document.querySelectorAll('#navLinks .nav-link, #navLinks a').forEach(function(a) {
        a.addEventListener('click', closeMobileNav);
    });
    
    // Close on Escape key
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') closeMobileNav();
    });
    
    // Close on backdrop click (outside nav)
    document.addEventListener('click', function(e) {
        const nav = document.getElementById('navLinks');
        const burger = document.querySelector('.nav-burger');
        if (!nav || !burger) return;
        
        if (nav.classList.contains('open') && 
            !nav.contains(e.target) && 
            !burger.contains(e.target)) {
            closeMobileNav();
        }
    });
});

// Export for inline onclick
window.toggleMobileNav = toggleMobileNav;
window.closeMobileNav = closeMobileNav;
