export function initAddonPurchase() {
    const pricingEl = document.getElementById('addon-pricing-display');
    if (!pricingEl) return;

    const totalEl = document.getElementById('addon-calculated-total');
    const quantityDisplay = document.getElementById('addon-selected-quantity');
    const unitPrice = parseFloat(pricingEl.dataset.unitPrice || '0');
    const currency = pricingEl.dataset.currency || '';
    const quantityInput = document.getElementById('id_quantity');

    function updateTotal() {
        const qty = quantityInput ? (parseInt(quantityInput.value, 10) || 1) : 1;
        if (quantityDisplay) {
            quantityDisplay.textContent = qty.toString();
        }
        if (totalEl) {
            const total = (unitPrice * qty).toFixed(2);
            totalEl.textContent = `${total} ${currency}`;
        }
    }

    if (quantityInput) {
        quantityInput.addEventListener('input', updateTotal);
        quantityInput.addEventListener('change', updateTotal);
    }
    updateTotal();
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initAddonPurchase);
} else {
    initAddonPurchase();
}
