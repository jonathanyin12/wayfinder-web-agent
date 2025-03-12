"""
Annotation actions for labeling and identifying interactive elements on web pages.
"""

from typing import Dict, Tuple

from playwright.async_api import Page

# JavaScript template for annotating page elements
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
        
        // Check if element or its ancestors are hidden
        if (isHiddenByAncestors(element)) {
            return false;
        }

        // Check if element is actually clickable/interactive
        if (style.pointerEvents === 'none') {
            return false;
        }

        // Special handling for small form elements
        const isSmallFormElement = element.tagName.toLowerCase() === 'input' && 
            (element.type === 'radio' || element.type === 'checkbox') &&
            element.offsetWidth <= 1 && element.offsetHeight <= 1;

        // Basic size and style checks (skip for small form elements)
        if (!isSmallFormElement && (
            element.offsetWidth <= 1 || element.offsetHeight <= 1 ||
            style.visibility === 'hidden' || style.display === 'none')) {
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

    function getParentWithLabel(element) {
        // If input has an associated label via 'for' attribute
        if (element.id) {
            const associatedLabel = document.querySelector(`label[for="${element.id}"]`);
            if (associatedLabel) {
                // Find common parent of input and label
                let inputParent = element.parentElement;
                while (inputParent) {
                    if (inputParent.contains(associatedLabel)) {
                        return inputParent;
                    }
                    inputParent = inputParent.parentElement;
                }
            }
        }
        
        // If input is wrapped in a label
        let parent = element.parentElement;
        while (parent) {
            if (parent.tagName.toLowerCase() === 'label') {
                return parent;
            }
            // Check if parent contains a label for this input
            const childLabels = parent.getElementsByTagName('label');
            for (const label of childLabels) {
                if (label.getAttribute('for') === element.id || label.contains(element)) {
                    return parent;
                }
            }
            parent = parent.parentElement;
        }
        
        return element; // fallback to the element itself
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

            // Keep the original selector pointing to the input element
            const cssSelector = getCssSelector(element);
            label_selectors[visibleIndex] = cssSelector;
            label_simplified_htmls[visibleIndex] = simplified_html;

            // Only use parent for visual display
            const targetElement = element.tagName.toLowerCase() === 'input' &&
                (element.type === 'radio' || element.type === 'checkbox') ?
                getParentWithLabel(element) : element;

            // Draw rectangle using parent dimensions
            const rect = targetElement.getBoundingClientRect();
            const adjustedTop = rect.top + window.scrollY;
            const adjustedLeft = rect.left + window.scrollX;

            const newElement = document.createElement('div');
            newElement.className = 'GWA-rect';
            newElement.style.border = '2px solid brown';
            newElement.style.position = 'absolute';
            newElement.style.top = `${adjustedTop}px`;
            newElement.style.left = `${adjustedLeft}px`;
            newElement.style.width = `${rect.width}px`;
            newElement.style.height = `${rect.height}px`;
            newElement.style.zIndex = 10000;
            newElement.style.pointerEvents = 'none';
            document.body.appendChild(newElement);

            const label = document.createElement("span");
            label.className = "GWA-label";
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


async def annotate_page(page: Page) -> Tuple[Dict[int, str], Dict[int, str]]:
    """
    Annotate the page with labels for interactive elements.

    Args:
        page: The Playwright page

    Returns:
        A tuple containing (label_selectors, label_simplified_htmls) with integer keys
    """
    selectors_dict, html_dict = await page.evaluate(ANNOTATE_PAGE_TEMPLATE)

    # Convert string keys to integers
    label_selectors = {int(k): v for k, v in selectors_dict.items()}
    label_simplified_htmls = {int(k): v for k, v in html_dict.items()}

    return label_selectors, label_simplified_htmls


ANNOTATE_PAGE_WITH_SINGLE_ELEMENT_TEMPLATE = """(selector) => {
        const element = document.querySelector(selector);
        if (!element) return;
        
        // Special handling for input elements
        let targetElement = element;
        if (element.tagName.toLowerCase() === 'input' && 
            (element.type === 'radio' || element.type === 'checkbox')) {
            // Find parent with label
            function getParentWithLabel(element) {
                // If input has an associated label via 'for' attribute
                if (element.id) {
                    const associatedLabel = document.querySelector(`label[for="${element.id}"]`);
                    if (associatedLabel) {
                        // Find common parent of input and label
                        let inputParent = element.parentElement;
                        while (inputParent) {
                            if (inputParent.contains(associatedLabel)) {
                                return inputParent;
                            }
                            inputParent = inputParent.parentElement;
                        }
                    }
                }
                
                // If input is wrapped in a label
                let parent = element.parentElement;
                while (parent) {
                    if (parent.tagName.toLowerCase() === 'label') {
                        return parent;
                    }
                    // Check if parent contains a label for this input
                    const childLabels = parent.getElementsByTagName('label');
                    for (const label of childLabels) {
                        if (label.getAttribute('for') === element.id || label.contains(element)) {
                            return parent;
                        }
                    }
                    parent = parent.parentElement;
                }
                
                return element; // fallback to the element itself
            }
            
            targetElement = getParentWithLabel(element);
        }
        
        const rect = targetElement.getBoundingClientRect();
        
        const box = document.createElement("div");
        box.className = "GWA-rect";
        box.style.position = "absolute";
        box.style.border = "2px solid red";
        box.style.top = `${rect.top}px`;
        box.style.left = `${rect.left}px`;
        box.style.width = `${rect.width}px`;
        box.style.height = `${rect.height}px`;
        box.style.zIndex = 10000;
        box.style.pointerEvents = "none";
        
        document.body.appendChild(box);
    }"""


async def annotate_page_with_single_element(page: Page, label_selector: str) -> None:
    """
    Annotate the page with a single element.

    Args:
        page: The Playwright page
        label_selector: The CSS selector for the element to annotate
    """
    await page.evaluate(ANNOTATE_PAGE_WITH_SINGLE_ELEMENT_TEMPLATE, label_selector)


CLEAR_PAGE_TEMPLATE = """() => {
    const removeElementsByClass = (className) => {
        const elements = Array.from(document.querySelectorAll(className));
        elements.forEach((element, index) => {
            element.remove();
        });
    };
    removeElementsByClass(".GWA-rect");
    removeElementsByClass(".GWA-label");
}"""


async def clear_annotations(page: Page) -> None:
    """
    Clear any annotations from the page.

    Args:
        page: The Playwright page
    """
    await page.evaluate(CLEAR_PAGE_TEMPLATE)
