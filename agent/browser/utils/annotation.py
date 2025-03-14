"""
Annotation actions for labeling and identifying interactive elements on web pages.
"""

from typing import Dict, List

from playwright.async_api import Page

# JavaScript template for finding and identifying interactive elements
FIND_INTERACTIVE_ELEMENTS_TEMPLATE = r"""() => {
    // Remove any existing data-gwa-id attributes to avoid duplicates
    document.querySelectorAll('[data-gwa-id]').forEach(el => {
        el.removeAttribute('data-gwa-id');
    });

    const elements = Array.from(document.querySelectorAll("a, button, input, textarea, select"));
    let element_simplified_htmls = {}; // HTML for each element index

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

        // For small form elements, check parent element dimensions
        if (isSmallFormElement) {
            const parentWithLabel = getParentWithLabel(element);
            if (parentWithLabel !== element) {
                const parentRect = parentWithLabel.getBoundingClientRect();
                if (parentRect.width <= 1 || parentRect.height <= 1) {
                    return false;
                }
            }
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

            // Determine the element to which we'll add the data-gwa-id attribute
            let targetElement = element;
            
            // For input elements, especially checkboxes and radio buttons, 
            // use the parent element that contains the label
            if (tagName === 'input' && (element.type === 'radio' || element.type === 'checkbox')) {
                targetElement = getParentWithLabel(element);
            } else if (tagName === 'input' || tagName === 'textarea' || tagName === 'select') {
                // For other form elements, check if there's a direct label to use
                if (element.id) {
                    const associatedLabel = document.querySelector(`label[for="${element.id}"]`);
                    if (associatedLabel) {
                        targetElement = associatedLabel;
                    }
                } else if (element.parentElement && element.parentElement.tagName.toLowerCase() === 'label') {
                    targetElement = element.parentElement;
                }
            }
            
            // Set a data attribute to uniquely identify the element using the visible index
            targetElement.setAttribute('data-gwa-id', `gwa-element-${visibleIndex}`);
            
            // Store simplified HTML with visible index as key
            element_simplified_htmls[visibleIndex] = simplified_html;

            visibleIndex++;
        }
    });
    return element_simplified_htmls;
}"""

# JavaScript template for drawing bounding boxes around annotated elements
DRAW_BOUNDING_BOXES_TEMPLATE = r"""(indices) => {
    // If no indices provided, draw boxes for all elements with data-gwa-id
    if (!indices || indices.length === 0) {
        indices = Array.from(document.querySelectorAll('[data-gwa-id]')).map(el => {
            const id = el.getAttribute('data-gwa-id');
            return parseInt(id.replace('gwa-element-', ''));
        });
    }

    // Clear any existing annotations first
    const removeElementsByClass = (className) => {
        const elements = Array.from(document.querySelectorAll(className));
        elements.forEach(element => {
            element.remove();
        });
    };
    removeElementsByClass(".GWA-rect");
    removeElementsByClass(".GWA-label");

    // Draw new annotations
    indices.forEach(index => {
        const element = document.querySelector(`[data-gwa-id="gwa-element-${index}"]`);
        if (!element) return;

        const rect = element.getBoundingClientRect();
        const adjustedTop = rect.top + window.scrollY;
        const adjustedLeft = rect.left + window.scrollX;

        // Create rectangle around element
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

        // Create label with index number
        const label = document.createElement("span");
        label.className = "GWA-label";
        label.textContent = index;
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
    });
    
    return indices.length;
}"""


async def find_interactive_elements(page: Page) -> Dict[int, str]:
    """
    Find and identify interactive elements on the page.
    This function adds data-gwa-id attributes to elements but does not draw visual annotations.

    Args:
        page: The Playwright page

    Returns:
        A dictionary mapping visible indices to simplified HTML representations
    """

    html_dict = await page.evaluate(FIND_INTERACTIVE_ELEMENTS_TEMPLATE)

    # Convert string keys to integers
    element_simplified_htmls = {int(k): v for k, v in html_dict.items()}

    return element_simplified_htmls


async def draw_bounding_boxes(page: Page, indices: List[int]) -> int:
    """
    Draw bounding boxes around elements with data-gwa-id attributes.

    Args:
        page: The Playwright page
        indices: List of specific element indices to annotate.

    Returns:
        Number of elements that were annotated
    """
    return await page.evaluate(DRAW_BOUNDING_BOXES_TEMPLATE, indices)


async def annotate_element_by_element_id(page: Page, element_id: int) -> None:
    """
    Draw a bounding box around the element with the specified index.

    Args:
        page: The Playwright page
        element_id: The unique GWA ID of the element to annotate
    """
    await draw_bounding_boxes(page, [element_id])


async def clear_bounding_boxes(page: Page) -> None:
    """
    Clear any bounding boxes from the page.
    Note: This does not remove the data-gwa-id attributes.

    Args:
        page: The Playwright page
    """
    await page.evaluate(
        "() => { "
        + "Array.from(document.querySelectorAll('.GWA-rect, .GWA-label')).forEach(el => el.remove());"
        + " }"
    )
