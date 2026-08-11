/**
 * Hamburger-Menü: Synchronisiert das [open]-Attribut des <details class="mobile-menu">
 * mit der Viewport-Breite.
 *
 * - Desktop (>= 769px): open = true  -> Menü immer ausgeklappt (Sidebar-Look)
 * - Mobile  (<  769px): open = false -> Menü startet geschlossen (Hamburger)
 *
 * Reagiert auch auf nachträgliche Viewport-Wechsel (Gerät drehen, Fenster resizen).
 */
(function () {
    var menu = document.querySelector('.mobile-menu');
    if (!menu) return;

    var mq = window.matchMedia('(min-width: 769px)');
    var sync = function () { menu.open = mq.matches; };

    sync();
    mq.addEventListener('change', sync);
})();
