document.addEventListener('DOMContentLoaded', () => {
    
    // Insight Cards Expand/Collapse
    const insightHeaders = document.querySelectorAll('.insight-header');
    
    insightHeaders.forEach(header => {
        header.addEventListener('click', () => {
            const card = header.closest('.insight-card');
            const body = card.querySelector('.insight-body');
            const icon = header.querySelector('.toggle-icon');
            
            const isExpanded = card.classList.contains('expanded');
            
            if (isExpanded) {
                card.classList.remove('expanded');
                if (body) body.style.display = 'none';
                if (icon) icon.textContent = '▶';
            } else {
                card.classList.add('expanded');
                if (body) body.style.display = 'block';
                if (icon) icon.textContent = '▼';
            }
        });
    });

    // General Expanders
    const expanderHeaders = document.querySelectorAll('.expander-header');
    
    expanderHeaders.forEach(header => {
        header.addEventListener('click', () => {
            const expander = header.closest('.expander');
            const body = expander.querySelector('.expander-body');
            const icon = header.querySelector('.toggle-icon');
            
            if (!body) return;
            
            const isHidden = body.style.display === 'none' || !body.style.display;
            
            if (isHidden) {
                body.style.display = 'block';
                if (icon) icon.textContent = '▼';
            } else {
                body.style.display = 'none';
                if (icon) icon.textContent = '▶';
            }
        });
    });

    // Make metric hover effects dynamic
    const metricCards = document.querySelectorAll('.metric-card');
    metricCards.forEach(card => {
        card.addEventListener('mouseenter', () => {
            card.style.transform = 'translateY(-2px)';
            card.style.transition = 'transform 0.2s ease';
        });
        card.addEventListener('mouseleave', () => {
            card.style.transform = 'translateY(0)';
        });
    });
});
