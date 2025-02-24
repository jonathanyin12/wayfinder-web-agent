from typing import Dict, Tuple

from playwright.async_api import Page

ANNOTATE_PAGE_TEMPLATE = r"""() => {
    const elements = Array.from(document.querySelectorAll("a, button, input, textarea, select"));
    let label_selectors = {};
    let label_simplified_htmls = {};

    function isHiddenByAncestors(element) {
        while (element) {
            const style = window.getComputedStyle(element);
            if (style.display === 'none' || style.visibility === 'hidden') {
                return true;
            }
            element = element.parentElement;
        }
        return false;
    }

    const getCssSelector = (element) => {
        if (element === null) return "";
        let path = [];
        while (element && element.nodeType === Node.ELEMENT_NODE) {
            let selector = element.nodeName.toLowerCase();
            if (element.id) {
                selector += "#" + CSS.escape(element.id);
                path.unshift(selector);
                break;
            } else {
                let sib = element;
                let nth = 1;
                while ((sib = sib.previousElementSibling)) {
                    if (sib.nodeName.toLowerCase() == selector) nth++;
                }
                if (nth != 1) selector += ":nth-of-type(" + nth + ")";
            }
            path.unshift(selector);
            element = element.parentNode;
        }
        return path.join(" > ");
    };

    function isElementVisible(element) {
        const rect = element.getBoundingClientRect();
        const style = window.getComputedStyle(element);
        
        // Basic size and style checks
        if (element.offsetWidth <= 1 || element.offsetHeight <= 1 ||
            style.visibility === 'hidden' || style.display === 'none') {
            return false;
        }

        // Check if element or its ancestors are hidden
        if (isHiddenByAncestors(element)) {
            return false;
        }

        // Check if element is actually clickable/interactive
        if (style.pointerEvents === 'none') {
            return false;
        }

        // Check if element is covered by other elements
        const elementAtPoint = document.elementFromPoint(
            rect.left + rect.width/2,
            rect.top + rect.height/2
        );
        
        // For form elements, check if clicking their label or container would trigger them
        if (element.tagName.toLowerCase() === 'input' && 
            (element.type === 'radio' || element.type === 'checkbox')) {
            // Consider the element visible if we hit its label or a parent with click handler
            let currentElement = elementAtPoint;
            while (currentElement) {
                if (currentElement.tagName.toLowerCase() === 'label' && 
                    currentElement.getAttribute('for') === element.id) {
                    return true;
                }
                // Check if this is an ancestor that would handle the click
                if (currentElement.contains(element)) {
                    return true;
                }
                currentElement = currentElement.parentElement;
            }
        }
        
        // General visibility check for other elements
        if (!elementAtPoint || 
            (elementAtPoint !== element && 
             !element.contains(elementAtPoint) && 
             !elementAtPoint.contains(element))) {
            return false;
        }

        // Check if element has meaningful dimensions
        if (rect.width * rect.height === 0) {
            return false;
        }

        // Viewport visibility check
        return (
            rect.top >= 0 &&
            rect.left >= 0 &&
            rect.bottom <= (window.innerHeight || document.documentElement.clientHeight) &&
            rect.right <= (window.innerWidth || document.documentElement.clientWidth)
        );
    }

    let visibleIndex = 0;
    elements.forEach((element) => {
        if (isElementVisible(element)) {
            const tagName = element.tagName.toLowerCase();
            let simplified_html = '<' + tagName;
            for (const attr of ['aria-label', 'alt', 'placeholder', 'value']) {
                if (element.hasAttribute(attr)) {
                    let attrValue = element.getAttribute(attr);
                    simplified_html += ` ${attr}="${attrValue}"`;
                }
            }

            // Get inner text from the element.
            let innerText = element.textContent.replace(/\n/g, ' ').trim();

            // For input elements, we need to look elsewhere for the visible label text.
            if (tagName === 'input' && innerText === '') {
                // 1. Try to get an associated label via the "for" attribute.
                if (element.id) {
                    const associatedLabel = document.querySelector(`label[for="${element.id}"]`);
                    if (associatedLabel) {
                        innerText = associatedLabel.textContent.replace(/\n/g, ' ').trim();
                    }
                }
                // 2. Check if the input is wrapped in a <label>.
                if (innerText === '' && element.parentElement && element.parentElement.tagName.toLowerCase() === 'label') {
                    innerText = element.parentElement.textContent.replace(/\n/g, ' ').trim();
                }
                // 3. Check if a sibling <span> element holds the text.
                if (innerText === '') {
                    if (element.nextElementSibling && element.nextElementSibling.tagName.toLowerCase() === 'span') {
                        innerText = element.nextElementSibling.textContent.replace(/\n/g, ' ').trim();
                    } else if (element.previousElementSibling && element.previousElementSibling.tagName.toLowerCase() === 'span') {
                        innerText = element.previousElementSibling.textContent.replace(/\n/g, ' ').trim();
                    }
                }
                // 4. Fallback to the "value" or "placeholder" attribute.
                if (innerText === '') {
                    innerText = element.getAttribute('value') || element.getAttribute('placeholder') || '';
                }
            }

            simplified_html = simplified_html + '>' + innerText + '</' + tagName + '>';
            simplified_html = simplified_html.replace(/\s+/g, ' ').trim();

            const cssSelector = getCssSelector(element);
            label_selectors[visibleIndex] = cssSelector;
            label_simplified_htmls[visibleIndex] = simplified_html;

            // Adjust positions with scroll offset
            const adjustedTop = element.getBoundingClientRect().top + window.scrollY;
            const adjustedLeft = element.getBoundingClientRect().left + window.scrollX;

            const newElement = document.createElement('div');
            newElement.className = 'autopilot-generated-rect';
            newElement.style.border = '2px solid brown';
            newElement.style.position = 'absolute';
            newElement.style.top = `${adjustedTop}px`;
            newElement.style.left = `${adjustedLeft}px`;
            newElement.style.width = `${element.getBoundingClientRect().width}px`;
            newElement.style.height = `${element.getBoundingClientRect().height}px`;
            newElement.style.zIndex = 10000;
            newElement.style.pointerEvents = 'none';
            document.body.appendChild(newElement);

            const label = document.createElement("span");
            label.className = "autopilot-generated-label";
            label.textContent = visibleIndex;
            label.style.position = "absolute";
            label.style.lineHeight = "16px";
            label.style.padding = "1px";
            label.style.top = `${adjustedTop}px`;
            label.style.left = `${adjustedLeft}px`;
            label.style.color = "white";
            label.style.fontWeight = "bold";
            label.style.fontSize = "16px";
            label.style.backgroundColor = "brown";
            label.style.zIndex = 10000;
            document.body.appendChild(label);

            visibleIndex++;
        }
    });
    return [label_selectors, label_simplified_htmls];
}"""


CLEAR_PAGE_TEMPLATE = """() => {
    const removeElementsByClass = (className) => {
        const elements = Array.from(document.querySelectorAll(className));
        elements.forEach((element, index) => {
            element.remove();
        });
    };
    removeElementsByClass(".autopilot-generated-rect");
    removeElementsByClass(".autopilot-generated-label");
}"""


async def annotate_page(page: Page) -> Tuple[Dict[int, str], Dict[int, str]]:
    label_selectors, label_simplified_htmls = await page.evaluate(
        ANNOTATE_PAGE_TEMPLATE
    )
    return label_selectors, label_simplified_htmls


async def clear_annotations(page: Page):
    await page.evaluate(CLEAR_PAGE_TEMPLATE)
